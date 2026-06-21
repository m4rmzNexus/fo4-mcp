"""Plugin-format planner + ESM master-flag writer — Faz 3 / W0 foundation.

The whole new-world-content quest roadmap (docs/world-content-quest-roadmap.md)
inherits one binary design decision: what plugin format the content forces. W0
locks it with two tools:

* `fo4_plan_plugin_format` — READ-ONLY advisor. Enforces the locked format law
  (tools._esl_verdict): ANY new cell/worldspace forces an ESM-flagged ESP and can
  NEVER be a light master (new-cell previs/precombine can't live in FE-space).
  Reports the REQUIRED format, the current TES4 flags, and any conflict. Composes
  fo4_check_esl_eligibility; never writes.

* `fo4_set_master_flag` — the dual of esl_flag.fo4_set_esl_flag: a pure-Python flip
  of the TES4 ESM master flag (0x0001) at file offset 8, gated output + .bak. It
  REFUSES the one true corruption combo (light-flagged AND new cells — light + new-
  cell previs is structurally invalid) and warns on softer mismatches.

Shares esl_flag's header primitives (same TES4 flags uint32 at offset 8) — no
duplicated byte logic. Pre-study: research/p0/esl-flag/2026-06-05-flag-write.md.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ok
from .esl_flag import (
    _ESM_MASTER_FLAG,
    _LIGHT_MASTER_FLAG,
    _TES4_FLAGS_OFFSET,
    _eligibility,
    _read_tes4_flags,
    _resolve_plugin,
)
from .safety import check_write


def _set_master_flag_bytes(data: bytes, enable: bool) -> tuple[bytes, bool, bool]:
    """Return (patched, old_master, new_master). Flips ONLY the 0x0001 ESM bit in
    the flags uint32 at offset 8; the body bytes[24:] and dataSize are untouched.
    Pure — the testable mirror of esl_flag._set_light_flag_bytes."""
    flags = _read_tes4_flags(data)
    old_master = bool(flags & _ESM_MASTER_FLAG)
    new_flags = (flags | _ESM_MASTER_FLAG) if enable else (flags & ~_ESM_MASTER_FLAG)
    new_master = bool(new_flags & _ESM_MASTER_FLAG)
    patched = (
        data[:_TES4_FLAGS_OFFSET]
        + struct.pack("<I", new_flags)
        + data[_TES4_FLAGS_OFFSET + 4:]
    )
    return patched, old_master, new_master


# Maps an esl_verdict to (required_format, recommended_action). Pure.
def _required_format(verdict: str) -> tuple[str, str]:
    return {
        "esm-flag": (
            "esm-flagged-esp",
            "new cell/worldspace present -> set the ESM master flag "
            "(fo4_set_master_flag enable=True) AND keep the light flag OFF; new-cell "
            "previs/precombine cannot live in FE/light-master space",
        ),
        "esl-eligible": (
            "esl-flagged-esp",
            "ESL-eligible -> set the light flag (fo4_set_esl_flag enable=True); do NOT ESM-flag",
        ),
        "esl-needs-compaction": (
            "esl-after-compaction",
            "ESL-eligible except max ObjectID > 0xFFF -> fo4_compact_formids first "
            "(gated, irreversible), then light-flag",
        ),
        "no-new-records": (
            "override-only-esp",
            "override-only plugin -> flagging is moot; a light flag is fine if it only overrides",
        ),
        "plain-esp": (
            "full-esp",
            "too many new records for ESL -> ship as a full ESP/ESM",
        ),
    }.get(verdict, ("unknown", f"unrecognized verdict '{verdict}'"))


def fo4_plan_plugin_format(cfg: Config, plugin: str) -> dict[str, Any]:
    """READ-ONLY: report the REQUIRED plugin format for a draft plugin's content
    and whether its current TES4 flags match, enforcing the locked format law.

    Core law (tools._esl_verdict): ANY new cell/worldspace -> ESM-flagged ESP,
    never light. Composes fo4_check_esl_eligibility (degrades to a flags-only
    report + warning if the writer/Spriggit is unavailable). Never writes.
    """
    src = _resolve_plugin(cfg, plugin)
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {src}", {"plugin": str(src)}
        )

    data = src.read_bytes()
    try:
        flags = _read_tes4_flags(data)
    except ValueError as e:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, str(e), {"plugin": str(src)})

    cur_esm = bool(flags & _ESM_MASTER_FLAG)
    cur_light = bool(flags & _LIGHT_MASTER_FLAG)
    if cur_esm and cur_light:
        current_format = "esl-flagged-esm (light master)"
    elif cur_light:
        current_format = "esl-flagged-esp (light)"
    elif cur_esm:
        current_format = "esm-flagged-esp (full master)"
    else:
        current_format = "plain-esp"

    elig = _eligibility(cfg, src)  # data dict or None (degrades, never raises)
    warning = None
    if elig is None:
        verdict = "unknown"
        required_format, action = (
            "unknown",
            "install the mutagen-cli/Spriggit writer to compute the required format",
        )
        warning = (
            "eligibility scan unavailable (Spriggit/writer missing) — required format "
            "could not be computed; current flags reported only"
        )
    else:
        verdict = elig.get("verdict", "unknown")
        required_format, action = _required_format(verdict)

    conflicts: list[str] = []
    if verdict == "esm-flag":
        if cur_light:
            conflicts.append(
                "CRITICAL: plugin is light-flagged but creates new cell/worldspace records — "
                "new-cell previs can't live in FE-space; clear the light flag and set ESM master"
            )
        if not cur_esm:
            conflicts.append(
                "new cell/worldspace present but the ESM master flag is OFF — set it "
                "(fo4_set_master_flag enable=True)"
            )
    elif verdict == "esl-eligible" and cur_esm and not cur_light:
        conflicts.append(
            "ESL-eligible content carries a full ESM flag — forfeits the light/ESL slot economy"
        )

    return ok({
        "plugin":                       str(src),
        "current_format":               current_format,
        "current_flags_hex":            "0x%08X" % flags,
        "is_esm":                       cur_esm,
        "is_light":                     cur_light,
        "eligibility_verdict":          verdict,
        "eligibility_reasons":          elig.get("reasons", []) if elig else [],
        "new_cell_or_worldspace_count": elig.get("new_cell_or_worldspace_count") if elig else None,
        "required_format":              required_format,
        "recommended_action":           action,
        "current_matches_required":     not conflicts,
        "conflicts":                    conflicts,
        "warning":                      warning,
    })


def fo4_set_master_flag(
    cfg: Config, plugin: str, output_path: str, *, enable: bool = True
) -> dict[str, Any]:
    """Set/clear the ESM master flag (0x0001), writing a patched copy to a gated
    output (staging/fixtures; never the Steam Data/ source).

    Mirrors fo4_set_esl_flag (pure-Python header rewrite, gated, .bak). The W0
    conflict-safety guard: when enabling ESM on a plugin that is currently light-
    flagged AND creates new cell/worldspace records, REFUSE — a light master can't
    hold new-cell previs/precombine (FE-space), so that combo is structurally
    invalid. Clear the light flag first (fo4_set_esl_flag enable=False). Softer
    mismatches (ESM-flagging content that doesn't need it) warn, not refuse.
    """
    out = Path(output_path)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises on DENY before any existence check

    src = _resolve_plugin(cfg, plugin)
    if not src.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {src}", {"plugin": str(src)}
        )

    data = src.read_bytes()
    try:
        flags = _read_tes4_flags(data)
    except ValueError as e:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, str(e), {"plugin": str(src)})

    src_light = bool(flags & _LIGHT_MASTER_FLAG)
    warning = None
    eligibility = None
    if enable:
        eligibility = _eligibility(cfg, src)
        has_new_cells = bool(eligibility and eligibility.get("verdict") == "esm-flag")
        if src_light and has_new_cells:
            raise Fo4McpError(
                ErrorCode.INVALID_ARGUMENT,
                "plugin is light-flagged (0x0200) AND creates new cell/worldspace records — "
                "a light master can't hold new-cell previs/precombine (FE-space). Clear the light "
                "flag first: fo4_set_esl_flag(plugin, out, enable=False), then set the master flag.",
                {
                    "plugin": str(src),
                    "light_flagged": True,
                    "eligibility_verdict": eligibility.get("verdict"),
                },
            )
        if eligibility is None:
            warning = (
                "eligibility check skipped (Spriggit unavailable) — could not confirm whether this "
                "plugin needs an ESM flag; verify new cell/worldspace presence manually"
            )
        elif not has_new_cells:
            warning = (
                f"eligibility verdict is '{eligibility.get('verdict')}', not 'esm-flag' — this "
                "content doesn't require a full ESM; ESM-flagging forfeits the ESL/light slot "
                "economy (an esl-eligible plugin should use fo4_set_esl_flag instead)"
            )

    patched, old_master, new_master = _set_master_flag_bytes(data, enable)

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
        "old_master":  old_master,
        "new_master":  new_master,
        "bak_path":    str(backup) if backup else None,
        "eligibility": eligibility,
        "warning":     warning,
    })
