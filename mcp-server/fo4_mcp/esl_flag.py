"""ESL (Light Master) flag read/write — pure-Python header rewrite.

Closes the `fo4_read_load_order` gap where light state is guessed from the
file extension: an ESL-flagged `.esp` (flagged without renaming, common in
2025 modding) is reported as `light: None`. Here we read the *real* flag from
the TES4 record header, and offer a gated writer to set/clear it.

The whole operation is a single bit (0x0200) in the flags uint32 at absolute
file offset 8 — the exact same shape as `fo4_ba2_version_patch`. No subrecord
parsing, no `dataSize`/MAST/ONAM/HEDR recomputation, no Mutagen. See the
pre-study: research/p0/esl-flag/2026-06-05-flag-write.md.

The writer NEVER writes in place to the game folder: `output_path` is gated
through safety.check_write (staging/fixtures only; Steam Data/ fails closed).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ok
from .manifest import parse_manifest
from .safety import check_write

# TES4 record header (FO4, same 24-byte layout as Skyrim SE):
#   0  type 'TES4' | 4 dataSize u32 | 8 flags u32 | 12 formID | ...
_TES4_MAGIC = b"TES4"
_TES4_FLAGS_OFFSET = 8           # flags uint32, little-endian
_ESM_MASTER_FLAG = 0x00000001
_LOCALIZED_FLAG = 0x00000080
_LIGHT_MASTER_FLAG = 0x00000200  # the target bit


def _read_tes4_flags(data: bytes) -> int:
    """Return the TES4 record flags uint32 (LE) at absolute file offset 8."""
    if data[0:4] != _TES4_MAGIC:
        raise ValueError(
            f"not a Fallout 4 plugin (magic={data[0:4]!r}, expected {_TES4_MAGIC!r})"
        )
    if len(data) < _TES4_FLAGS_OFFSET + 4:
        raise ValueError("file too short to contain a TES4 record header")
    return struct.unpack_from("<I", data, _TES4_FLAGS_OFFSET)[0]


def _set_light_flag_bytes(data: bytes, enable: bool) -> tuple[bytes, bool, bool]:
    """Return (patched, old_light, new_light). Flips only the 0x0200 bit in the
    flags uint32; the body bytes[24:] and dataSize are untouched. Pure."""
    flags = _read_tes4_flags(data)
    old_light = bool(flags & _LIGHT_MASTER_FLAG)
    new_flags = (flags | _LIGHT_MASTER_FLAG) if enable else (flags & ~_LIGHT_MASTER_FLAG)
    new_light = bool(new_flags & _LIGHT_MASTER_FLAG)
    patched = (
        data[:_TES4_FLAGS_OFFSET]
        + struct.pack("<I", new_flags)
        + data[_TES4_FLAGS_OFFSET + 4:]
    )
    return patched, old_light, new_light


def _resolve_plugin(cfg: Config, plugin: str) -> Path:
    """Resolve a plugin arg: absolute, repo-relative, or under the FO4 Data dir."""
    p = Path(plugin)
    if p.is_absolute():
        return p.resolve()
    repo_rel = (cfg.repo_root / p).resolve()
    if repo_rel.exists():
        return repo_rel
    if cfg.fo4_install_dir is not None:
        data_rel = (cfg.fo4_install_dir / "Data" / p).resolve()
        if data_rel.exists():
            return data_rel
    return repo_rel


def fo4_read_esl_flag(cfg: Config, plugin: str) -> dict[str, Any]:
    """Read the real light/master flags from a plugin's TES4 header (read-only).

    Closes the extension-only classification gap: an ESL-flagged `.esp` reports
    `light_flagged: True` here even though its name says `.esp`. Reads only the
    header bytes; never writes.
    """
    path = _resolve_plugin(cfg, plugin)
    if not path.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"plugin not found: {path}",
            {"plugin": str(path)},
        )

    data = path.read_bytes()
    try:
        flags = _read_tes4_flags(data)
    except ValueError as e:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, str(e), {"plugin": str(path)})

    return ok({
        "plugin":        str(path),
        "light_flagged": bool(flags & _LIGHT_MASTER_FLAG),
        "flags_hex":     "0x%08X" % flags,
        "is_esm":        bool(flags & _ESM_MASTER_FLAG),
        "is_localized":  bool(flags & _LOCALIZED_FLAG),
    })


def _eligibility(cfg: Config, plugin_path: Path) -> dict[str, Any] | None:
    """Run the existing read-only eligibility check; None if Spriggit unavailable.

    Imported lazily to avoid a hard dependency on the binary for the pure
    helpers / read path. Failures degrade to None (caller warns), never raise.
    """
    try:
        from . import tools  # noqa: PLC0415

        manifest = parse_manifest(cfg.tools_dir / "MANIFEST.md")
        return tools.fo4_check_esl_eligibility(cfg, manifest, str(plugin_path))["data"]
    except Exception:
        return None


def fo4_set_esl_flag(
    cfg: Config, plugin: str, output_path: str, *, enable: bool = True
) -> dict[str, Any]:
    """Set/clear the ESL (light master) flag, writing a patched copy to a gated
    output (staging/fixtures; never the Steam Data/ source).

    Mirrors `fo4_ba2_version_patch`: pure-Python header rewrite, output safety-
    gated, existing target backed up to .bak. When `enable=True`, runs the
    existing eligibility logic and WARNS (does not refuse) if the verdict is not
    `esl-eligible` — flagging an ineligible plugin is a semantic footgun
    (FE-space overflow / save breakage), not a structural one.
    """
    out = Path(output_path)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY — before existence check

    src = _resolve_plugin(cfg, plugin)
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND,
            f"plugin not found: {src}",
            {"plugin": str(src)},
        )

    data = src.read_bytes()
    try:
        patched, old_light, new_light = _set_light_flag_bytes(data, enable)
    except ValueError as e:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, str(e), {"plugin": str(src)})

    warning = None
    eligibility = None
    if enable:
        eligibility = _eligibility(cfg, src)
        if eligibility is None:
            warning = (
                "eligibility check skipped (Spriggit unavailable); could not confirm "
                "this plugin is safe to ESL-flag — verify new-record count / max ObjectID manually"
            )
        elif eligibility.get("verdict") != "esl-eligible":
            warning = (
                f"eligibility verdict is '{eligibility.get('verdict')}', not 'esl-eligible' "
                f"({'; '.join(eligibility.get('reasons', []))}) — flagging anyway; "
                "flagging an ineligible plugin can overflow FE-space or break existing saves"
            )

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())
    out.write_bytes(patched)

    return ok({
        "plugin":      str(src),
        "output_path": str(out),
        "enabled":     enable,
        "old_light":   old_light,
        "new_light":   new_light,
        "bak_path":    str(backup) if backup else None,
        "eligibility": eligibility,
        "warning":     warning,
    })
