"""fo4_read_load_order unit tests.

Hermetic: synthetic Config pointed at tmp_path; no real MO2 / game install.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.tools import (
    _classify_plugin,
    _light_flag_from_path,
    _mo2_base_directory,
    _mo2_selected_profile,
    _parse_plugins_txt,
    fo4_read_load_order,
)


def _tes4(flags: int) -> bytes:
    """Minimal TES4 record header: type[4] + dataSize u32 + flags u32 (+ pad)."""
    return b"TES4" + (0).to_bytes(4, "little") + flags.to_bytes(4, "little") + b"\x00" * 12


def _cfg(tmp_path: Path, *, localappdata=None, mo2=None, fo4=None) -> Config:
    return Config(
        repo_root=tmp_path,
        fo4_install_dir=fo4,
        fo4_user_docs=None,
        fo4_localappdata=localappdata,
        mo2_instance_dir=mo2,
        tools_dir=tmp_path / "tools",
        log_level="INFO",
        subprocess_timeout=120,
    )


# ---- pure helpers ----

def test_parse_plugins_txt_enabled_disabled_comments():
    body = "# header comment\n*Enabled.esp\nDisabled.esp\n\n*Another.esl\n"
    assert _parse_plugins_txt(body) == [
        ("Enabled.esp", True),
        ("Disabled.esp", False),
        ("Another.esl", True),
    ]


def test_classify_plugin_types():
    assert _classify_plugin("X.esl") == {"type": "esl", "light": True}
    assert _classify_plugin("X.esm") == {"type": "esm", "light": False}
    assert _classify_plugin("X.esp") == {"type": "esp", "light": None}
    assert _classify_plugin("README.txt")["type"] == "other"


def test_mo2_selected_profile_bytearray():
    assert _mo2_selected_profile("[General]\nselected_profile=@ByteArray(default-ae)\n") == "default-ae"


def test_mo2_selected_profile_plain():
    assert _mo2_selected_profile("selected_profile=Default\n") == "Default"


def test_mo2_selected_profile_missing():
    assert _mo2_selected_profile("[General]\ngameName=Fallout 4\n") is None


# ---- vanilla mode ----

def test_vanilla_reads_plugins_txt(tmp_path: Path):
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*MyMod.esp\nDisabledMod.esp\n*Light.esl\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, localappdata=lad))
    assert res["ok"]
    data = res["data"]
    assert data["source"] == "vanilla"
    names = [p["name"] for p in data["plugins"]]
    assert names == ["MyMod.esp", "DisabledMod.esp", "Light.esl"]
    assert data["count"] == {"total": 3, "enabled": 2}
    light = next(p for p in data["plugins"] if p["name"] == "Light.esl")
    assert light["type"] == "esl" and light["light"] is True


def test_vanilla_missing_plugins_txt_warns(tmp_path: Path):
    lad = tmp_path / "lad"
    lad.mkdir()
    res = fo4_read_load_order(_cfg(tmp_path, localappdata=lad))
    data = res["data"]
    assert data["plugins"] == []
    assert any("not found" in w for w in data["warnings"])


def test_no_localappdata_raises(tmp_path: Path):
    with pytest.raises(Fo4McpError):
        fo4_read_load_order(_cfg(tmp_path))


# ---- base masters + CC ----

def test_base_masters_prepended_when_install_present(tmp_path: Path):
    fo4 = tmp_path / "fo4"
    (fo4 / "Data").mkdir(parents=True)
    (fo4 / "Data" / "Fallout4.esm").write_text("x", encoding="utf-8")
    (fo4 / "Data" / "DLCRobot.esm").write_text("x", encoding="utf-8")
    (fo4 / "Fallout4.ccc").write_text("ccBGSFO4001-PipBoy(Black).esl\n", encoding="utf-8")
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*MyMod.esp\n*ccBGSFO4001-PipBoy(Black).esl\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, localappdata=lad, fo4=fo4))
    data = res["data"]
    names = [p["name"] for p in data["plugins"]]
    assert names[0] == "Fallout4.esm"
    assert names[1] == "DLCRobot.esm"
    assert all(p["implicit_base"] for p in data["plugins"][:2])
    cc = next(p for p in data["plugins"] if "PipBoy" in p["name"])
    assert cc["cc"] is True


# ---- MO2 mode ----

def _make_mo2(tmp_path: Path, profile: str, plugins_body: str) -> Path:
    inst = tmp_path / "mo2"
    (inst / "profiles" / profile).mkdir(parents=True)
    (inst / "ModOrganizer.ini").write_text(
        f"[General]\nselected_profile=@ByteArray({profile})\n", encoding="utf-8"
    )
    (inst / "profiles" / profile / "plugins.txt").write_text(plugins_body, encoding="utf-8")
    return inst


def test_mo2_mode_reads_profile_plugins(tmp_path: Path):
    inst = _make_mo2(tmp_path, "default-ae", "*ModFromMO2.esp\nOff.esp\n")
    res = fo4_read_load_order(_cfg(tmp_path, mo2=inst))
    data = res["data"]
    assert data["source"] == "mo2"
    assert data["active_profile"] == "default-ae"
    assert [p["name"] for p in data["plugins"]] == ["ModFromMO2.esp", "Off.esp"]


def test_mo2_not_onboarded_falls_back_to_vanilla(tmp_path: Path):
    """Portable extracted but no ModOrganizer.ini -> vanilla fallback + warn."""
    inst = tmp_path / "mo2-bare"
    inst.mkdir()
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*Vanilla.esp\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, mo2=inst, localappdata=lad))
    data = res["data"]
    assert data["source"] == "vanilla"
    assert any("not an onboarded instance" in w for w in data["warnings"])
    assert [p["name"] for p in data["plugins"]] == ["Vanilla.esp"]


def test_mo2_base_directory_parse():
    """base_directory may be plain or @ByteArray, with INI-escaped backslashes."""
    assert _mo2_base_directory(
        "[Settings]\nbase_directory=C:\\\\Modding\\\\tools\\\\mo2\\\\portable-fo4-agentic\n"
    ) == "C:\\Modding\\tools\\mo2\\portable-fo4-agentic"
    assert _mo2_base_directory("[Settings]\nbase_directory=@ByteArray(D:\\\\inst)\n") == "D:\\inst"
    assert _mo2_base_directory("[General]\ngameName=Fallout 4\n") is None


def test_mo2_split_base_directory_reads_profile(tmp_path: Path):
    """Real portable layout: ModOrganizer.ini in the exe dir, but mods/ and
    profiles/ live under a separate base_directory. The tool must follow it."""
    inst = tmp_path / "mo2-exe"
    inst.mkdir()
    base = tmp_path / "mo2-data"
    (base / "profiles" / "default-ae").mkdir(parents=True)
    (base / "profiles" / "default-ae" / "plugins.txt").write_text(
        "*SplitMod.esp\n", encoding="utf-8"
    )
    # base_directory written the way MO2 escapes it (doubled backslashes)
    base_escaped = str(base).replace("\\", "\\\\")
    (inst / "ModOrganizer.ini").write_text(
        f"[General]\nselected_profile=@ByteArray(default-ae)\n"
        f"[Settings]\nbase_directory={base_escaped}\n",
        encoding="utf-8",
    )
    res = fo4_read_load_order(_cfg(tmp_path, mo2=inst))
    data = res["data"]
    assert data["source"] == "mo2"
    assert data["active_profile"] == "default-ae"
    assert data["plugins_path"] == str(base / "profiles" / "default-ae" / "plugins.txt")
    assert [p["name"] for p in data["plugins"]] == ["SplitMod.esp"]


# ---- real light-flag (TES4 header) upgrade ----

def test_light_flag_from_path_reads_bit(tmp_path: Path):
    light = tmp_path / "light.esp"
    light.write_bytes(_tes4(0x0200))
    plain = tmp_path / "plain.esp"
    plain.write_bytes(_tes4(0x0000))
    notplugin = tmp_path / "x.esp"
    notplugin.write_bytes(b"NOPE")
    assert _light_flag_from_path(light) is True
    assert _light_flag_from_path(plain) is False
    assert _light_flag_from_path(notplugin) is None
    assert _light_flag_from_path(tmp_path / "missing.esp") is None


def test_esl_flagged_esp_detected_from_header(tmp_path: Path):
    """An ESL-flagged .esp in Data is reported light=True (not the .esp guess)."""
    fo4 = tmp_path / "fo4"
    (fo4 / "Data").mkdir(parents=True)
    (fo4 / "Data" / "LightEsp.esp").write_bytes(_tes4(0x0200))
    (fo4 / "Data" / "PlainEsp.esp").write_bytes(_tes4(0x0000))
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*LightEsp.esp\n*PlainEsp.esp\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, localappdata=lad, fo4=fo4))
    data = res["data"]
    light = next(p for p in data["plugins"] if p["name"] == "LightEsp.esp")
    plain = next(p for p in data["plugins"] if p["name"] == "PlainEsp.esp")
    assert light["light"] is True and light["light_source"] == "header"
    assert light.get("esl_flagged_esp") is True
    assert plain["light"] is False and plain["light_source"] == "header"
    assert "esl_flagged_esp" not in plain


def test_unresolved_plugin_falls_back_to_extension(tmp_path: Path):
    """No file on disk -> light stays the filename heuristic, source=extension."""
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*Ghost.esp\n*Ghost.esl\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, localappdata=lad))
    data = res["data"]
    esp = next(p for p in data["plugins"] if p["name"] == "Ghost.esp")
    esl = next(p for p in data["plugins"] if p["name"] == "Ghost.esl")
    assert esp["light"] is None and esp["light_source"] == "extension"
    assert esl["light"] is True and esl["light_source"] == "extension"


def test_mo2_mods_dir_resolves_light_flag(tmp_path: Path):
    """Plugin physically in an MO2 mod folder gets its real flag read."""
    inst = _make_mo2(tmp_path, "default-ae", "*ModLight.esp\n")
    # _make_mo2 writes no base_directory, so the instance dir is the data root.
    mods = inst / "mods" / "SomeMod"
    mods.mkdir(parents=True)
    (mods / "ModLight.esp").write_bytes(_tes4(0x0200))
    res = fo4_read_load_order(_cfg(tmp_path, mo2=inst))
    data = res["data"]
    p = next(x for x in data["plugins"] if x["name"] == "ModLight.esp")
    assert p["light"] is True and p["light_source"] == "header"


def test_mo2_profile_missing_plugins_falls_back(tmp_path: Path):
    inst = tmp_path / "mo2"
    inst.mkdir()
    (inst / "ModOrganizer.ini").write_text(
        "[General]\nselected_profile=@ByteArray(ghost)\n", encoding="utf-8"
    )
    lad = tmp_path / "lad"
    lad.mkdir()
    (lad / "plugins.txt").write_text("*Vanilla.esp\n", encoding="utf-8")
    res = fo4_read_load_order(_cfg(tmp_path, mo2=inst, localappdata=lad))
    data = res["data"]
    assert data["source"] == "vanilla"
    assert any("no usable profile" in w for w in data["warnings"])
