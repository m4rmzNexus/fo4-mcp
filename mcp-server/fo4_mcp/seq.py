"""fo4_build_seq — drive Creation Kit SEQ generation (CLI) for a plugin (Faz 3 / W12 shipping gap).

A Start-Game-Enabled quest does NOT fire on a new game unless the plugin ships a SEQ file
(Data\\SEQ\\<plugin>.seq) listing its start-game-enabled quest FormIDs — a real, commonly-forgotten
shipping requirement. Unlike navmesh, SEQ generation IS a scriptable CK CLI op (binary-confirmed
flag, 2026-06-21):

    CreationKit.exe -GenerateSEQ:<Plugin.esp>

Routed through MO2 so the .seq lands in the writable VFS overwrite, never the Steam Data folder
(see ck_run). dry_run defaults True (returns the argv WITHOUT running). A plugin with no
start-game-enabled quest produces no .seq — that is correct, not a failure.

KNOWN OPERATIONAL BOUNDARY (2026-06-21): CK -GenerateSEQ occasionally emits NO .seq when CK
loads the plugin "as a master" (read-only) instead of the active plugin — set the plugin active
(last in load order) for the run. CK is the RIGHT tool here, NOT a pure-Python generator: a .seq
is a flat array of uint32-LE quest FormIDs, but the high byte is the LOAD-ORDER index, which is
only known at CK generation time (not at authoring time) — a hand-rolled writer can't encode it
reliably. Path convention (xEdit-confirmed): Data\\Seq\\<plugin-basename>.seq. SEQ only matters for
fresh-new-game auto-start of a Start-Game-Enabled quest; a quest started via console/script (e.g.
the in-game smoke `startquest`) does not depend on it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok

_FLAG = "-GenerateSEQ"
_PLUGIN_SUFFIXES = (".esp", ".esm", ".esl")
_WARNING = (
    "machine-locked CK run (needs Steam logged in); the .seq lands in the MO2 VFS overwrite. "
    "Only start-game-enabled quests are emitted — a plugin without one produces no .seq."
)


def fo4_build_seq(cfg: Config, plugin: str, *, dry_run: bool = True) -> dict[str, Any]:
    """Construct (and on dry_run=False, run via MO2-VFS) the CK SEQ-generation command.

    Args:
        plugin:  plugin filename (must end .esp/.esm/.esl).
        dry_run: default True — return the constructed command WITHOUT running.

    Returns ok({...}) with the argv + metadata; when executed, the MO2-VFS run result.
    """
    if not plugin.lower().endswith(_PLUGIN_SUFFIXES):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"plugin must end in one of {list(_PLUGIN_SUFFIXES)}", {"plugin": plugin})
    if cfg.fo4_install_dir is None:
        raise Fo4McpError(
            ErrorCode.ENV_FO4_NOT_DETECTED,
            "FO4 install dir not detected; cannot locate CreationKit.exe", {})
    ck = (cfg.fo4_install_dir / "CreationKit.exe").resolve()
    if not ck.exists():
        raise ToolBinaryMissingError("CreationKit.exe", str(ck))
    ck_exe = str(ck)

    command = [ck_exe, f"{_FLAG}:{plugin}"]
    if dry_run:
        return ok({"command": command, "ck_exe": ck_exe, "plugin": plugin,
                   "dry_run": True, "warning": _WARNING})

    from .ck_run import run_ck_via_mo2

    timeout = max(cfg.subprocess_timeout, 1800)
    # No expected_outputs: a plugin with no start-game-enabled quest correctly emits NO .seq (see
    # docstring), so an empty overwrite is NOT a failure. artifacts_ok folds in only the ckpe.log scan.
    r = run_ck_via_mo2(cfg, command[1:], timeout=timeout)
    return ok({
        "command": command, "ck_exe": ck_exe, "plugin": plugin, "dry_run": False,
        "via": "mo2-vfs", "ok": r["exited"] and not r["timed_out"] and r["artifacts_ok"],
        **r, "warning": _WARNING,
    })
