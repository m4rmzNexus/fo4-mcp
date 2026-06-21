"""fo4_lint_engine_config tests — pure ruleset + file/double-patch checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.tools import _lint_engine_config, fo4_lint_engine_config

_REPO = Path(__file__).resolve().parents[2]
_ADDICTOL = _REPO / "tools" / "addictol" / "f4se" / "plugins" / "Addictol.toml"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


# ---------------- pure ruleset ----------------

def test_lint_clean_when_consistent():
    data = {"Patches": {"bScaleformAllocator": True},
            "Additional": {"uScaleformPageSize": 256, "uScaleformHeapSize": 512}}
    assert _lint_engine_config(data) == []


def test_lint_flags_noop_setting():
    data = {"Fixes": {"bBakaMaxPapyrusOps": False},
            "Additional": {"nMaxPapyrusOpsPerFrame": 500}}
    f = _lint_engine_config(data)
    assert any(x["rule"] == "nMaxPapyrusOpsPerFrame->bBakaMaxPapyrusOps" for x in f)


def test_lint_scaleform_not_multiple_of_8():
    data = {"Patches": {"bScaleformAllocator": True}, "Additional": {"uScaleformPageSize": 100}}
    f = _lint_engine_config(data)
    assert any("multiple of 8" in x["message"] for x in f)


def test_lint_scaleform_out_of_range():
    data = {"Patches": {"bScaleformAllocator": True}, "Additional": {"uScaleformHeapSize": 4096}}
    f = _lint_engine_config(data)
    assert any("out of range" in x["message"] for x in f)


def test_lint_maxstdio_over_limit():
    data = {"Fixes": {"nMaxStdIO": 9000}}
    f = _lint_engine_config(data)
    assert any(x["rule"] == "nMaxStdIO" for x in f)
    # -1 (auto) is fine
    assert _lint_engine_config({"Fixes": {"nMaxStdIO": -1}}) == []


def test_lint_bool_setting_off_with_flag_off_is_silent():
    # a disabled setting with its disabled flag should NOT warn
    data = {"Patches": {"bMemoryManager": False}, "Additional": {"bUseNewRedistributable": False}}
    assert _lint_engine_config(data) == []


# ---------------- file + double-patch ----------------

def test_real_addictol_toml_is_clean():
    if not _ADDICTOL.exists():
        pytest.skip("Addictol.toml not extracted")
    cfg = _cfg(_REPO)
    data = fo4_lint_engine_config(cfg, str(_ADDICTOL))["data"]
    assert data["config_kind"] == "addictol"
    assert data["verdict"] == "clean"
    assert data["error_count"] == 0


def test_double_patch_detected(tmp_path):
    cfg = _cfg(tmp_path)
    toml = tmp_path / "Addictol.toml"
    toml.write_text("[Patches]\nbMemoryManager=true\n", encoding="utf-8")
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "Buffout4.dll").write_bytes(b"x")
    (plugins / "Addictol.dll").write_bytes(b"x")
    (plugins / "UnrelatedMod.dll").write_bytes(b"x")
    data = fo4_lint_engine_config(cfg, str(toml), plugins_dir=str(plugins))["data"]
    assert data["verdict"] == "conflict"
    assert "Buffout4.dll" in data["double_patch_plugins"]
    assert "UnrelatedMod.dll" not in data["double_patch_plugins"]


def test_missing_config_raises(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(Fo4McpError):
        fo4_lint_engine_config(cfg, str(tmp_path / "nope.toml"))


def test_invalid_toml_raises(tmp_path):
    cfg = _cfg(tmp_path)
    bad = tmp_path / "bad.toml"
    bad.write_text("this is = = not valid toml [[[", encoding="utf-8")
    with pytest.raises(Fo4McpError):
        fo4_lint_engine_config(cfg, str(bad))
