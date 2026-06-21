"""fo4_build_lod tests — xLODGen argv construction + gating + dry-run.

xLODGen LOD generation is GUI-only (interactive worldspace + Build meshes), so
these tests NEVER launch the binary. They exercise the headless contract:
argv construction (with/without optional paths), output_dir gating, binary
resolution error, and that dry_run does not execute.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp import lod as lod_mod
from fo4_mcp.config import Config
from fo4_mcp.errors import PathForbiddenError, ToolBinaryMissingError
from fo4_mcp.lod import fo4_build_lod

_REPO = Path(__file__).resolve().parents[2]


def _cfg(repo_root: Path, tools_dir: Path | None = None) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None,
        tools_dir=tools_dir or (repo_root / "tools"),
        log_level="INFO", subprocess_timeout=120,
    )


def _fake_exe(tools_dir: Path) -> Path:
    """Create a stand-in xLODGenx64.exe so resolution succeeds without the
    real 34 MB binary (we never execute it)."""
    exe = tools_dir / "xlodgen" / "xLODGen" / "xLODGenx64.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")  # token PE header; never run
    return exe


# ---------------- argv construction ----------------

def test_argv_minimal(tmp_path):
    tools = tmp_path / "tools"
    exe = _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)
    out = fo4_build_lod(cfg, "staging/lod-out", dry_run=True)["data"]

    cmd = out["command"]
    assert cmd[0] == str(exe)
    assert cmd[1] == "-fo4"
    # -o: glued to resolved abs path, no space after colon
    out_abs = (tmp_path / "staging" / "lod-out").resolve()
    assert cmd[2] == f"-o:{out_abs}"
    # no optional path flags present
    assert not any(t.startswith("-d:") for t in cmd)
    assert not any(t.startswith("-p:") for t in cmd)
    assert not any(t.startswith("-m:") for t in cmd)
    # fixed tail order
    assert cmd[-3:] == ["-lodgen", "-autoload", "-autoexit"]
    assert out["dry_run"] is True
    assert out["interactive_step_required"]
    assert "UNVERIFIED" in out["license"]
    assert out["xlodgen_exe"] == str(exe)


def test_argv_with_optional_paths(tmp_path):
    tools = tmp_path / "tools"
    _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)
    out = fo4_build_lod(
        cfg, "staging/lod-out",
        data_path=r"C:\MO2\overwrite\Data",
        plugins_path=r"C:\plugins.txt",
        ini_path=r"C:\inis",
        dry_run=True,
    )["data"]
    cmd = out["command"]
    assert r"-d:C:\MO2\overwrite\Data" in cmd
    assert r"-p:C:\plugins.txt" in cmd
    assert r"-m:C:\inis" in cmd
    # order: -fo4, -o:, optionals, then fixed tail
    assert cmd.index("-d:" + r"C:\MO2\overwrite\Data") < cmd.index("-lodgen")
    assert cmd[-3:] == ["-lodgen", "-autoload", "-autoexit"]


# ---------------- output_dir gating ----------------

def test_staging_output_allowed(tmp_path):
    tools = tmp_path / "tools"
    _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)
    # should not raise
    out = fo4_build_lod(cfg, "staging/lod", dry_run=True)["data"]
    assert out["output_dir"].lower().endswith("staging\\lod") or \
        out["output_dir"].replace("\\", "/").lower().endswith("staging/lod")


def test_steam_data_output_forbidden(tmp_path):
    tools = tmp_path / "tools"
    _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)
    forbidden = r"C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/LOD"
    with pytest.raises(PathForbiddenError):
        fo4_build_lod(cfg, forbidden, dry_run=True)


# ---------------- binary resolution ----------------

def test_missing_binary_raises(tmp_path):
    # tools_dir with no xLODGen exe present
    cfg = _cfg(tmp_path, tools_dir=tmp_path / "empty-tools")
    with pytest.raises(ToolBinaryMissingError):
        fo4_build_lod(cfg, "staging/lod", dry_run=True)


# ---------------- dry_run does not execute ----------------

def test_dry_run_does_not_execute(tmp_path, monkeypatch):
    tools = tmp_path / "tools"
    _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)

    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("run_tool must NOT be called in dry_run")

    monkeypatch.setattr(lod_mod, "run_tool", _boom)
    out = fo4_build_lod(cfg, "staging/lod", dry_run=True)["data"]
    assert called["n"] == 0
    assert "exit_code" not in out  # execute-only fields absent
    # dry-run must not create the output dir
    assert not (tmp_path / "staging" / "lod").exists()


def test_execute_path_calls_run_tool(tmp_path, monkeypatch):
    """dry_run=False routes through run_tool (stubbed — no real launch)."""
    tools = tmp_path / "tools"
    exe = _fake_exe(tools)
    cfg = _cfg(tmp_path, tools_dir=tools)

    from fo4_mcp.subprocess_wrap import ToolResult

    seen = {}

    def _fake_run(binary, args, **k):
        seen["binary"] = str(binary)
        seen["args"] = list(args)
        return ToolResult(cmd=[str(binary), *args], exit_code=0,
                          stdout="done", stderr="", timed_out=False)

    monkeypatch.setattr(lod_mod, "run_tool", _fake_run)
    out = fo4_build_lod(cfg, "staging/lod", dry_run=False)["data"]
    assert seen["binary"] == str(exe)
    assert seen["args"][0] == "-fo4"
    assert out["exit_code"] == 0
    assert out["ok"] is True
    # execute path creates the gated output dir
    assert (tmp_path / "staging" / "lod").exists()
