"""Run a Creation Kit CLI op headlessly THROUGH MO2 so output lands in the MO2 VFS overwrite
(writable, under the repo) instead of the read-only Steam game Data folder.

PROVEN 2026-06-21: `-GeneratePreCombined:<plugin> clean all` on an authored interior cell
produced CombinedObjects.esp + <plugin> - Geometry.psg + Meshes/PreCombined/.../*.NIF in the MO2
overwrite, and CK exited cleanly; `-ExportFaceGenData:<plugin> W32` ran headless too. The Steam
folder is never written (only CKPE's own ckpe.log). CK has NO navmesh CLI flag (binary-probed:
only Generate{PreCombined,PreVisData,Lips,SingleLip,SEQ,AnimInfo,StaticCollections}), so exterior
navmesh stays Render-Window-interactive.

Mechanism: MO2 launches a registered custom-executable via `moshortcut://:<title>`, passing that
entry's stored `arguments`. MO2 reads ModOrganizer.ini at startup, so we (1) back the ini up,
(2) set the CreationKit entry's arguments to the CK op, (3) launch, (4) poll for CK to exit
(bounded — kill on timeout to avoid a GUI-modal hang), (5) ALWAYS restore the ini. Output is
collected from the VFS overwrite dir.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError

_CK_TITLE = "CreationKit"


def _read_base_directory(ini: Path, mo2_dir: Path) -> Path:
    """The MO2 [Settings] base_directory holds mods/profiles/overwrite (may differ from the exe dir)."""
    for line in ini.read_text(encoding="utf-8", errors="surrogateescape").splitlines():
        if line.strip().lower().startswith("base_directory"):
            val = line.split("=", 1)[1].strip()
            # MO2 may wrap it as @ByteArray(...) or use @\x... escapes; take the plain tail
            if val.startswith("@ByteArray(") and val.endswith(")"):
                val = val[len("@ByteArray("):-1]
            p = Path(val)
            if p.exists():
                return p
    return mo2_dir  # fallback: overwrite alongside the exe


def _ck_entry_index(ini_lines: list[str]) -> int | None:
    """Find the customExecutables index N whose N\\title == CreationKit."""
    for l in ini_lines:
        key, _, val = l.partition("=")
        if key.endswith("\\title") and val.strip() == _CK_TITLE:
            return int(key.split("\\", 1)[0])
    return None


_DEFAULT_FAILURE_MARKERS = ("ERROR", "FATAL", "failed", "Assert")


def run_ck_via_mo2(
    cfg: Config,
    ck_args: list[str],
    *,
    timeout: int = 600,
    poll: int = 20,
    expected_outputs: list[str] | None = None,
    failure_markers: tuple[str, ...] = _DEFAULT_FAILURE_MARKERS,
) -> dict[str, Any]:
    """Launch CreationKit with `ck_args` through MO2 (VFS-safe) and wait (bounded) for it to exit.

    Returns {launched, exited, timed_out, duration_s, ckpe_log_tail, overwrite_new,
    expected_outputs, missing_outputs, ckpe_errors, artifacts_ok}. Restores the MO2 ini in a
    finally block. Raises if MO2/CK or the CreationKit MO2 entry is missing.

    artifacts_ok is an INDEPENDENT gate ("did the op actually produce its artifact + no ckpe.log
    errors"): "not hanging" no longer implies success. exited/timed_out keep their old semantics.
    """
    import ctypes
    import subprocess

    if cfg.mo2_instance_dir is None:
        raise Fo4McpError(ErrorCode.ENV_FO4_NOT_DETECTED, "MO2 instance not detected", {})
    mo2_exe = cfg.mo2_instance_dir / "ModOrganizer.exe"
    ini = cfg.mo2_instance_dir / "ModOrganizer.ini"
    if not mo2_exe.exists():
        raise ToolBinaryMissingError("ModOrganizer.exe", str(mo2_exe))
    if not ini.exists():
        raise ToolBinaryMissingError("ModOrganizer.ini", str(ini))
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "CreationKit.exe").exists():
        raise ToolBinaryMissingError("CreationKit.exe",
                                     str((cfg.fo4_install_dir or Path()) / "CreationKit.exe"))

    base_dir = _read_base_directory(ini, cfg.mo2_instance_dir)
    overwrite = base_dir / "overwrite"
    ckpe_log = cfg.fo4_install_dir / "ckpe.log"

    raw = ini.read_text(encoding="utf-8", errors="surrogateescape")
    lines = raw.splitlines()
    idx = _ck_entry_index(lines)
    if idx is None:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"no MO2 custom-executable titled '{_CK_TITLE}' — add Creation Kit to MO2 first", {})

    bak = ini.with_suffix(ini.suffix + ".ckrunbak")
    shutil.copy2(ini, bak)
    arg_str = " ".join(ck_args)
    before = {str(p) for p in overwrite.rglob("*")} if overwrite.exists() else set()
    started = time.monotonic()
    timed_out = False
    try:
        # set N\arguments
        for i, l in enumerate(lines):
            key = l.split("=", 1)[0]
            if key == f"{idx}\\arguments":
                lines[i] = f"{idx}\\arguments={arg_str}"
                break
        ini.write_text("\n".join(lines) + "\n", encoding="utf-8", errors="surrogateescape")
        if ckpe_log.exists():
            try:
                ckpe_log.unlink()
            except OSError:
                pass

        # launch via ShellExecute (same as the in-game runner) — detached, shell-owned
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "open", str(mo2_exe), f"moshortcut://:{_CK_TITLE}", str(mo2_exe.parent), 1)
        if rc <= 32:
            raise Fo4McpError(ErrorCode.SUBPROCESS_FAILED,
                              f"ShellExecute failed to launch MO2 (code {rc})", {})

        # poll for CreationKit.exe to exit (it auto-exits when the CLI op completes).
        # Two completion paths: (a) seen RUNNING then gone = clean finish; (b) never seen within
        # the appear-grace = a fast op that started+exited between polls (don't wait full timeout).
        deadline = started + timeout
        appear_grace = started + 180   # MO2->CK spawn is quick; 180s is a safe upper bound
        seen = False
        while time.monotonic() < deadline:
            time.sleep(poll)
            if _proc_running("CreationKit.exe"):
                seen = True
            elif seen:
                break                                   # was running, now gone -> finished
            elif time.monotonic() > appear_grace:
                break                                   # never appeared -> already done (fast)
        timed_out = _proc_running("CreationKit.exe")     # still up at deadline -> hung
        if timed_out:
            _kill("CreationKit.exe")
        _kill("ModOrganizer.exe")
    finally:
        shutil.copy2(bak, ini)
        try:
            bak.unlink()
        except OSError:
            pass

    after = {str(p) for p in overwrite.rglob("*")} if overwrite.exists() else set()
    new_files = sorted(p for p in (after - before) if Path(p).is_file())
    overwrite_new_rel = [str(Path(p).relative_to(overwrite)) for p in new_files]
    tail = ""
    ckpe_lines: list[str] = []
    if ckpe_log.exists():
        ckpe_lines = ckpe_log.read_text(errors="surrogateescape").splitlines()
        tail = "\n".join(ckpe_lines[-12:])

    # artifact validation: did the op produce its expected output(s), and is ckpe.log clean?
    # missing_outputs/ckpe_errors are an independent gate — "not hanging" no longer == success.
    missing = [
        e for e in (expected_outputs or [])
        if not any(e.lower() in nf.lower() for nf in overwrite_new_rel)
    ]
    log_errors = [
        ln for ln in ckpe_lines
        if any(m.lower() in ln.lower() for m in failure_markers)
    ]
    return {
        "launched": True,
        "exited": not timed_out,
        "timed_out": timed_out,
        "duration_s": round(time.monotonic() - started, 1),
        "overwrite_dir": str(overwrite),
        "overwrite_new": overwrite_new_rel,
        "ckpe_log_tail": tail,
        "expected_outputs": expected_outputs or [],
        "missing_outputs": missing,
        "ckpe_errors": log_errors[:20],
        "artifacts_ok": not missing and not log_errors,
    }


def _proc_running(name: str) -> bool:
    import subprocess

    from .ingame_test import _proc_present  # exact field-0 CSV match (no substring false-positive)
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return _proc_present(out, name)


def _kill(name: str) -> None:
    import subprocess
    subprocess.run(["taskkill", "/IM", name, "/F"], capture_output=True, text=True)
