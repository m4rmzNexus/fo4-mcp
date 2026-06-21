"""fo4_backup_saves tests — read-only save archival to staging/."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.tools import fo4_backup_saves


def _cfg(repo_root: Path, user_docs: Path | None) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=user_docs,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _make_saves(docs: Path) -> Path:
    saves = docs / "Saves"
    saves.mkdir(parents=True)
    (saves / "Save1.fos").write_bytes(b"FO4_SAVE_1")
    (saves / "Save1.f4se").write_bytes(b"COSAVE_1")
    (saves / "Save2.fos").write_bytes(b"FO4_SAVE_2")
    (saves / "notes.txt").write_text("ignore me", encoding="utf-8")  # must be skipped
    return saves


def test_backup_copies_saves_only(tmp_path):
    docs = tmp_path / "docs"
    _make_saves(docs)
    cfg = _cfg(tmp_path, docs)
    data = fo4_backup_saves(cfg)["data"]
    assert data["save_count"] == 2
    assert data["cosave_count"] == 1
    assert data["file_count"] == 3  # .txt excluded
    arch = Path(data["archive_dir"])
    assert arch.exists()
    assert (arch / "Save1.fos").exists() and (arch / "Save1.f4se").exists()
    assert not (arch / "notes.txt").exists()
    assert str(arch).replace("\\", "/").find("/staging/save-archive/") != -1


def test_backup_label_in_dirname(tmp_path):
    docs = tmp_path / "docs"
    _make_saves(docs)
    cfg = _cfg(tmp_path, docs)
    data = fo4_backup_saves(cfg, label="pre-compaction")["data"]
    assert Path(data["archive_dir"]).name.endswith("-pre-compaction")


def test_backup_no_user_docs_raises(tmp_path):
    cfg = _cfg(tmp_path, None)
    with pytest.raises(Fo4McpError):
        fo4_backup_saves(cfg)


def test_backup_missing_saves_dir_raises(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    cfg = _cfg(tmp_path, docs)
    with pytest.raises(Fo4McpError):
        fo4_backup_saves(cfg)


def test_backup_forbidden_dest_raises(tmp_path):
    docs = tmp_path / "docs"
    _make_saves(docs)
    cfg = _cfg(tmp_path, docs)
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/saves"
    with pytest.raises(PathForbiddenError):
        fo4_backup_saves(cfg, dest_dir=forbidden)
