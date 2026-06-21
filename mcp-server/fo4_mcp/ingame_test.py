"""fo4_run_ingame_test — drive a headless FO4 in-game test (Tier 3 RE / Faz 2.2b).

This is the orchestration half of the proven in-game test runner. It:
  1. Renders a job file (save-load directive + FormID resolves + console command
     list) that the native F4SE runner plugin reads.
  2. Launches the game through MO2 headlessly.
  3. Waits for the plugin to auto-quit (qqq) — or kills a hang.
  4. Judges success by grepping Papyrus.0.log for the job's success_pattern, and
     reports the plugin's flush-on-write diag trace.

The native half (commonlibf4-template plugin) bakes in the hard-won lessons:
FormID-not-editorID resolution, kQuickLoad (not kLoadMostRecentSave),
GetParentCell() in-game polling, flush-on-write diag under tools/.

REALITY-CHECK (project core rule): a real run launches the game (long,
machine-locked, needs Steam logged in), so this mirrors fo4_build_previs —
dry_run=True (default) renders the job + launch plan WITHOUT writing or
launching; only dry_run=False actually drives the game.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import Config
from .errors import ErrorCode, Fo4McpError, ToolBinaryMissingError, ok

_PLUGIN_SUFFIXES = (".esp", ".esm", ".esl")
_KEY_RE = re.compile(r"^[A-Za-z0-9]+$")
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z0-9]+)\}")

# These MUST match the constants baked into the native plugin (src/main.cpp).
_JOB_REL = ("commonlibf4-template", "ingame-job.txt")
_DIAG_REL = ("commonlibf4-template", "runner-diag.log")


# ---- job rendering (pure) -----------------------------------------------------

def _bad(msg: str, details: dict[str, Any] | None = None) -> Fo4McpError:
    return Fo4McpError(ErrorCode.INVALID_ARGUMENT, msg, details or {})


def _norm_formid(v: Any) -> str:
    """Normalize a raw object-FormID to '0xHEX'. Bare strings are read as HEX
    (modding convention); ints are taken as-is. Must fit the 24-bit object id."""
    if isinstance(v, bool):  # bool is an int subclass — reject explicitly
        raise _bad("resolve.form_id must be an int or hex string, not bool")
    if isinstance(v, int):
        n = v
    elif isinstance(v, str):
        s = v.strip().lower()
        if not s:
            raise _bad("resolve.form_id is empty")
        try:
            n = int(s, 16)
        except ValueError as e:
            raise _bad(f"resolve.form_id not hex: {v!r}") from e
    else:
        raise _bad(f"resolve.form_id must be an int or hex string, got {type(v).__name__}")
    if not 0 <= n <= 0xFFFFFF:
        raise _bad(f"resolve.form_id raw must be 0..0xFFFFFF (object id within plugin), got {n:#x}")
    return f"0x{n:X}"


def render_job(spec: dict[str, Any]) -> str:
    """Render the line-based job file the runner plugin reads. Pure + validating.

    spec keys:
        commands         required list[str]; console commands, {KEY} placeholders
        resolves         optional [{key, plugin, form_id}]; {KEY} -> runtime FormID
        save             "quickload" (default) | "mostrecent" | "coc:<cell>"
        settle_ms/gap_ms/post_ms   optional timing ints
    (success_pattern / *_timeout_s are consumed by the orchestrator, not the job.)
    """
    if not isinstance(spec, dict):
        raise _bad("spec must be a dict")

    commands = spec.get("commands")
    if not isinstance(commands, list) or not commands:
        raise _bad("spec.commands must be a non-empty list of strings")
    for c in commands:
        if not isinstance(c, str) or not c.strip():
            raise _bad("each spec.commands entry must be a non-empty string", {"command": c})
        if "\n" in c or "\r" in c:
            raise _bad("a command may not contain newlines (job file is line-based)", {"command": c})

    # save directive
    save = str(spec.get("save", "quickload")).strip()
    if save in ("quickload", "mostrecent"):
        save_line = f"save {save}"
    elif save.startswith("coc:"):
        cell = save[len("coc:"):].strip()
        if not cell or re.search(r"\s", cell):
            raise _bad("coc cell must be a single whitespace-free token", {"save": save})
        save_line = f"save coc {cell}"
    else:
        raise _bad("spec.save must be 'quickload', 'mostrecent', or 'coc:<cell>'", {"save": save})

    # resolves
    resolves = spec.get("resolves") or []
    if not isinstance(resolves, list):
        raise _bad("spec.resolves must be a list")
    res_lines: list[str] = []
    keys: set[str] = set()
    for r in resolves:
        if not isinstance(r, dict):
            raise _bad("each resolve must be a dict {key, plugin, form_id}", {"resolve": r})
        key = str(r.get("key", "")).strip()
        plugin = str(r.get("plugin", "")).strip()
        if not _KEY_RE.match(key):
            raise _bad("resolve.key must be alphanumeric", {"key": key})
        if key in keys:
            raise _bad(f"duplicate resolve key {key!r}")
        keys.add(key)
        if not plugin.lower().endswith(_PLUGIN_SUFFIXES):
            raise _bad(f"resolve.plugin must end in one of {list(_PLUGIN_SUFFIXES)}", {"plugin": plugin})
        if re.search(r"\s", plugin):
            raise _bad("resolve.plugin may not contain whitespace", {"plugin": plugin})
        res_lines.append(f"resolve {key} {plugin} {_norm_formid(r.get('form_id'))}")

    # every {KEY} used by a command must be a declared resolve
    used = set(_PLACEHOLDER_RE.findall(" ".join(commands)))
    unknown = used - keys
    if unknown:
        raise _bad(f"commands reference undefined resolve keys: {sorted(unknown)}", {"keys": sorted(keys)})

    def _ms(name: str, default: int) -> int:
        v = spec.get(name, default)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            raise _bad(f"spec.{name} must be a non-negative int", {name: v})
        return v

    # navtest: poll an actor's pathing state to prove an authored navmesh is
    # in-game valid. spec.navtest = {npc: <resolve key>, sample_ms?, duration_s?}.
    nav_line: str | None = None
    nav = spec.get("navtest")
    if nav is not None:
        if not isinstance(nav, dict):
            raise _bad("spec.navtest must be a dict {npc, sample_ms?, duration_s?}", {"navtest": nav})
        npc = str(nav.get("npc", "")).strip()
        if npc not in keys:
            raise _bad("navtest.npc must reference a declared resolve key", {"npc": npc, "keys": sorted(keys)})

        def _navint(name: str, default: int) -> int:
            v = nav.get(name, default)
            if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                raise _bad(f"navtest.{name} must be a positive int", {name: v})
            return v

        nav_line = f"navtest {npc} {_navint('sample_ms', 1000)} {_navint('duration_s', 15)}"

    lines = ["# fo4-mcp in-game test job (generated; do not edit by hand)", save_line]
    lines += res_lines
    lines += [f"settle_ms {_ms('settle_ms', 4000)}",
              f"gap_ms {_ms('gap_ms', 1500)}",
              f"post_ms {_ms('post_ms', 8000)}"]
    if nav_line:
        lines.append(nav_line)
    lines += [f"cmd {c.strip()}" for c in commands]
    return "\n".join(lines) + "\n"


# ---- live process helpers (Windows; system utilities, not GPL tools) ----------

_SYS32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"


def _launch_detached(exe: Path, arg: str) -> None:
    """Launch MO2 via ShellExecute — the way PowerShell's Start-Process does.

    This matters (proven by A/B test): a plain subprocess.Popen leaves the game
    attached to our console / job object, so its window message pump never runs —
    it loads (RAM climbs, kGameLoaded fires) but F4SE's AddUITask queue never
    drains and the test sequence never fires. ShellExecute has the *shell* create
    the process, so it lands in the interactive session with a normal window
    station and the UI loop pumps normally. Fire-and-forget; we poll by image."""
    import ctypes  # noqa: PLC0415 — Windows-only, lazy

    rc = ctypes.windll.shell32.ShellExecuteW(None, "open", str(exe), arg, str(exe.parent), 1)
    if rc <= 32:  # ShellExecute returns >32 on success
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED,
            f"ShellExecute failed to launch {exe.name} (code {rc})",
            {"exe": str(exe), "code": rc},
        )


def _tasklist_ws_mb(image: str) -> int | None:
    """Working-set MB of a running process by image name; None if not running.
    Used to tell a real game (WS>200MB) from the ~25MB Steam DRM stub."""
    try:
        out = subprocess.run(  # noqa: S603 — system utility, fixed argv
            [str(_SYS32 / "tasklist.exe"), "/fi", f"imagename eq {image}", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue  # "INFO: No tasks..." when absent
        fields = [f.strip('"') for f in line.split('","')]
        if len(fields) >= 5 and fields[0].lower() == image.lower():
            mem = fields[-1].upper().replace(",", "").replace("K", "").strip()
            if mem.isdigit():
                return int(mem) // 1024
    return None


def _kill(image: str) -> None:
    try:
        subprocess.run(  # noqa: S603 — system utility, fixed argv
            [str(_SYS32 / "taskkill.exe"), "/f", "/im", image],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.SubprocessError, OSError):
        pass


def _steam_active_user() -> int | None:
    """Steam's logged-in user id (0 = logged out), or None if unreadable."""
    try:
        import winreg  # noqa: PLC0415 — Windows-only, imported lazily
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as k:
            val, _ = winreg.QueryValueEx(k, "ActiveUser")
            return int(val)
    except (OSError, ValueError):
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---- orchestration ------------------------------------------------------------

