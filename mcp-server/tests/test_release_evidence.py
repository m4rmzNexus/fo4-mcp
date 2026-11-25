import hashlib
import json
import sqlite3
import struct
import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from fo4_mcp import asset_catalog, bgsm_ops, release_zip, tools
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.manifest import Manifest, ToolEntry


def make_catalog(path, copies):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE assets (id INTEGER, source INTEGER, path TEXT);
            CREATE TABLE sources (id INTEGER, provider TEXT, kind TEXT, path TEXT);
            CREATE TABLE issues (asset INTEGER, reason TEXT);
            CREATE TABLE shapes (asset INTEGER, block INTEGER, material TEXT);
            CREATE TABLE materials (asset INTEGER, fields TEXT);
        """)
        for i, provider in enumerate(copies):
            db.execute("INSERT INTO sources VALUES (?, ?, 'ba2', ?)", (i, provider, provider + ".ba2"))
            db.execute("INSERT INTO assets VALUES (?, ?, 'materials/wall.bgsm')", (i, i))
            db.execute("INSERT INTO materials VALUES (?, ?)", (i, json.dumps({"DiffuseTexture": provider + ".dds"})))


def test_snapshots_keep_all_variants_and_do_not_leak_between_profiles(tmp_path):
    a, b = tmp_path / "a.db", tmp_path / "b.db"
    make_catalog(a, ["original", "replacement"])
    make_catalog(b, [])
    query = "Materials\\Wall.BGSM"
    result = asset_catalog.inspect_catalog(a, query)["data"]
    assert len(result["assets"]["materials/wall.bgsm"]) == 2
    assert set(result["absent"]) == {"textures/original.dds", "textures/replacement.dds"}
    assert asset_catalog.inspect_catalog(a, query, max_paths=1)["data"]["truncated"]
    assert asset_catalog.inspect_catalog(b, query)["data"]["absent"] == ["materials/wall.bgsm"]


def test_release_uses_final_zip_not_adjacent_source_tree(tmp_path):
    source = tmp_path / "Textures" / "Wall.dds"
    source.parent.mkdir()
    source.write_bytes(b"local fallback")
    mat = bgsm_ops.defaults()
    mat["DiffuseTexture"] = "Wall.dds\0"
    out = tmp_path / "test.zip"
    with ZipFile(out, "w") as z:
        z.writestr("Materials/Wall.bgsm", bgsm_ops.encode(mat))
    report = release_zip.inspect_zip(out, ["Textures/Wall.dds"])["data"]
    assert report["verdict"] == "fail"
    assert report["missing_expected"] == ["textures/wall.dds"]
    assert report["unresolved_loose_references"]["textures/wall.dds"]["examples"][0]["field"] == "DiffuseTexture"
    with ZipFile(out, "a") as z:
        z.write(source, "TEXTURES/Wall.dds")
    assert release_zip.inspect_zip(out, ["Textures/Wall.dds"])["data"]["verdict"] == "pass"


def test_installer_sources_resolve_relative_to_wrapped_fomod_root(tmp_path):
    out = tmp_path / "test.zip"
    with ZipFile(out, "w") as z:
        z.writestr("bundle/fomod/ModuleConfig.xml", '<config><moduleName>W</moduleName><requiredInstallFiles>'
                   '<folder source="data"/><file source="absent.esp"/></requiredInstallFiles></config>')
        z.writestr("bundle/Data/Here.esp", b"")
        z.writestr("absent.esp", b"outside installer root")
    report = release_zip.inspect_zip(out, [])["data"]
    assert report["verdict"] == "fail"
    assert list(report["fomod_missing_sources"].values()) == [["bundle/absent.esp"]]


def test_duplicate_windows_path(tmp_path):
    zpath = tmp_path / "case.zip"
    with ZipFile(zpath, "w") as z:
        z.writestr("FO4.esp", b"1")
        z.writestr("fo4.esp", b"2")
    report = release_zip.inspect_zip(zpath, [])["data"]
    assert report["duplicates"] == ["fo4.esp"] and report["verdict"] == "fail"


def test_crc_checks_the_actual_payload(tmp_path):
    path = tmp_path / "crc.zip"
    with ZipFile(path, "w") as z:
        z.writestr("terrain.esm", b"original-payload")
    assert release_zip.inspect_zip(path, [], verify_crc=True)["data"]["crc_verified"] is True
    path.write_bytes(path.read_bytes().replace(b"original-payload", b"modified-payload"))
    report = release_zip.inspect_zip(path, [], verify_crc=True)["data"]
    assert report["damaged_member"] == "terrain.esm" and report["verdict"] == "fail"


def test_missing_catalog_is_never_created(tmp_path):
    missing = tmp_path / "missing.sqlite"
    with pytest.raises(Fo4McpError):
        asset_catalog.inspect_catalog(missing, "Materials/Wall.bgsm")
    assert not missing.exists()


def test_matching_apphost_does_not_hide_stale_writer(tmp_path):
    (tmp_path / "writer.exe").write_bytes(b"launcher")
    (tmp_path / "writer.dll").write_bytes(b"different build")
    entry = ToolEntry("writer", "1", "", "", "writer.exe", "", {
        "sha256": hashlib.sha256(b"launcher").hexdigest(),
        "managed_dll_sha256": hashlib.sha256(b"expected build").hexdigest(),
    })
    manifest = Manifest({"writer": entry}, tmp_path / "MANIFEST.md")
    report = manifest.check_selected(tmp_path, ["writer"])["writer"]
    assert report["sha256_matches"] is True
    assert report["managed_dll"]["sha256_matches"] is False


def test_shader_material_points_to_package_member(tmp_path):
    def string(raw):
        return struct.pack("<I", len(raw)) + raw

    # FO4 BSLightingShaderProperty: shader type followed by NiObjectNET Name.
    shader = struct.pack("<Ii", 0, 0)
    nif = (b"Gamebryo File Format, Version 20.2.0.7\n" + struct.pack("<IBIII", 0x14020007, 1, 12, 1, 130)
           + bytes(4) + struct.pack("<H", 1) + string(b"BSLightingShaderProperty")
           + struct.pack("<HIII", 0, len(shader), 1, 19) + string(b"Materials/Wall.bgsm")
           + struct.pack("<I", 0) + shader + struct.pack("<II", 1, 0))
    path = tmp_path / "test.zip"
    with ZipFile(path, "w") as z:
        z.writestr("Meshes/Test.nif", nif)
    report = release_zip.inspect_zip(path, [])["data"]
    assert report["unresolved_loose_references"]["materials/wall.bgsm"]["references"] == 1
    assert report["verdict"] == "review"
    with ZipFile(path, "a") as z:
        z.writestr("Materials/Wall.bgsm", bgsm_ops.encode(bgsm_ops.defaults()))
    assert release_zip.inspect_zip(path, [])["data"]["verdict"] == "pass"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows version resource")
def test_runtime_version_reads_resource_not_filesize(tmp_path):
    exe = tmp_path / "Fallout4.exe"
    exe.write_bytes(b"placeholder")
    assert tools._windows_file_version(exe) is None
    # The interpreter executable ships with a fixed file version on Windows.
    assert len(tools._windows_file_version(Path(sys.executable)).split(".")) == 4
