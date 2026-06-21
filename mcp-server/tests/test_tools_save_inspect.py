"""fo4_inspect_save tests — pure-Python FO4 .fos save parser (read-only).

The core test builds a synthetic minimal UNCOMPRESSED .fos byte blob from
scratch (matching the layout in fo4_mcp/save_inspect.py, derived from
ReSaver's Header.java / ESS.java / PluginInfo.java) and round-trips it
through the pure helper. No real save is required.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import ErrorCode, Fo4McpError
from fo4_mcp.save_inspect import FO4_MAGIC, _parse_fos_header, fo4_inspect_save


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _ws(s: str) -> bytes:
    """u16 length-prefixed string (wstring)."""
    raw = s.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def _build_fos(
    *,
    version: int = 11,
    save_number: int = 7,
    player_name: str = "TestSole",
    player_level: int = 12,
    player_location: str = "Sanctuary",
    game_date: str = "Day 3",
    race: str = "HumanRace",
    sex: int = 0,
    cur_exp: float = 100.0,
    lvlup_exp: float = 250.0,
    filetime: int = 132000000000000000,
    shot_w: int = 1,
    shot_h: int = 1,
    form_version: int = 74,
    game_version: str = "1.10.163.0",
    plugins: list[str] | None = None,
    light_plugins: list[str] | None = None,
) -> bytes:
    """Construct a faithful minimal uncompressed FO4 .fos byte blob."""
    if plugins is None:
        plugins = ["Fallout4.esm", "MyMod.esp"]
    if light_plugins is None:
        light_plugins = ["MyLite.esl"]

    # Header block (the part counted by headerSize) — everything from
    # `version` through `shotHeight`.
    header_block = b""
    header_block += struct.pack("<I", version)
    header_block += struct.pack("<I", save_number)
    header_block += _ws(player_name)
    header_block += struct.pack("<I", player_level)
    header_block += _ws(player_location)
    header_block += _ws(game_date)
    header_block += _ws(race)
    header_block += struct.pack("<H", sex)
    header_block += struct.pack("<f", cur_exp)
    header_block += struct.pack("<f", lvlup_exp)
    header_block += struct.pack("<Q", filetime)
    header_block += struct.pack("<I", shot_w)
    header_block += struct.pack("<I", shot_h)

    out = FO4_MAGIC
    out += struct.pack("<I", len(header_block))
    out += header_block

    # Screenshot: shot_w * shot_h * 4 (RGBA) bytes.
    out += b"\x00" * (shot_w * shot_h * 4)

    # Body (uncompressed): formVersion, gameVersion, plugin info.
    out += struct.pack("<B", form_version)
    out += _ws(game_version)

    # PluginInfo: pluginInfoSize(u32) + numberOfFull(u8) + full plugins
    #             + (if ESL) numberOfLite(u16) + lite plugins.
    plugin_block = struct.pack("<B", len(plugins))
    for name in plugins:
        plugin_block += _ws(name)
    include_esl = form_version >= 68
    if include_esl:
        plugin_block += struct.pack("<H", len(light_plugins))
        for name in light_plugins:
            plugin_block += _ws(name)
    # pluginInfoSize in ReSaver = calculateSize() - 4 (it excludes its own u32).
    out += struct.pack("<I", len(plugin_block))
    out += plugin_block

    return out


# ---- Test 1: pure helper happy path ------------------------------------------

def test_parse_header_happy_path():
    blob = _build_fos()
    h = _parse_fos_header(blob)

    assert h["magic_ok"] is True
    assert h["save_version"] == 11
    assert h["save_number"] == 7
    assert h["player_name"] == "TestSole"
    assert h["player_level"] == 12
    assert h["player_location"] == "Sanctuary"
    assert h["game_date"] == "Day 3"
    assert h["race"] == "HumanRace"
    assert h["sex"] == 0
    assert h["screenshot"] == {"width": 1, "height": 1}
    assert h["filetime"] == 132000000000000000
    assert h["compression_type"] == "none"
    assert h["form_version"] == 74
    assert h["game_version"] == "1.10.163.0"
    assert h["plugin_count"] == 2
    assert h["plugins"] == ["Fallout4.esm", "MyMod.esp"]
    assert h["light_plugin_count"] == 1
    assert h["light_plugins"] == ["MyLite.esl"]


def test_parse_header_pre_esl_form_version():
    """form_version < 68 => no light plugin table, with an explanatory note."""
    blob = _build_fos(form_version=60, light_plugins=[])
    h = _parse_fos_header(blob)
    assert h["form_version"] == 60
    assert h["plugin_count"] == 2
    assert h["light_plugin_count"] is None
    assert h["light_plugins"] is None
    assert any("no ESL" in n for n in h["notes"])


def test_inspect_save_happy_path_via_file(tmp_path):
    save = tmp_path / "Save7.fos"
    save.write_bytes(_build_fos())
    res = fo4_inspect_save(_cfg(tmp_path), str(save))
    assert res["ok"] is True
    data = res["data"]
    assert data["player_name"] == "TestSole"
    assert data["save_path"] == str(save)
    assert data["plugins"] == ["Fallout4.esm", "MyMod.esp"]


# ---- Test 2: bad magic -------------------------------------------------------

def test_parse_header_bad_magic_raises_valueerror():
    with pytest.raises(ValueError):
        _parse_fos_header(b"NOPE_NOT_A_SAVE_FILE_AT_ALL")


def test_inspect_save_bad_magic_raises(tmp_path):
    bad = tmp_path / "bad.fos"
    bad.write_bytes(b"NOPE" + b"\x00" * 64)
    with pytest.raises(Fo4McpError) as exc:
        fo4_inspect_save(_cfg(tmp_path), str(bad))
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT


# ---- Test 3: missing file ----------------------------------------------------

def test_inspect_save_missing_file_raises(tmp_path):
    with pytest.raises(Fo4McpError) as exc:
        fo4_inspect_save(_cfg(tmp_path), str(tmp_path / "does_not_exist.fos"))
    assert exc.value.code == ErrorCode.PATH_NOT_FOUND


def test_inspect_save_f4se_cosave_rejected(tmp_path):
    cosave = tmp_path / "Save7.f4se"
    cosave.write_bytes(b"\x00" * 16)
    with pytest.raises(Fo4McpError) as exc:
        fo4_inspect_save(_cfg(tmp_path), str(cosave))
    assert exc.value.code == ErrorCode.INVALID_ARGUMENT
    assert "co-save" in exc.value.message


# ---- Test 4: real save integration (skip if none) ----------------------------

def _find_real_save() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "My Games" / "Fallout4" / "Saves",
        Path("C:/Modding/staging/save-archive"),
    ]
    for root in candidates:
        if root.is_dir():
            for fos in sorted(root.rglob("*.fos")):
                return fos
    return None


def test_inspect_real_save_if_present():
    sample = _find_real_save()
    if sample is None:
        pytest.skip("no sample .fos found")
    res = fo4_inspect_save(_cfg(Path("C:/Modding")), str(sample))
    assert res["ok"] is True
    data = res["data"]
    assert data["magic_ok"] is True
    assert data["save_version"] > 0
    # player_name is always a str; it can legitimately be empty for an
    # early-game autosave taken before the character is named.
    assert isinstance(data["player_name"], str)
    # For an uncompressed FO4 save the body parses too: plugin list present.
    assert isinstance(data["plugins"], list)
    assert "Fallout4.esm" in data["plugins"]
