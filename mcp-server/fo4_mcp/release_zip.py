"""Inspect the final ZIP directory, FOMOD sources and loose material references in place."""
from __future__ import annotations

import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from . import bgsm_ops, nif_ops
from .asset_catalog import material_links, open_catalog, providers, virtual_path
from .errors import ErrorCode, Fo4McpError, ok


def member_key(name):
    path = virtual_path(name).rstrip("/")
    if not path or ":" in path or any(part in ("", ".", "..") for part in path.split("/")):
        raise ValueError(f"Invalid relative archive path: {name!r}")
    return path


def read_small(archive, member, limit):
    if member.file_size > limit:
        raise ValueError(f"{member.filename} exceeds the {limit}-byte inspection limit")
    return archive.read(member)


def installer_sources(archive, config, files):
    root = ET.fromstring(read_small(archive, config, 4 * 1024 * 1024))
    if root.tag != "config" or root.find("moduleName") is None:
        raise ValueError("Expected a FOMOD config with moduleName")
    missing = []
    prefix = virtual_path(config.filename)[:-len("fomod/moduleconfig.xml")]
    folders = set()
    for name in files:
        parts = name.split("/")
        folders.update("/".join(parts[:i]) for i in range(1, len(parts)))
    for entry in root.iter():
        if entry.tag in ("file", "folder"):
            source = entry.get("source")
        elif entry.tag in ("image", "moduleImage"):
            source = entry.get("path")
        else:
            continue
        if entry.tag == "folder" and source == "":
            continue  # the installer's archive root
        path = prefix + member_key(source or "")
        if path not in (folders if entry.tag == "folder" else files):
            missing.append(path)
    return sorted(set(missing))


def inspect_zip(path: Path, expected: list[str], catalog: Path | None = None,
                verify_crc: bool = False) -> dict:
    if not path.is_file():
        raise Fo4McpError(ErrorCode.PATH_NOT_FOUND, "Release ZIP not found", {"archive": str(path)})
    try:
        with ZipFile(path) as archive:
            damaged = archive.testzip() if verify_crc else None
            if damaged:
                return ok(dict(archive=str(path), evidence="zip_crc", verdict="fail",
                               crc_verified=False, damaged_member=damaged))
            files = {}
            duplicates = set()
            for item in archive.infolist():
                key = member_key(item.filename)
                if item.is_dir():
                    continue
                if key in files:
                    duplicates.add(key)
                files[key] = item
            missing = sorted({key for name in expected if (key := member_key(name)) not in files})
            configs = [item for key, item in files.items()
                       if key == "fomod/moduleconfig.xml" or key.endswith("/fomod/moduleconfig.xml")]
            missing_sources = {item.filename: installer_sources(archive, item, files) for item in configs}
            external = {}
            # FOMOD can remap destinations at install time. Only resolve ordinary Data layouts here.
            inspected = 0
            if not configs:
                for key, item in files.items():
                    relative = key.removeprefix("data/")
                    if relative.startswith("materials/") and key.endswith((".bgsm", ".bgem")):
                        fields = bgsm_ops.decode(read_small(archive, item, 1024 * 1024))
                    elif relative.startswith("meshes/") and key.endswith(".nif"):
                        fields = nif_ops.shader_paths(read_small(archive, item, 64 * 1024 * 1024))
                    else:
                        continue
                    inspected += 1
                    prefix = key[:-len(relative)]
                    for slot, dep in material_links(fields):
                        if prefix + dep not in files:
                            hit = external.setdefault(dep, {"references": 0, "examples": []})
                            hit["references"] += 1
                            if len(hit["examples"]) < 3:
                                hit["examples"].append({"source": key, "field": slot})
            if catalog is not None:
                with open_catalog(catalog) as db:
                    for dep, hit in external.items():
                        hit["catalog_sources"] = [
                            {"provider": provider, "kind": kind, "file": source}
                            for _, provider, kind, source in providers(db, dep)
                        ]
            errors = bool(not files or missing or duplicates or any(missing_sources.values()))
            return ok(dict(archive=str(path), evidence="zip_directory_and_references",
                           verdict="fail" if errors else "review" if external or len(configs) > 1 else "pass",
                           file_count=len(files), missing_expected=missing, duplicates=sorted(duplicates),
                           fomod_missing_sources=missing_sources, unresolved_loose_references=external,
                           catalog_snapshot=str(catalog) if catalog else None, loose_assets_inspected=inspected,
                           crc_verified=True if verify_crc else None))
    except (ValueError, BadZipFile, ET.ParseError, struct.error, IndexError, KeyError,
            OSError, RuntimeError, NotImplementedError) as exc:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"Cannot inspect release ZIP: {exc}") from exc
