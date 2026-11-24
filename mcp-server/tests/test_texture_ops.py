"""fo4_encode_texture tests — texconv PNG->DDS wrapper (Track 4b).

Pure tests (pow2 math, PNG dim read, validation/precedence, srgb auto-align) run
always; the integration test drives the real Texconvx64.exe and is skipped if
the bundled binary is absent."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError, ToolBinaryMissingError
from fo4_mcp.manifest import Manifest, ToolEntry
from fo4_mcp.texture_ops import (
    _nearest_pow2,
    _png_dims,
    _read_dds_format,
    fo4_encode_texture,
)

_REPO = Path(__file__).resolve().parents[2]
_TEXCONV = _REPO / "tools" / "xlodgen" / "xLODGen" / "Edit Scripts" / "Texconvx64.exe"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _mani(binary: Path = _TEXCONV) -> Manifest:
    return Manifest(
        tools={"texconv": ToolEntry(
            name="Texconv", version="dx", source="", asset="",
            binary_path=str(binary), license="MIT", raw={},
        )},
        source_path=Path("x"),
    )


def _make_png(path: Path, w: int, h: int) -> Path:
    """Write a minimal valid 8-bit RGB PNG (solid mid-gray) so texconv can read it."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # RGB, no interlace
    row = b"\x00" + b"\x80\x80\x80" * w                  # filter byte 0 + gray pixels
    idat = zlib.compress(row * h)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b""))
    return path


# ---------------- pure: pow2 + dim read ----------------

def test_nearest_pow2_rounds_in_log_space():
    assert _nearest_pow2(1384) == 1024   # the real coupon width
    assert _nearest_pow2(1010) == 1024
    assert _nearest_pow2(1536) == 2048   # 1.5 * 1024 rounds up
    assert _nearest_pow2(700) == 512
    assert _nearest_pow2(1) == 4         # clamp floor
    assert _nearest_pow2(99999) == 4096  # clamp ceil


def test_png_dims_reads_ihdr(tmp_path):
    p = _make_png(tmp_path / "x.png", 1384, 1010)
    assert _png_dims(p) == (1384, 1010)


def test_png_dims_rejects_non_png(tmp_path):
    f = tmp_path / "x.png"
    f.write_bytes(b"not a png")
    assert _png_dims(f) is None


# ---------------- pure: validation + precedence (no binary) ----------------

def test_bad_format_raises(tmp_path):
    src = _make_png(tmp_path / "s.png", 16, 16)
    with pytest.raises(Fo4McpError):
        fo4_encode_texture(_cfg(tmp_path), _mani(), str(src), "staging/x.dds", fmt="BC9_MYTH")


def test_missing_source_raises(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_encode_texture(_cfg(tmp_path), _mani(), str(tmp_path / "nope.png"), "staging/x.dds")


def test_non_dds_output_raises(tmp_path):
    src = _make_png(tmp_path / "s.png", 16, 16)
    with pytest.raises(Fo4McpError):
        fo4_encode_texture(_cfg(_REPO), _mani(), str(src), "staging/x.png")


def test_forbidden_output_raises(tmp_path):
    src = _make_png(tmp_path / "s.png", 16, 16)
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/Textures/x.dds"
    with pytest.raises(PathForbiddenError):
        fo4_encode_texture(_cfg(_REPO), _mani(), str(src), forbidden)


def test_unresolved_binary_raises(tmp_path):
    src = _make_png(tmp_path / "s.png", 16, 16)
    bad = Manifest(tools={"texconv": ToolEntry(
        name="Texconv", version="dx", source="", asset="",
        binary_path="TBD", license="MIT", raw={})}, source_path=Path("x"))
    with pytest.raises(ToolBinaryMissingError):
        fo4_encode_texture(_cfg(_REPO), bad, str(src), "staging/x.dds")


# ---------------- integration: real texconv ----------------

def _skip_if_no_texconv():
    if not _TEXCONV.exists():
        pytest.skip("Texconvx64.exe not present")


def test_encode_diffuse_is_srgb_bc7(tmp_path):
    _skip_if_no_texconv()
    cfg = _cfg(_REPO)  # repo_root so staging/ is writable
    src = _make_png(tmp_path / "art.png", 300, 300)   # non-pow2 -> resized to 256
    out_rel = "staging/texconv-test/art.dds"
    out = _REPO / "staging" / "texconv-test" / "art.dds"
    try:
        data = fo4_encode_texture(cfg, _mani(), str(src), out_rel,
                                  fmt="BC7_UNORM_SRGB")["data"]
        assert data["ok"] is True
        assert data["actual_dxgi"] == 99           # BC7_UNORM_SRGB
        assert data["srgb"] is True
        assert data["width"] == 256 and data["height"] == 256   # nearest pow2 of 300
        assert out.read_bytes()[:4] == b"DDS "
    finally:
        import shutil
        shutil.rmtree(_REPO / "staging" / "texconv-test", ignore_errors=True)


def test_encode_linear_format_disables_srgb(tmp_path):
    _skip_if_no_texconv()
    cfg = _cfg(_REPO)
    src = _make_png(tmp_path / "spec.png", 64, 64)
    out_rel = "staging/texconv-test/spec.dds"
    try:
        data = fo4_encode_texture(cfg, _mani(), str(src), out_rel,
                                  fmt="BC7_UNORM", srgb=True)["data"]   # ask srgb on a linear fmt
        assert data["ok"] is True
        assert data["actual_dxgi"] == 98           # BC7_UNORM (linear)
        assert data["srgb"] is False               # auto-corrected off
        assert any("srgb disabled" in w for w in data["warnings"])
    finally:
        import shutil
        shutil.rmtree(_REPO / "staging" / "texconv-test", ignore_errors=True)


def test_read_dds_format_helper():
    # round-trip the helper against a known DX10 header layout
    hdr = bytearray(148)
    hdr[0:4] = b"DDS "
    struct.pack_into("<II", hdr, 12, 512, 256)       # height, width
    hdr[0x54:0x58] = b"DX10"
    struct.pack_into("<I", hdr, 128, 99)
    dxgi, w, h = _read_dds_format_bytes(bytes(hdr))
    assert (dxgi, w, h) == (99, 256, 512)


def _read_dds_format_bytes(b: bytes):
    """Tiny shim so the helper test doesn't need a tmp file."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".dds", delete=False) as f:
        f.write(b)
        name = f.name
    try:
        return _read_dds_format(Path(name))
    finally:
        Path(name).unlink(missing_ok=True)
