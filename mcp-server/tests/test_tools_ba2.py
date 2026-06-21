"""fo4_ba2_version_patch tests — pure header rewrite, no external tool."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.tools import _patch_ba2_version_bytes, fo4_ba2_version_patch

_REPO = Path(__file__).resolve().parents[2]
_HUD_BA2 = _REPO / "tools" / "hudframework" / "HUDFramework - Main.ba2"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _fake_ba2(version: int, btype: bytes = b"GNRL") -> bytes:
    # magic | version u32 | type | 12 bytes of plausible header tail
    return b"BTDX" + struct.pack("<I", version) + btype + (b"\x00" * 12)


# ---------------- pure helper ----------------

def test_patch_bytes_flips_version():
    patched, old, btype = _patch_ba2_version_bytes(_fake_ba2(8), 1)
    assert old == 8 and btype == "GNRL"
    assert struct.unpack_from("<I", patched, 4)[0] == 1
    # body beyond the version field is untouched
    assert patched[8:] == _fake_ba2(8)[8:]


def test_patch_bytes_rejects_non_ba2():
    with pytest.raises(ValueError):
        _patch_ba2_version_bytes(b"NOPE" + b"\x00" * 12, 1)


# ---------------- tool: file round-trip ----------------

def test_version_patch_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.ba2"
    src.write_bytes(_fake_ba2(8))
    out = "staging/patched.ba2"
    data = fo4_ba2_version_patch(cfg, str(src), out, target_version=1)["data"]
    assert data["source_version"] == 8 and data["target_version"] == 1
    assert data["archive_type"] == "GNRL"
    written = (tmp_path / "staging" / "patched.ba2").read_bytes()
    assert struct.unpack_from("<I", written, 4)[0] == 1


def test_version_patch_backs_up_existing(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.ba2"
    src.write_bytes(_fake_ba2(7))
    (tmp_path / "staging").mkdir()
    dst = tmp_path / "staging" / "out.ba2"
    dst.write_bytes(_fake_ba2(1))  # pre-existing
    data = fo4_ba2_version_patch(cfg, str(src), "staging/out.ba2", target_version=1)["data"]
    assert data["backup_path"] is not None
    assert Path(data["backup_path"]).exists()


def test_dx10_warns_on_downgrade(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "tex.ba2"
    src.write_bytes(_fake_ba2(8, b"DX10"))
    data = fo4_ba2_version_patch(cfg, str(src), "staging/tex.ba2", target_version=1)["data"]
    assert any("DX10" in w for w in data["warnings"])


def test_invalid_target_version_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.ba2"
    src.write_bytes(_fake_ba2(8))
    with pytest.raises(Fo4McpError):
        fo4_ba2_version_patch(cfg, str(src), "staging/x.ba2", target_version=99)


def test_non_ba2_input_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "notba2.bin"
    src.write_bytes(b"PK\x03\x04nope")
    with pytest.raises(Fo4McpError):
        fo4_ba2_version_patch(cfg, str(src), "staging/x.ba2")


def test_forbidden_output_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.ba2"
    src.write_bytes(_fake_ba2(8))
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.ba2"
    with pytest.raises(PathForbiddenError):
        fo4_ba2_version_patch(cfg, str(src), forbidden)


# ---------------- integration: real BA2 ----------------

def test_real_hudframework_ba2(tmp_path):
    if not _HUD_BA2.exists():
        pytest.skip("HUDFramework BA2 not extracted")
    cfg = _cfg(_REPO)  # repo_root so staging/ is writable
    out = "staging/ba2-test/hud-v8.ba2"
    data = fo4_ba2_version_patch(cfg, str(_HUD_BA2), out, target_version=8)["data"]
    assert data["source_version"] == 1  # HUDFramework ships v1
    assert data["target_version"] == 8
    written = (_REPO / "staging" / "ba2-test" / "hud-v8.ba2").read_bytes()
    assert struct.unpack_from("<I", written, 4)[0] == 8
    assert len(written) == _HUD_BA2.stat().st_size  # body length unchanged
    import shutil
    shutil.rmtree(_REPO / "staging" / "ba2-test", ignore_errors=True)
