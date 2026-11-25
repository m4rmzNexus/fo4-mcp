"""fo4_pack_ba2 — pack a source folder into a Fallout 4 BA2 archive (#A2).

Wraps the console BSArch v0.9c (`tools/xedit/BSArch64.exe`, zilav/ElminsterAU/
Sheson, MPL-2.0) bundled with xEdit — a real headless packer (`pack` verb).
This unblocks the long-deferred BA2 pack tool; the GUI BSArchPro variant has no
headless CLI and is NOT used.

Verified CLI (confirmed by running the binary):
    BSArch64.exe pack <source_folder> <archive.ba2> -fo4 [-z] [-mt] [-share]
    BSArch64.exe pack <source_folder> <archive.ba2> -fo4dds [-mt] [-share]

  -fo4    general (GNRL) archive — meshes/scripts/sounds/etc.
  -fo4dds texture (DX10) archive — DDS only.
  -z      zlib-compress the body. WARNING: breaks sounds/voices if the archive
          contains any; only safe for meshes/scripts/etc. DDS archives are not
          -z compressed (BSArch ignores it), so we drop it + warn for "dds".
  -mt     multithreaded.
  -share  dedupe byte-identical files.

Layout note (empirical): BSArch packs the source folder's *contents* relative
to the folder root — i.e. the folder you point at IS the Data/ root, so a file
at `<source>/meshes/foo.nif` lands in the BA2 as `meshes\foo.nif`. Lay the
source dir out exactly like a Data/ tree.

Output is safety-gated to staging/ or fixtures/ (Karar 4); an existing target
is backed up to `.bak` before packing, mirroring fo4_ba2_version_patch.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Literal

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok
from .manifest import Manifest
from .safety import check_write
from .subprocess_wrap import run_tool

_ARCHIVE_TYPE_FLAGS = {
    "general": "-fo4",
    "dds": "-fo4dds",
    "textures": "-fo4dds",  # alias
}

_BA2_MAGIC = b"BTDX"
# Type tag the engine writes at offset 8 for each archive flavour.
_EXPECTED_TYPE_TAG = {"general": "GNRL", "dds": "DX10", "textures": "DX10"}


def _read_ba2_header(data: bytes) -> dict[str, Any]:
    """Parse the fixed BA2 header: magic 'BTDX'(4) | version u32 | type 'GNRL'/'DX10'(4) | fileCount u32.

    Pure. Returns magic_ok / version / type_tag / file_count (None where unreadable).
    Mirrors tools._patch_ba2_version_bytes' layout (verified vs real archives)."""
    if len(data) < 16 or data[0:4] != _BA2_MAGIC:
        return {"magic_ok": False, "version": None, "type_tag": None, "file_count": None}
    return {
        "magic_ok":   True,
        "version":    struct.unpack_from("<I", data, 4)[0],
        "type_tag":   data[8:12].decode("ascii", "replace"),
        "file_count": struct.unpack_from("<I", data, 12)[0],
    }


def _naming_warning(out_name: str, archive_type: str) -> str | None:
    """The engine only AUTO-loads a BA2 named '<PluginName> - Main.ba2' (general)
    or '<PluginName> - Textures.ba2' (dds) matching a plugin in the load order.
    Return a warning if the output name breaks that convention, else None (it may
    still be valid for manual/loose use, so this is advisory, not a failure)."""
    lower = out_name.lower()
    if archive_type == "general":
        if not lower.endswith(" - main.ba2"):
            return (f"'{out_name}' is not named '<PluginName> - Main.ba2' — the engine only "
                    "auto-loads a general archive whose name matches a plugin with that suffix")
    elif not lower.endswith(" - textures.ba2"):
        return (f"'{out_name}' is not named '<PluginName> - Textures.ba2' — the engine only "
                "auto-loads a texture archive whose name matches a plugin with that suffix")
    return None


