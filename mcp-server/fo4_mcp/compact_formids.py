"""fo4_compact_formids — SAFE GATING + planning for ESL FormID compaction.

xEdit's "Compact FormIDs for ESL" rewrites every new record's FormID into the
ESL ObjectID range (0x800..0xFFF). It is **IRREVERSIBLE** and **SAVE-BREAKING**:
any existing save that references the plugin's old FormIDs is invalidated. End
users never compact; an author compacts only their OWN plugin, only when needed,
and only BEFORE any save references it.

REALITY-CHECK (project core rule — do not freeze a signature on an unverified
command): "Compact FormIDs for ESL" is an xEdit GUI context-menu action. xEdit
does expose `-script:` command-line automation, but there is NO community-
confirmed, reliable headless script that performs the built-in compaction
routine end-to-end (the compaction logic lives behind the GUI menu, not the
scripting surface). So this tool does NOT silently perform an unverified
destructive op. Its JOB is:

  1. resolve the xEdit binary,
  2. construct + VALIDATE the exact argv we would document,
  3. gate the plugin path (must be writable, never the read-only game folder),
  4. require explicit confirm + saves_backed_up gates,
  5. make a .bak BEFORE any destructive step,
  6. default to dry_run=True (return the plan WITHOUT executing),
  7. on execute, attempt the invocation but be HONEST that the user must perform
     the menu action in the xEdit GUI on the .bak-protected plugin.

automatable = "gui-required".
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok
from .safety import check_write

# xEdit FO4 binary candidates, in resolution order. The community convention
# renames the generic xEdit to FO4Edit64.exe; this repo's distribution ships it
# as xFOEdit64.exe (see tools/MANIFEST.md). All are the same xEdit engine in
# Fallout 4 mode.
_XEDIT_CANDIDATES = (
    "FO4Edit64.exe",
    "xEdit64.exe",
    "xFOEdit64.exe",
    "FO4Edit.exe",
    "xFOEdit.exe",
)

_PLUGIN_SUFFIXES = {".esp", ".esm", ".esl"}


def _resolve_xedit(cfg: Config) -> Path:
    """Find an xEdit FO4 binary under cfg.tools_dir / 'xedit'.

    Raises ToolBinaryMissingError if none of the known candidates exist.
    """
    xedit_dir = cfg.tools_dir / "xedit"
    for name in _XEDIT_CANDIDATES:
        candidate = xedit_dir / name
        if candidate.exists():
            return candidate
    raise ToolBinaryMissingError(
        "xedit", str(xedit_dir / _XEDIT_CANDIDATES[0])
    )


def fo4_compact_formids(
    cfg: Config,
    plugin: str,
    *,
    confirm: bool = False,
    saves_backed_up: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Gate + plan an ESL FormID compaction for one author plugin.

    IRREVERSIBLE + SAVE-BREAKING. See module docstring for the reality-check.

    Args:
        plugin:          path to the plugin to compact (.esp/.esm/.esl). Resolved
                         against cfg.repo_root if relative. Must exist and be a
                         file. Must be writable (never the read-only game folder).
        confirm:         must be True to proceed past the refusal gate — the
                         caller is acknowledging the destructive nature.
        saves_backed_up: must be True; the user has run fo4_backup_saves first.
        dry_run:         default True — return the plan + documented xedit_cmd
                         WITHOUT making a .bak or invoking xEdit.

    Returns:
        ok({...}) — either a refusal envelope ({"refused": True, ...}) when a
        gate fails, or a plan / execute envelope.
    """
    # ---- plugin resolution + validation -------------------------------------
    p = Path(plugin)
    if not p.is_absolute():
        p = (cfg.repo_root / p).resolve()

    # The plugin will be rewritten in place by the compaction. Gate the write
    # target FIRST — fail closed for the read-only Steam game folder / Docs /
    # AppData (PathForbiddenError) before any other check, so a forbidden path
    # is rejected on the safety boundary regardless of whether it exists.
    check_write(p, cfg.repo_root)

    if not p.exists():
        raise Fo4McpError(
            ErrorCode.PATH_NOT_FOUND, f"plugin not found: {p}", {"plugin": str(p)}
        )
    if not p.is_file():
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT, f"plugin is not a file: {p}", {"plugin": str(p)}
        )
    if p.suffix.lower() not in _PLUGIN_SUFFIXES:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"not a plugin file (expected {sorted(_PLUGIN_SUFFIXES)}): {p.name}",
            {"plugin": str(p)},
        )

    # ---- mandatory refusal gates (clear ok-envelope, NOT an error) ----------
    if not confirm:
        return ok({
            "refused": True,
            "reason": "irreversible + save-breaking; pass confirm=True",
            "plugin": str(p),
        })
    if not saves_backed_up:
        return ok({
            "refused": True,
            "reason": "saves not confirmed backed up; run fo4_backup_saves first, "
                      "then pass saves_backed_up=True",
            "plugin": str(p),
        })

    # ---- binary resolution ---------------------------------------------------
    binary = _resolve_xedit(cfg)

    # ---- construct + VALIDATE the documented xEdit invocation ----------------
    # Documented form (community convention): point xEdit at the plugin via
    # -autoload and a script. There is no confirmed headless compaction script,
    # so this is the documented invocation to OPEN the plugin for the manual
    # "Compact FormIDs for ESL" menu action — not a silent headless run.
    bak_path = p.with_suffix(p.suffix + ".bak")
    xedit_cmd = [
        str(binary),
        "-fo4",
        f"-autoload:{p.name}",
        str(p),
    ]
    # validate argv: no empty tokens, binary first, plugin path present
    if any(not tok for tok in xedit_cmd):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            "constructed xEdit argv contains an empty token",
            {"argv": xedit_cmd},
        )

    warning = (
        "IRREVERSIBLE + SAVE-BREAKING. Run fo4_backup_saves first. A reliable "
        "fully-headless xEdit 'Compact FormIDs for ESL' is NOT confirmed — you "
        "must perform the menu action in the xEdit GUI on the .bak-protected "
        "plugin, then verify the result before shipping."
    )

    plan: dict[str, Any] = {
        "plugin": str(p),
        "action": "Compact FormIDs for ESL",
        "irreversible": True,
        "save_breaking": True,
        "steps": [
            "fo4_backup_saves (done — saves_backed_up=True)",
            f"copy {p.name} -> {bak_path.name} (.bak safety net)",
            f"open plugin in xEdit ({binary.name}) in FO4 mode",
            "right-click plugin -> Other -> Compact FormIDs for ESL",
            "apply, save, then verify FormIDs are in 0x800..0xFFF range",
        ],
        "binary": str(binary),
    }

    # ---- DRY RUN (default): plan only, no .bak, no execution -----------------
    if dry_run:
        return ok({
            "plan": plan,
            "bak_path": str(bak_path),
            "xedit_cmd": xedit_cmd,
            "dry_run": True,
            "warning": warning,
        })

    # ---- EXECUTE: make the .bak BEFORE any destructive step ------------------
    # .bak is created first so the original is recoverable no matter what xEdit
    # does. We back up to .bak even before attempting the invocation.
    shutil.copy2(p, bak_path)

    return ok({
        "plan": plan,
        "bak_path": str(bak_path),
        "xedit_cmd": xedit_cmd,
        "dry_run": False,
        "executed": False,
        "automatable": "gui-required",
        "note": (
            "A .bak copy was created. A reliable fully-headless xEdit compaction "
            "is NOT confirmed: 'Compact FormIDs for ESL' is a GUI context-menu "
            "action with no verified -script automation. Run the documented "
            "xedit_cmd to open the plugin, perform the menu action manually, "
            "save, and verify. The .bak protects the original if you need to "
            "revert."
        ),
        "warning": warning,
    })