def fo4_run_ingame_test(
    cfg: Config,
    spec: dict[str, Any],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Render the job, then (dry_run=False) launch FO4 via MO2 and judge the run.

    Returns ok({...}). dry_run=True returns the rendered job + launch plan only.
    A live run blocks for up to appear_timeout_s + run_timeout_s seconds.
    """
    job_text = render_job(spec)  # validates everything first

    success_pattern = spec.get("success_pattern")
    if success_pattern is not None and not isinstance(success_pattern, str):
        raise _bad("spec.success_pattern must be a string")
    appear_timeout = int(spec.get("appear_timeout_s", 240))
    run_timeout = int(spec.get("run_timeout_s", 180))

    tmpl = cfg.tools_dir / _JOB_REL[0]
    job_path = cfg.tools_dir.joinpath(*_JOB_REL)
    diag_path = cfg.tools_dir.joinpath(*_DIAG_REL)

    mo2_exe = (cfg.mo2_instance_dir / "ModOrganizer.exe") if cfg.mo2_instance_dir else None
    papyrus = (cfg.fo4_user_docs / "Logs" / "Script" / "Papyrus.0.log") if cfg.fo4_user_docs else None

    plan = {
        "job_path": str(job_path),
        "job_text": job_text,
        "mo2_exe": str(mo2_exe) if mo2_exe else None,
        "launch_argv": [str(mo2_exe), "moshortcut://:F4SE"] if mo2_exe else None,
        "papyrus_log": str(papyrus) if papyrus else None,
        "diag_log": str(diag_path),
        "success_pattern": success_pattern,
        "appear_timeout_s": appear_timeout,
        "run_timeout_s": run_timeout,
    }

    if dry_run:
        return ok({**plan, "dry_run": True,
                   "note": "dry_run: job NOT written, game NOT launched. Set dry_run=false to run."})

    # ---- execute (long, machine-locked, user-triggered) ----
    if mo2_exe is None:
        raise Fo4McpError(ErrorCode.ENV_FO4_NOT_DETECTED,
                          "MO2 instance not detected; cannot launch the game", {})
    if not mo2_exe.exists():
        raise ToolBinaryMissingError("ModOrganizer.exe", str(mo2_exe))

    active = _steam_active_user()
    if active == 0:
        raise Fo4McpError(
            ErrorCode.ENV_FO4_NOT_DETECTED,
            "Steam is not logged in (ActiveUser=0); FO4 would launch as a ~25MB DRM stub "
            "and the plugin never injects. Log into Steam first.",
            {"steam_active_user": 0},
        )

    if not tmpl.is_dir():
        raise Fo4McpError(ErrorCode.PATH_NOT_FOUND,
                          f"runner plugin dir not found: {tmpl} (build/deploy the plugin first)", {})
    job_path.write_text(job_text, encoding="utf-8")

    for img in ("Fallout4.exe", "ModOrganizer.exe", "f4se_loader.exe"):
        _kill(img)
    time.sleep(2)

    _launch_detached(mo2_exe, "moshortcut://:F4SE")

    # 1) wait for a REAL game (WS>200MB = not the 25MB DRM stub)
    appeared = False
    appear_after = 0
    for appear_after in range(appear_timeout):
        mb = _tasklist_ws_mb("Fallout4.exe")
        if mb is not None and mb > 200:
            appeared = True
            break
        time.sleep(1)

    # 2) the runner auto-quits after load + commands + post delay; watch for exit
    exited = False
    run_seconds = 0
    peak_ram = 0
    if appeared:
        for run_seconds in range(run_timeout):
            mb = _tasklist_ws_mb("Fallout4.exe")
            if mb is None:
                exited = True
                break
            peak_ram = max(peak_ram, mb)
            time.sleep(1)
        if not exited:
            _kill("Fallout4.exe")
    _kill("ModOrganizer.exe")

    # 3) collect + judge
    diag_text = _read_text(diag_path)
    papyrus_matches: list[str] = []
    if papyrus and papyrus.exists() and success_pattern:
        for line in _read_text(papyrus).splitlines():
            if success_pattern in line:
                papyrus_matches.append(line)

    sequence_completed = "[seq] UI: qqq" in diag_text
    plugin_timed_out = "TIMEOUT 120s" in diag_text

    # navtest verdict (if this was a navmesh pathing run): the DLL emits one
    # summary line "[NAVTEST] ... VERDICT=PASS|FAIL" with the parsed metrics.
    navmesh_verdict: dict[str, Any] | None = None
    for line in diag_text.splitlines():
        if line.startswith("[NAVTEST]") and "VERDICT=" in line:
            m = dict(re.findall(r"(\w+)=([-\d.A-Z]+)", line))
            navmesh_verdict = {
                "verdict": m.get("VERDICT"),
                "any_pathing": m.get("anyPathing") == "1",
                "any_path_valid": m.get("anyPathValid") == "1",
                "on_navmesh": m.get("on_navmesh") == "1",
                "moved": float(m["moved"]) if "moved" in m else None,
                "samples": int(m["samples"]) if "samples" in m else None,
                "line": line,
            }

    if success_pattern:
        success = appeared and bool(papyrus_matches)
    else:
        success = appeared and exited and sequence_completed

    return ok({
        **plan,
        "dry_run": False,
        "success": success,
        "appeared": appeared,
        "appear_after_s": appear_after,
        "exited": exited,
        "run_seconds": run_seconds,
        "peak_ram_mb": peak_ram,
        "killed_hung": appeared and not exited,
        "steam_active_user": active,
        "sequence_completed": sequence_completed,
        "plugin_timed_out": plugin_timed_out,
        "papyrus_matches": papyrus_matches[:20],
        "navmesh_verdict": navmesh_verdict,
        "diag_tail": diag_text.splitlines()[-25:],
    })
