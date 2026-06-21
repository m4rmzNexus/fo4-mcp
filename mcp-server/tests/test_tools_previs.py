"""fo4_build_previs tests — CK precombine/previs CLI argv construction + gating.

No real CK run: CK is long/machine-locked. We test argv construction, the
"full" pipeline ordering, validation errors, binary resolution, and that the
dry_run default returns commands WITHOUT executing (run_tool not called), while
dry_run=False DOES call run_tool.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fo4_mcp.subprocess_wrap as subprocess_wrap
from fo4_mcp.config import Config
from fo4_mcp.errors import ErrorCode, Fo4McpError, ToolBinaryMissingError
from fo4_mcp.previs import fo4_build_previs
from fo4_mcp.subprocess_wrap import ToolResult

_REPO = Path(__file__).resolve().parents[2]


def _cfg(tmp_path: Path, *, install: Path | None) -> Config:
    return Config(
        repo_root=tmp_path, fo4_install_dir=install, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=tmp_path / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _install_with_ck(tmp_path: Path) -> Path:
    """Build a fake FO4 install dir with a CreationKit.exe present."""
    install = tmp_path / "Fallout 4"
    install.mkdir(parents=True)
    (install / "CreationKit.exe").write_bytes(b"MZ")
    return install


def _ck_exe(install: Path) -> str:
    return str((install / "CreationKit.exe").resolve())


# ---------------- argv construction ----------------

def test_precombined_argv(tmp_path):
    install = _install_with_ck(tmp_path)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="precombined")["data"]
    assert data["dry_run"] is True
    assert data["commands"] == [
        [_ck_exe(install), "-GeneratePrecombined:MyMod.esp", "clean", "all"]
    ]
    assert data["warning"]


def test_previs_argv_filtered(tmp_path):
    install = _install_with_ck(tmp_path)
    data = fo4_build_previs(
        _cfg(tmp_path, install=install), "MyMod.esp", step="previs", filter="filtered"
    )["data"]
    assert data["commands"] == [
        [_ck_exe(install), "-GeneratePreVisData:MyMod.esp", "filtered", "all"]
    ]


def test_compress_psg_no_filter_area(tmp_path):
    install = _install_with_ck(tmp_path)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="compress_psg")["data"]
    assert data["commands"] == [[_ck_exe(install), "-CompressPSG:MyMod.esp"]]


def test_build_cdx_no_filter_area(tmp_path):
    install = _install_with_ck(tmp_path)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="build_cdx")["data"]
    assert data["commands"] == [[_ck_exe(install), "-BuildCDX:MyMod.esp"]]


def test_full_pipeline_ordering(tmp_path):
    install = _install_with_ck(tmp_path)
    ck = _ck_exe(install)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="full")["data"]
    assert data["commands"] == [
        [ck, "-GeneratePrecombined:MyMod.esp", "clean", "all"],
        [ck, "-CompressPSG:MyMod.esp"],
        [ck, "-BuildCDX:MyMod.esp"],
        [ck, "-GeneratePreVisData:MyMod.esp", "clean", "all"],
    ]


def test_esm_plugin_accepted(tmp_path):
    install = _install_with_ck(tmp_path)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "Master.esm")["data"]
    assert data["commands"][0][1] == "-GeneratePrecombined:Master.esm"


# ---------------- validation errors ----------------

def test_bad_step_raises(tmp_path):
    install = _install_with_ck(tmp_path)
    with pytest.raises(Fo4McpError) as ei:
        fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="bogus")
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


def test_bad_filter_raises(tmp_path):
    install = _install_with_ck(tmp_path)
    with pytest.raises(Fo4McpError) as ei:
        fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", filter="dirty")
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


def test_bad_plugin_suffix_raises(tmp_path):
    install = _install_with_ck(tmp_path)
    with pytest.raises(Fo4McpError) as ei:
        fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.ba2")
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


def test_no_install_dir_raises(tmp_path):
    with pytest.raises(Fo4McpError) as ei:
        fo4_build_previs(_cfg(tmp_path, install=None), "MyMod.esp")
    assert ei.value.code == ErrorCode.ENV_FO4_NOT_DETECTED


def test_missing_ck_binary_raises(tmp_path):
    install = tmp_path / "Fallout 4"
    install.mkdir(parents=True)  # no CreationKit.exe inside
    with pytest.raises(ToolBinaryMissingError):
        fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp")


# ---------------- dry_run gating (run_tool not called) ----------------

def test_dry_run_does_not_call_run_tool(tmp_path, monkeypatch):
    install = _install_with_ck(tmp_path)
    called = {"n": 0}

    def _spy(*a, **k):
        called["n"] += 1
        raise AssertionError("run_tool must NOT be called in dry_run")

    monkeypatch.setattr(subprocess_wrap, "run_tool", _spy)
    data = fo4_build_previs(_cfg(tmp_path, install=install), "MyMod.esp", step="full")["data"]
    assert data["dry_run"] is True
    assert called["n"] == 0


def test_execute_runs_ck_per_command(tmp_path, monkeypatch):
    """dry_run=False routes each CK step through the MO2-VFS launcher (run_ck_via_mo2)."""
    from fo4_mcp import ck_run
    install = _install_with_ck(tmp_path)
    calls: list[list[str]] = []

    def _fake(cfg, ck_args, **kwargs):
        calls.append(list(ck_args))
        return {"launched": True, "exited": True, "timed_out": False, "duration_s": 1.0,
                "overwrite_dir": "ow", "overwrite_new": ["CombinedObjects.esp"],
                "ckpe_log_tail": "SAVE COMPLETE."}

    monkeypatch.setattr(ck_run, "run_ck_via_mo2", _fake)
    data = fo4_build_previs(
        _cfg(tmp_path, install=install), "MyMod.esp", step="full", dry_run=False
    )["data"]
    assert data["dry_run"] is False
    assert data["via"] == "mo2-vfs"
    assert data["ok"] is True
    assert len(calls) == 4  # one MO2-VFS CK launch per pipeline step
    assert len(data["results"]) == 4
    assert all(r["exited"] and not r["timed_out"] for r in data["results"])


def test_execute_propagates_ck_failure(tmp_path, monkeypatch):
    """A timed-out (hung-then-killed) CK run surfaces ok=False."""
    from fo4_mcp import ck_run
    install = _install_with_ck(tmp_path)

    def _fail(cfg, ck_args, **kwargs):
        return {"launched": True, "exited": False, "timed_out": True, "duration_s": 600.0,
                "overwrite_dir": "ow", "overwrite_new": [], "ckpe_log_tail": ""}

    monkeypatch.setattr(ck_run, "run_ck_via_mo2", _fail)
    data = fo4_build_previs(
        _cfg(tmp_path, install=install), "MyMod.esp", step="precombined", dry_run=False
    )["data"]
    assert data["ok"] is False
    assert data["results"][0]["timed_out"] is True
