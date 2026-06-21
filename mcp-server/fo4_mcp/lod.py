"""fo4_build_lod — construct + validate an xLODGen invocation for FO4 LOD.

xLODGen (sheson, beta 132) is a **GUI fork of xEdit**; the binary lives at
``tools/xlodgen/xLODGen/xLODGenx64.exe``. It has NO clean headless batch mode:
``-autoload``/``-autoexit`` only skip the *module-selection* dialog — the LOD
**options window** (worldspace selection + Terrain/Object/Tree checkboxes +
"Build meshes" click) is INTERACTIVE and CANNOT be driven to completion
headlessly. See ``research/p0/xlodgen/2026-06-05-cli-probe.md``.

Therefore this tool does NOT claim to generate LOD. It:
  1. resolves the xLODGen binary,
  2. constructs + validates the exact argv,
  3. gates the output dir through check_write (staging/ or fixtures/ only),
  4. defaults to dry_run=True, returning the command for the user to run
     interactively (e.g. as an MO2 tool — the MO2 VFS supplies the load order),
  5. only with dry_run=False launches the process — and even then it BLOCKS on
     the GUI (worldspace select + Build meshes), so the headless path is for
     users who explicitly accept the interactive run.

Verified argv (research/p0/xlodgen/2026-06-05-cli-probe.md):
    xLODGenx64.exe -fo4 -o:"<outdir>" [-d:<datapath>] [-p:<pluginspath>]
                   [-m:<inipath>] -lodgen -autoload -autoexit

  -fo4       FO4 game mode.
  -o:"<dir>" output dir (no space after the colon). REQUIRED.
  -d:<dir>   Data/ folder (for MO2 VFS / non-default setups).
  -p:<file>  plugins.txt path.
  -m:<dir>   INI folder.
  -lodgen    xEdit "LODGen" tool mode.
  -autoload  skip Module Selection dialog (load active plugins.txt).
  -autoexit  close xLODGen after a mode finishes.

LICENSE: **UNVERIFIED.** xLODGen ships no clear license file in the beta-132
archive (it is an xEdit fork; xEdit is MPL-2.0, but xLODGen's redistribution
terms are not confirmed here). Confirm before distributing any generated output
or the binary itself. Surfaced in the returned envelope ("license" field).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok
from .safety import check_write
from .subprocess_wrap import run_tool

# Relative to cfg.tools_dir — the archive nests one level (xlodgen/xLODGen/).
_XLODGEN_REL = Path("xlodgen") / "xLODGen" / "xLODGenx64.exe"

_LICENSE_NOTE = "UNVERIFIED — confirm before distributing output"
_INTERACTIVE_NOTE = "worldspace select + Build meshes is GUI-only"


def _resolve_xlodgen(cfg: Config, manifest: Any | None) -> Path:
    """Resolve the xLODGenx64.exe path.

    Prefer a manifest key "xlodgen" if one is ever wired; otherwise fall back
    to ``cfg.tools_dir / xlodgen/xLODGen/xLODGenx64.exe``. Raises
    ToolBinaryMissingError if the resolved file is absent.
    """
    binary: Path | None = None
    if manifest is not None:
        entry = manifest.get("xlodgen")
        if entry is not None and entry.is_resolved:
            binary = Path(entry.binary_path)
            if not binary.is_absolute():
                binary = (cfg.repo_root / binary).resolve()
    if binary is None:
        binary = (cfg.tools_dir / _XLODGEN_REL).resolve()

    if not binary.exists():
        raise ToolBinaryMissingError("xlodgen", str(binary))
    return binary


def fo4_build_lod(
    cfg: Config,
    output_dir: str,
    *,
    data_path: str | None = None,
    plugins_path: str | None = None,
    ini_path: str | None = None,
    dry_run: bool = True,
    manifest: Any | None = None,
) -> dict[str, Any]:
    """Construct (and optionally launch) an xLODGen LOD-build invocation.

    Args:
        output_dir:   LOD output folder. Resolved against repo_root if relative.
                      Gated to staging/ or fixtures/ (Steam/Data -> forbidden).
        data_path:    optional Data/ folder (-d:). Pass-through; not resolved.
        plugins_path: optional plugins.txt (-p:). Pass-through; not resolved.
        ini_path:     optional INI folder (-m:). Pass-through; not resolved.
        dry_run:      default True — return the constructed argv WITHOUT running.
                      False launches the process (still blocks on the GUI).
        manifest:     optional Manifest; used only if a "xlodgen" key is wired.

    Returns ok({...}) with the argv, the resolved exe, the output dir, and
    loud interactive/license caveats. With dry_run=False it also includes the
    subprocess exit code and output tails.
    """
    # ---- binary resolution ----
    binary = _resolve_xlodgen(cfg, manifest)

    # ---- output gate ----
    out = Path(output_dir)
    if not out.is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)  # raises PathForbiddenError on DENY

    # ---- argv construction (verified order) ----
    # -o:"<dir>" — no space after the colon. We pass the path glued to the flag
    # as a single argv token (run_tool does not shell-join, so no quoting needed).
    args: list[str] = ["-fo4", f"-o:{out}"]
    if data_path is not None:
        args.append(f"-d:{data_path}")
    if plugins_path is not None:
        args.append(f"-p:{plugins_path}")
    if ini_path is not None:
        args.append(f"-m:{ini_path}")
    args += ["-lodgen", "-autoload", "-autoexit"]

    command = [str(binary), *args]

    payload: dict[str, Any] = {
        "command": command,
        "xlodgen_exe": str(binary),
        "output_dir": str(out),
        "dry_run": dry_run,
        "interactive_step_required": _INTERACTIVE_NOTE,
        "license": _LICENSE_NOTE,
    }

    if dry_run:
        return ok(payload)

    # ---- execute (user explicitly accepted the interactive run) ----
    # This will STILL block on the GUI (worldspace select + Build meshes); it is
    # not a headless generation. Long timeout because a real LOD run is minutes
    # to hours. We mkdir the gated output dir so xLODGen can write into it.
    out.mkdir(parents=True, exist_ok=True)
    result = run_tool(binary, args, timeout=cfg.subprocess_timeout)
    payload["exit_code"] = result.exit_code
    payload["ok"] = result.ok
    payload["stdout_tail"] = result.stdout[-1500:]
    payload["stderr_tail"] = result.stderr[-1500:]
    payload["note"] = (
        "process launched; xLODGen still requires the interactive options "
        "window (worldspace + Build meshes) to actually generate LOD"
    )
    return ok(payload)
