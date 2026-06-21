"""fo4_pack_ba2 tests — console BSArch (tools/xedit/BSArch64.exe) wrapper."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.ba2_pack import fo4_pack_ba2
from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError, ToolBinaryMissingError
from fo4_mcp.manifest import Manifest, ToolEntry

_REPO = Path(__file__).resolve().parents[2]
_BSARCH = _REPO / "tools" / "xedit" / "BSArch64.exe"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _mani() -> Manifest:
    return Manifest(
        tools={"bsarch": ToolEntry(
            name="BSArch", version="0.9c", source="xEdit", asset="",
            binary_path=str(_BSARCH), license="MPL-2.0", raw={},
        )},
        source_path=Path("x"),
    )


def _src_with_file(tmp_path: Path) -> Path:
    """Build a tmp source folder with one small file at a Data/-style path."""
    src = tmp_path / "src"
    probe = src / "meshes" / "test" / "probe.txt"
    probe.parent.mkdir(parents=True)
    probe.write_bytes(b"hi")
    return src


# ---------------- integration: real BSArch ----------------

def test_pack_happy_path(tmp_path):
    if not _BSARCH.exists():
        pytest.skip("BSArch64.exe not present")
    cfg = _cfg(_REPO)  # repo_root so staging/ is writable
    src = _src_with_file(tmp_path)
    out_rel = "staging/ba2-pack-test/probe.ba2"
    try:
        data = fo4_pack_ba2(cfg, _mani(), str(src), out_rel, archive_type="general")["data"]
        assert data["ok"] is True
        out = _REPO / "staging" / "ba2-pack-test" / "probe.ba2"
        assert out.exists() and out.stat().st_size > 0
        # real BA2 magic
        assert out.read_bytes()[:4] == b"BTDX"
    finally:
        shutil.rmtree(_REPO / "staging" / "ba2-pack-test", ignore_errors=True)


def test_pack_backs_up_existing(tmp_path):
    if not _BSARCH.exists():
        pytest.skip("BSArch64.exe not present")
    cfg = _cfg(_REPO)
    src = _src_with_file(tmp_path)
    out_rel = "staging/ba2-pack-test/probe.ba2"
    out = _REPO / "staging" / "ba2-pack-test" / "probe.ba2"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"OLD")  # pre-existing target
        data = fo4_pack_ba2(cfg, _mani(), str(src), out_rel, archive_type="general")["data"]
        assert data["backup_path"] is not None
        assert Path(data["backup_path"]).exists()
    finally:
        shutil.rmtree(_REPO / "staging" / "ba2-pack-test", ignore_errors=True)


# ---------------- pure validation (no binary needed) ----------------

def test_forbidden_output_raises(tmp_path):
    cfg = _cfg(_REPO)
    src = _src_with_file(tmp_path)
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.ba2"
    with pytest.raises(PathForbiddenError):
        fo4_pack_ba2(cfg, _mani(), str(src), forbidden)


def test_missing_source_raises(tmp_path):
    cfg = _cfg(_REPO)
    missing = tmp_path / "does-not-exist"
    with pytest.raises(Fo4McpError):
        fo4_pack_ba2(cfg, _mani(), str(missing), "staging/x.ba2")


def test_bad_archive_type_raises(tmp_path):
    cfg = _cfg(_REPO)
    src = _src_with_file(tmp_path)
    with pytest.raises(Fo4McpError):
        fo4_pack_ba2(cfg, _mani(), str(src), "staging/x.ba2", archive_type="zip")


def test_unresolved_binary_raises(tmp_path):
    cfg = _cfg(_REPO)
    src = _src_with_file(tmp_path)
    bad_mani = Manifest(
        tools={"bsarch": ToolEntry(
            name="BSArch", version="0.9c", source="xEdit", asset="",
            binary_path="TBD", license="MPL-2.0", raw={},
        )},
        source_path=Path("x"),
    )
    with pytest.raises(ToolBinaryMissingError):
        fo4_pack_ba2(cfg, bad_mani, str(src), "staging/x.ba2")
