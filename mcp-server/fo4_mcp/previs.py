"""fo4_build_previs — drive Creation Kit precombine/previs generation (CLI).

The Creation Kit (with CKPE merged into the main game folder) exposes a set of
headless command-line flags that regenerate precombined meshes, previs visibility
data, and the supporting geometry/CDX files for a plugin. Verified present on this
machine 2026-06-05 (CreationKit.exe lives in the main FO4 install dir alongside
Fallout4.exe; CKPE makes the precombine/previs flags run headless).

Documented CK CLI flags:
    CreationKit.exe -GeneratePrecombined:<Plugin.esp> <filter> <area>
    CreationKit.exe -GeneratePreVisData:<Plugin.esp> <filter> <area>
    CreationKit.exe -CompressPSG:<Plugin.esp>
    CreationKit.exe -BuildCDX:<Plugin.esp>

  <filter> is "clean" or "filtered"; <area> is "all".
  CompressPSG / BuildCDX take NO filter/area argument.

The canonical full previs pipeline order is:
    1. -GeneratePrecombined  (clean all)   -> Data\\Meshes\\Precombined
    2. -CompressPSG                          -> <Plugin> - Geometry.csg
    3. -BuildCDX                             -> <Plugin> - Geometry.cdx
    4. -GeneratePreVisData   (clean all)   -> Data\\Vis

REALITY-CHECK (project core rule): a real CK previs run is LONG (often hours),
machine-locked (CK grabs the GPU/display), and irreversible (it rewrites Data).
It is therefore USER-TRIGGERED. This function defaults to dry_run=True: it
resolves the binary, constructs + validates the exact argv, and returns the
commands WITHOUT executing. Only dry_run=False actually spawns CK.

CK owns its own Data\\ output for this operation, so the long run's outputs are
NOT gated through check_write — the run is the user's explicit trigger. We do
surface a warning about the cost and about the FE-space (ESL) previs limitation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok

# step -> CK flag stem; bool = takes <filter> <area> trailing args
_STEPS: dict[str, tuple[str, bool]] = {
    "precombined": ("-GeneratePrecombined", True),
    "previs":      ("-GeneratePreVisData", True),
    "compress_psg": ("-CompressPSG", False),
    "build_cdx":   ("-BuildCDX", False),
}

# canonical previs pipeline order for step="full"
_FULL_ORDER = ("precombined", "compress_psg", "build_cdx", "previs")

_VALID_FILTERS = ("clean", "filtered")
_PLUGIN_SUFFIXES = (".esp", ".esm", ".esl")

_WARNING = (
    "long machine-locked run; outputs land in game Data\\Meshes\\Precombined, "
    "Data\\Vis, <plugin> - Geometry.csg; FE-space(ESL) cells cannot hold previs"
)


def _build_argv(ck_exe: str, step: str, plugin: str, filter: str, area: str) -> list[str]:
    """Construct the exact argv for a single CK step."""
    flag, takes_filter = _STEPS[step]
    argv = [ck_exe, f"{flag}:{plugin}"]
    if takes_filter:
        argv += [filter, area]
    return argv


def fo4_build_previs(
    cfg: Config,
    plugin: str,
    *,
    step: str = "precombined",
    filter: str = "clean",
    area: str = "all",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Construct (and optionally execute) CK precombine/previs commands for a plugin.

    Args:
        plugin:  plugin filename (must end .esp/.esm/.esl).
        step:    one of {"precombined","previs","compress_psg","build_cdx","full"}.
                 "full" = the canonical pipeline [precombined, compress_psg,
                 build_cdx, previs] in order.
        filter:  "clean" or "filtered" (only used by precombined/previs steps).
        area:    area token, normally "all".
        dry_run: default True — return the constructed commands WITHOUT running.
                 Set False to actually launch CK (long, machine-locked).

    Returns ok({...}) with the constructed argv list(s) and metadata. When
    executed, also returns each command's exit code.
    """
    # ---- validation ----
    if step not in _STEPS and step != "full":
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"step must be one of {sorted(_STEPS) + ['full']}",
            {"step": step},
        )
    if filter not in _VALID_FILTERS:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"filter must be one of {list(_VALID_FILTERS)}",
            {"filter": filter},
        )
    if not plugin.lower().endswith(_PLUGIN_SUFFIXES):
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"plugin must end in one of {list(_PLUGIN_SUFFIXES)}",
            {"plugin": plugin},
        )

    # ---- binary resolution (CK lives in the game install, not the manifest) ----
    if cfg.fo4_install_dir is None:
        raise Fo4McpError(
            ErrorCode.ENV_FO4_NOT_DETECTED,
            "FO4 install dir not detected; cannot locate CreationKit.exe",
            {},
        )
    ck = (cfg.fo4_install_dir / "CreationKit.exe").resolve()
    if not ck.exists():
        raise ToolBinaryMissingError("CreationKit.exe", str(ck))
    ck_exe = str(ck)

    # ---- argv construction ----
    steps = _FULL_ORDER if step == "full" else (step,)
    commands = [_build_argv(ck_exe, s, plugin, filter, area) for s in steps]

    if dry_run:
        return ok({
            "commands": commands,
            "ck_exe":   ck_exe,
            "plugin":   plugin,
            "step":     step,
            "dry_run":  True,
            "warning":  _WARNING,
        })

    # ---- execute via MO2 VFS so output lands in the writable overwrite, NOT the Steam Data
    # folder (proven 2026-06-21; launching CK directly would write the read-only game dir). ----
    from .ck_run import run_ck_via_mo2

    timeout = max(cfg.subprocess_timeout, 3600)
    results: list[dict[str, Any]] = []
    all_ok = True
    for cmd in commands:
        # cmd[0] is ck_exe; MO2 launches CK itself, so pass only the CK flag args
        r = run_ck_via_mo2(cfg, cmd[1:], timeout=timeout)
        all_ok = all_ok and r["exited"] and not r["timed_out"]
        results.append({"argv": cmd, **r})

    return ok({
        "commands": commands,
        "ck_exe":   ck_exe,
        "plugin":   plugin,
        "step":     step,
        "dry_run":  False,
        "via":      "mo2-vfs",
        "ok":       all_ok,
        "results":  results,
        "warning":  _WARNING,
    })
