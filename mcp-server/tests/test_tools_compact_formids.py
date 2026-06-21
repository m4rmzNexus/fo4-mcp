"""fo4_compact_formids tests — SAFE GATING + planning for ESL compaction.

The real "Compact FormIDs for ESL" is a GUI context-menu action and is NOT
exercised here (it is irreversible + machine-locked). We unit-test the gates,
the .bak-before-write ordering, the dry-run (no-execute) path, and the
constructed argv. A tiny fixture .esp copy in a tmp dir stands in for a plugin.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.compact_formids import _XEDIT_CANDIDATES, fo4_compact_formids
from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _make_plugin(tmp_path: Path, name: str = "MyMod.esp") -> Path:
    """A tmp staging-style plugin (writable per check_write)."""
    staging = tmp_path / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    p = staging / name
    p.write_bytes(b"TES4\x00\x00\x00\x00fake-esp-bytes")
    return p


def _fake_xedit(tmp_path: Path) -> None:
    """Drop a fake xEdit binary so _resolve_xedit succeeds."""
    xedit_dir = tmp_path / "tools" / "xedit"
    xedit_dir.mkdir(parents=True, exist_ok=True)
    (xedit_dir / _XEDIT_CANDIDATES[0]).write_bytes(b"MZ")  # FO4Edit64.exe


# ---------------- refusal gates ----------------

def test_refuses_without_confirm(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    p = _make_plugin(tmp_path)
    data = fo4_compact_formids(cfg, str(p))["data"]  # confirm defaults False
    assert data["refused"] is True
    assert "confirm=True" in data["reason"]
    # nothing created
    assert not p.with_suffix(p.suffix + ".bak").exists()


def test_refuses_without_saves_backed_up(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    p = _make_plugin(tmp_path)
    data = fo4_compact_formids(cfg, str(p), confirm=True)["data"]
    assert data["refused"] is True
    assert "fo4_backup_saves" in data["reason"]
    assert not p.with_suffix(p.suffix + ".bak").exists()


# ---------------- dry run (default) ----------------

def test_dry_run_does_not_execute_or_bak(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    p = _make_plugin(tmp_path)
    out = fo4_compact_formids(cfg, str(p), confirm=True, saves_backed_up=True)
    data = out["data"]
    assert data["dry_run"] is True
    assert "plan" in data
    assert data["plan"]["irreversible"] is True
    assert data["plan"]["save_breaking"] is True
    assert "IRREVERSIBLE" in data["warning"]
    # dry run: NO .bak, plugin untouched
    assert not Path(data["bak_path"]).exists()
    assert p.read_bytes().startswith(b"TES4")


def test_dry_run_constructs_argv(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    p = _make_plugin(tmp_path)
    data = fo4_compact_formids(cfg, str(p), confirm=True, saves_backed_up=True)["data"]
    cmd = data["xedit_cmd"]
    assert cmd[0].endswith(_XEDIT_CANDIDATES[0])  # binary first
    assert "-fo4" in cmd
    assert f"-autoload:{p.name}" in cmd
    assert str(p) in cmd
    assert all(tok for tok in cmd)  # no empty tokens


# ---------------- execute path: .bak BEFORE any destructive step ----------------

def test_execute_creates_bak_before_write(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    p = _make_plugin(tmp_path)
    original = p.read_bytes()
    out = fo4_compact_formids(
        cfg, str(p), confirm=True, saves_backed_up=True, dry_run=False
    )
    data = out["data"]
    bak = Path(data["bak_path"])
    # .bak exists and is a faithful copy of the original
    assert bak.exists()
    assert bak.read_bytes() == original
    # honest about not auto-performing the GUI action
    assert data["executed"] is False
    assert data["automatable"] == "gui-required"
    assert "NOT confirmed" in data["note"]


# ---------------- path / input validation ----------------

def test_forbidden_plugin_path_raises(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/MyMod.esp"
    with pytest.raises(PathForbiddenError):
        fo4_compact_formids(cfg, forbidden, confirm=True, saves_backed_up=True)


def test_missing_plugin_raises(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    with pytest.raises(Fo4McpError):
        fo4_compact_formids(cfg, str(tmp_path / "staging" / "nope.esp"), confirm=True)


def test_non_plugin_suffix_raises(tmp_path):
    _fake_xedit(tmp_path)
    cfg = _cfg(tmp_path)
    bad = tmp_path / "staging" / "notes.txt"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_bytes(b"x")
    with pytest.raises(Fo4McpError):
        fo4_compact_formids(cfg, str(bad), confirm=True)
