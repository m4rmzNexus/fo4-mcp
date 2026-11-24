"""fo4_encode_texture — author a game-ready DDS from a source image (Track 4b).

Wraps DirectXTex **texconv** (`Texconvx64.exe`, bundled under xLODGen; manifest
slug "texconv"). This is the real PNG->DDS authoring step the asset-pipeline
roadmap (B2) calls for — it REPLACES the lossless dxgi-tag-flip
(`nif_ops.set_dds_diffuse_srgb`, which only rewrites the 4-byte format tag) with
a true re-encode: gamma-correct mip generation + power-of-two resize + an
explicit BC format. (The tag-flip stays as a zero-risk fallback for already-
encoded linear-diffuse DDS.)

Proven argv (hand-tested on coupon art -> 1024x1024 BC7_UNORM_SRGB / DXGI 99):
    Texconvx64.exe -nologo -y -f <FMT> [-srgb] -m <mips> [-w W -h H] -o <dir> <in>
texconv writes `<dir>/<inputstem>.DDS`; we rename to the requested output name.

FO4 format convention:
  * diffuse / albedo  -> BC7_UNORM_SRGB (sRGB);  a linear UNORM diffuse renders washed-out
  * normal (_n)       -> BC5_UNORM     (no sRGB, 2-channel)
  * specular / mask   -> BC7_UNORM     (linear)

Output is safety-gated to staging/ or fixtures/ (Karar 4).
"""

from __future__ import annotations

import math
import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok
from .manifest import Manifest
from .safety import check_write
from .subprocess_wrap import run_tool

# texconv -f <name> -> the DXGI format enum value the output DDS must carry.
# Restricted to the formats FO4 actually uses for authored art.
_FORMATS: dict[str, int] = {
    "BC7_UNORM_SRGB": 99, "BC7_UNORM": 98,
    "BC1_UNORM_SRGB": 72, "BC1_UNORM": 71,
    "BC3_UNORM_SRGB": 78, "BC3_UNORM": 77,
    "BC5_UNORM": 83, "BC4_UNORM": 80,
    "R8G8B8A8_UNORM_SRGB": 29, "R8G8B8A8_UNORM": 28,
}
# Which of the above are sRGB (color-space) formats.
_SRGB_FORMATS = {99, 72, 78, 29}

_IMAGE_SUFFIXES = {".png", ".tga", ".bmp", ".jpg", ".jpeg", ".dds", ".tif", ".tiff", ".hdr"}


def _nearest_pow2(n: int) -> int:
    """Round a dimension to the nearest power of two in log space, clamped to [4, 4096]
    (FO4's practical texture range). Non-pow2 textures break mipmapping/streaming."""
    if n < 4:
        return 4
    p = 1 << round(math.log2(n))
    return max(4, min(4096, p))


def _png_dims(path: Path) -> tuple[int, int] | None:
    """(width, height) from a PNG IHDR, or None if not a parseable PNG."""
    b = path.read_bytes()[:33]
    if b[:8] != b"\x89PNG\r\n\x1a\n" or b[12:16] != b"IHDR":
        return None
    w, h = struct.unpack_from(">II", b, 16)
    return (w, h)


def _read_dds_format(path: Path) -> tuple[int | None, int, int]:
    """(dxgiFormat|None, width, height) of a produced DDS. dxgiFormat is set only
    for a DX10-header DDS. width/height come from the base header (offsets 16/12)."""
    b = path.read_bytes()[:148]
    if b[:4] != b"DDS ":
        return (None, 0, 0)
    height, width = struct.unpack_from("<II", b, 12)
    dxgi = struct.unpack_from("<I", b, 128)[0] if b[0x54:0x58] == b"DX10" and len(b) >= 132 else None
    return (dxgi, width, height)


