"""fo4_build_facegen — drive Creation Kit FaceGen export (CLI) for a plugin (Faz 3 / W10).

The Creation Kit (with CKPE merged into the main game folder, verified on this machine:
CreationKit.exe alongside Fallout4.exe + winhttp.dll, GPU = RTX 3080) exposes a headless
FaceGen export flag. The platform TARGET is mandatory (discovered by a live run 2026-06-21 —
CK rejects the bare form with "Should be -ExportFaceGenData:<ESMFilename> <XB1|X64|PS4|W32>"):

    CreationKit.exe -ExportFaceGenData:<Plugin.esp> <XB1|X64|PS4|W32>   (W32 = PC desktop)

It bakes the per-NPC FaceGen meshes (.nif -> Data\\Meshes\\Actors\\Character\\FaceGenData\\FaceGeom\\
<plugin>\\) and textures (.dds -> Data\\Textures\\Actors\\Character\\FaceCustomization\\<plugin>\\)
for the NPCs that carry their own face data. Trait-templated NPCs (W3 defaultTemplate + Traits)
inherit a baked face and need ZERO export — use fo4_lint_npc_template to see the bounded set
(facegen_needed; inheritsTraits=true => lower risk).

REALITY-CHECK (project core rule, mirrors fo4_build_previs): a real CK FaceGen run is machine-locked
(CK grabs the GPU/display), needs Steam logged in, and rewrites the game Data tree. It is therefore
USER-TRIGGERED: this function defaults to dry_run=True (resolve binary + construct/validate the exact
argv, return it WITHOUT executing). Only dry_run=False spawns CK. CK owns its own Data output for
this op (not gated through check_write) — the run is the user's explicit trigger.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok

_FLAG = "-ExportFaceGenData"
_PLUGIN_SUFFIXES = (".esp", ".esm", ".esl")
_TARGETS = ("W32", "X64", "XB1", "PS4")   # W32 = PC desktop (mandatory CK arg)
_WARNING = (
    "machine-locked CK run (needs Steam logged in + grabs the GPU/display); outputs land in game "
    "Data\\Meshes\\Actors\\Character\\FaceGenData and Data\\Textures\\Actors\\Character\\"
    "FaceCustomization. Trait-templated NPCs need NO export — scope with fo4_lint_npc_template."
)


def fo4_build_facegen(
    cfg: Config,
    plugin: str,
    *,
    target: str = "W32",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Construct (and optionally execute) the CK FaceGen-export command for a plugin.

    Args:
        plugin:  plugin filename (must end .esp/.esm/.esl).
        target:  platform target (mandatory CK arg) — one of W32 (PC, default)/X64/XB1/PS4.
        dry_run: default True — return the constructed command WITHOUT running. Set False to
                 actually launch CK (machine-locked, needs Steam + GPU).

    Returns ok({...}) with the constructed argv + metadata; when executed, also the exit code.
    """
    if not plugin.lower().endswith(_PLUGIN_SUFFIXES):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"plugin must end in one of {list(_PLUGIN_SUFFIXES)}", {"plugin": plugin})
    if target not in _TARGETS:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"target must be one of {list(_TARGETS)}", {"target": target})

    if cfg.fo4_install_dir is None:
        raise Fo4McpError(
            ErrorCode.ENV_FO4_NOT_DETECTED,
            "FO4 install dir not detected; cannot locate CreationKit.exe", {})
    ck = (cfg.fo4_install_dir / "CreationKit.exe").resolve()
    if not ck.exists():
        raise ToolBinaryMissingError("CreationKit.exe", str(ck))
    ck_exe = str(ck)

    command = [ck_exe, f"{_FLAG}:{plugin}", target]

    if dry_run:
        return ok({
            "command": command, "ck_exe": ck_exe, "plugin": plugin,
            "dry_run": True, "warning": _WARNING,
        })

    # execute via MO2 VFS so .nif/.dds land in the writable overwrite, not the Steam Data folder
    from .ck_run import run_ck_via_mo2

    timeout = max(cfg.subprocess_timeout, 3600)
    r = run_ck_via_mo2(cfg, command[1:], timeout=timeout)
    return ok({
        "command": command, "ck_exe": ck_exe, "plugin": plugin, "dry_run": False,
        "via": "mo2-vfs", "ok": r["exited"] and not r["timed_out"], **r,
        "warning": _WARNING,
    })