def fo4_pack_ba2(
    cfg: Config,
    manifest: Manifest,
    source_dir: str,
    output_ba2: str,
    *,
    archive_type: str = "general",
    compress: bool = False,
    multithreaded: bool = True,
    share: bool = False,
) -> dict[str, Any]:
    """Pack a source folder into a BA2 via the console BSArch (#A2).

    Args:
        source_dir:   folder to pack; laid out like a Data/ tree (its contents
                      become the archive root). Resolved against repo_root if
                      relative. Must exist, be a directory, and be non-empty.
        output_ba2:   target .ba2; resolved against repo_root if relative.
                      Gated to staging/ or fixtures/. Existing target is .bak'd.
        archive_type: "general" (-fo4) or "dds"/"textures" (-fo4dds).
        compress:     -z body compression (general only; ignored+warned for dds;
                      breaks sounds/voices — caller's responsibility).
        multithreaded:-mt.
        share:        -share (dedupe identical files).

    Returns ok({...}) with exit code, output size, backup path, argv, warnings.
    """
    fmt_flag = _ARCHIVE_TYPE_FLAGS.get(archive_type)
    if fmt_flag is None:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"archive_type must be one of {sorted(_ARCHIVE_TYPE_FLAGS)}",
            {"archive_type": archive_type},
        )
    is_dds = fmt_flag == "-fo4dds"

    warnings: list[str] = []
    if is_dds and compress:
        warnings.append(
            "compress ignored: DDS (-fo4dds) archives are not -z compressed by BSArch"
        )

    # ---- binary resolution via manifest slug "bsarch" ----
    entry = manifest.get("bsarch")
    if entry is None or not entry.is_resolved:
        raise ToolBinaryMissingError("bsarch", entry.binary_path if entry else None)
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()

    # ---- source dir ----
    src = Path(source_dir)
    if not src.is_absolute():
        src = (cfg.repo_root / src).resolve()
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"source_dir not found: {src}", {"source_dir": str(src)}
        )
    if not src.is_dir():
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"source_dir is not a directory: {src}",
            {"source_dir": str(src)},
        )
    if not any(src.iterdir()):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"source_dir is empty: {src}", {"source_dir": str(src)}
        )

    # ---- output gate ----
    out = Path(output_ba2)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY
    out.parent.mkdir(parents=True, exist_ok=True)

    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())

    # ---- argv ----
    args: list[str] = ["pack", str(src), str(out), fmt_flag]
    if compress and not is_dds:
        args.append("-z")
    if multithreaded:
        args.append("-mt")
    if share:
        args.append("-share")

    # The binary path is RECORDED (is_resolved) but may not be on disk; surface a
    # clean ToolBinaryMissingError instead of an opaque run_tool failure. Placed
    # last (after the forbidden-output / missing-source gates) so those keep
    # precedence — callers/tests rely on that ordering.
    if not binary.is_file():
        raise ToolBinaryMissingError("bsarch", str(binary))

    result = run_tool(binary, args, timeout=cfg.subprocess_timeout)

    # OS-17: success != "a file appeared" — read the produced header and confirm
    # it's a real BA2 of the requested flavour, and flag a non-conventional name.
    header: dict[str, Any] | None = None
    header_valid = False
    if out.exists():
        header = _read_ba2_header(out.read_bytes()[:16])
        expected_tag = _EXPECTED_TYPE_TAG[archive_type]
        header_valid = bool(header["magic_ok"]) and header["type_tag"] == expected_tag
        if not header["magic_ok"]:
            warnings.append("output is not a valid BA2 (missing BTDX magic) — pack likely failed")
        elif header["type_tag"] != expected_tag:
            warnings.append(
                f"BA2 type tag '{header['type_tag']}' != expected '{expected_tag}' for "
                f"archive_type='{archive_type}' — wrong -fo4/-fo4dds flavour?"
            )
        naming = _naming_warning(out.name, archive_type)
        if naming:
            warnings.append(naming)

    succeeded = result.ok and out.exists() and header_valid

    return ok({
        "source_dir":   str(src),
        "output":       str(out),
        "archive_type": archive_type,
        "compressed":   compress and not is_dds,
        "multithreaded": multithreaded,
        "share":        share,
        "exit_code":    result.exit_code,
        "ok":           succeeded,
        "header":       header,
        "bytes":        out.stat().st_size if out.exists() else 0,
        "backup_path":  str(backup) if backup else None,
        "argv":         args,
        "stdout_tail":  result.stdout[-1500:],
        "stderr_tail":  result.stderr[-1500:],
        "warnings":     warnings,
    })