def fo4_encode_texture(
    cfg: Config,
    manifest: Manifest,
    source_image: str,
    output_dds: str,
    *,
    fmt: str = "BC7_UNORM_SRGB",
    srgb: bool = True,
    mips: int = 0,
    resize_pow2: bool = True,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Encode a source image into a game-ready DDS via texconv (#B2 / Track 4b).

    Args:
        source_image: PNG/TGA/BMP/JPG/TIFF/HDR/DDS to encode. Resolved against
                      repo_root if relative. Must exist.
        output_dds:   target .dds; resolved against repo_root if relative.
                      Gated to staging/ or fixtures/. An existing target is
                      overwritten (texconv -y).
        fmt:          texconv -f format; one of _FORMATS (FO4-authoring subset).
        srgb:         pass -srgb (gamma-correct filtering for an sRGB color map).
                      Auto-aligned to the format with a warning on mismatch.
        mips:         -m value; 0 = full chain down to 1x1.
        resize_pow2:  resize to the nearest power-of-two (mipmap/stream safe).
                      Only applied when source dims are known (PNG) or width/
                      height are given explicitly.
        width/height: explicit output size (overrides resize_pow2 inference).

    Returns ok({...}) with the produced format, dims, byte size, argv, warnings.
    """
    fmt = fmt.upper()
    if fmt not in _FORMATS:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"fmt must be one of {sorted(_FORMATS)}",
            {"fmt": fmt},
        )
    expected_dxgi = _FORMATS[fmt]

    warnings: list[str] = []
    # Keep -srgb consistent with the chosen format: an _SRGB format wants sRGB
    # filtering; a linear format must NOT be sRGB-filtered. Correct + warn.
    fmt_is_srgb = expected_dxgi in _SRGB_FORMATS
    if srgb and not fmt_is_srgb:
        warnings.append(f"srgb disabled: '{fmt}' is a linear format (sRGB filtering would double-correct)")
        srgb = False
    elif not srgb and fmt_is_srgb:
        warnings.append(f"srgb enabled: '{fmt}' is an sRGB format — filtering must be gamma-correct")
        srgb = True

    # ---- binary resolution via manifest slug "texconv" ----
    entry = manifest.get("texconv")
    if entry is None or not entry.is_resolved:
        raise ToolBinaryMissingError("texconv", entry.binary_path if entry else None)
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()

    # ---- source image ----
    src = Path(source_image)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not src.is_file():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"source_image not found: {src}", {"source_image": str(src)}
        )
    if src.suffix.lower() not in _IMAGE_SUFFIXES:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"unsupported source suffix '{src.suffix}'; expected one of {sorted(_IMAGE_SUFFIXES)}",
            {"source_image": str(src)},
        )

    # ---- output gate ----
    out = Path(output_dds)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    if out.suffix.lower() != ".dds":
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"output must end in .dds: {out}", {"output_dds": str(out)}
        )
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY
    out.parent.mkdir(parents=True, exist_ok=True)

    # ---- target dimensions ----
    target_w, target_h = width, height
    if (target_w is None or target_h is None) and resize_pow2:
        dims = _png_dims(src)
        if dims is not None:
            target_w = target_w or _nearest_pow2(dims[0])
            target_h = target_h or _nearest_pow2(dims[1])
        else:
            warnings.append(
                f"resize_pow2 skipped: cannot read dimensions of '{src.name}' "
                "(non-PNG); pass width/height to force a size"
            )

    # ---- argv (proven order) ----
    args: list[str] = ["-nologo", "-y", "-f", fmt]
    if srgb:
        args.append("-srgb")
    args += ["-m", str(mips)]
    if target_w and target_h:
        args += ["-w", str(target_w), "-h", str(target_h)]
    args += ["-o", str(out.parent), str(src)]

    # Binary path is RECORDED but may be absent on disk (CI / fresh clone); surface
    # a clean ToolBinaryMissingError rather than an opaque run_tool failure.
    if not binary.is_file():
        raise ToolBinaryMissingError("texconv", str(binary))

    result = run_tool(binary, args, timeout=cfg.subprocess_timeout)

    # texconv writes <out.parent>/<src.stem>.DDS (case varies). Find + rename to
    # the requested output name.
    produced = None
    for cand in (out.parent / f"{src.stem}.dds", out.parent / f"{src.stem}.DDS"):
        if cand.exists():
            produced = cand
            break
    if produced is not None and produced.resolve() != out.resolve():
        out.unlink(missing_ok=True)
        produced.replace(out)

    # OS-17-style: success != "a file appeared" — confirm a real DDS of the
    # requested DXGI format landed at the target.
    actual_dxgi, actual_w, actual_h = (None, 0, 0)
    format_ok = False
    if out.exists():
        actual_dxgi, actual_w, actual_h = _read_dds_format(out)
        format_ok = actual_dxgi == expected_dxgi
        if actual_dxgi is None:
            warnings.append("output is not a DX10-header DDS — cannot confirm format")
        elif not format_ok:
            warnings.append(
                f"output DXGI {actual_dxgi} != expected {expected_dxgi} for fmt '{fmt}'"
            )

    succeeded = result.ok and out.exists() and format_ok

    return ok({
        "source_image":  str(src),
        "output":        str(out),
        "format":        fmt,
        "srgb":          srgb,
        "expected_dxgi": expected_dxgi,
        "actual_dxgi":   actual_dxgi,
        "width":         actual_w,
        "height":        actual_h,
        "mips":          mips,
        "exit_code":     result.exit_code,
        "ok":            succeeded,
        "bytes":         out.stat().st_size if out.exists() else 0,
        "argv":          args,
        "stdout_tail":   result.stdout[-1000:],
        "stderr_tail":   result.stderr[-1000:],
        "warnings":      warnings,
    })
