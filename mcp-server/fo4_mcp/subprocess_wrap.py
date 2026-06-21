"""Subprocess runner — every external tool goes through here.

Why centralized: GPL-3.0 license isolation requires a clean process
boundary, and we want one place to enforce timeouts, capture stderr,
strip ANSI codes, and log invocations for debugging. Tools never call
`subprocess.run` directly.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import SubprocessFailedError, ToolBinaryMissingError

log = logging.getLogger(__name__)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


@dataclass(frozen=True)
class ToolResult:
    cmd: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def run_tool(
    binary: str | Path,
    args: list[str],
    *,
    cwd: str | Path | None = None,
    timeout: int = 120,
    env_extra: dict[str, str] | None = None,
    check: bool = False,
) -> ToolResult:
    """Run an external CLI tool and capture its output.

    Args:
        binary:    path to executable
        args:      argv list (NOT shell-joined; passed verbatim)
        cwd:       working dir, default = current
        timeout:   wall clock seconds; raises SubprocessFailedError on timeout
        env_extra: extra env vars merged into os.environ for the child
        check:     if True, non-zero exit raises SubprocessFailedError

    Returns ToolResult with stripped (no-ANSI) stdout/stderr.

    Raises:
        ToolBinaryMissingError if `binary` doesn't exist on disk.
        SubprocessFailedError if check=True and exit != 0, or on timeout.
    """
    binary_path = Path(binary)
    if not binary_path.exists():
        raise ToolBinaryMissingError(binary_path.name, str(binary_path))

    cmd = [str(binary_path), *args]
    log.debug("run_tool: %s (cwd=%s timeout=%ds)", cmd, cwd, timeout)

    import os
    full_env = {**os.environ, **(env_extra or {})}

    try:
        proc = subprocess.run(  # noqa: S603 — args list, no shell
            cmd,
            cwd=str(cwd) if cwd else None,
            timeout=timeout,
            capture_output=True,
            text=True,
            env=full_env,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        log.warning("run_tool timed out: %s after %ds", cmd[0], timeout)
        result = ToolResult(
            cmd=cmd,
            exit_code=-1,
            stdout=_strip_ansi(e.stdout or ""),
            stderr=_strip_ansi(e.stderr or "") + f"\n[fo4-mcp] timed out after {timeout}s",
            timed_out=True,
        )
        if check:
            raise SubprocessFailedError(cmd, -1, result.stderr) from e
        return result

    result = ToolResult(
        cmd=cmd,
        exit_code=proc.returncode,
        stdout=_strip_ansi(proc.stdout or ""),
        stderr=_strip_ansi(proc.stderr or ""),
        timed_out=False,
    )

    if check and not result.ok:
        raise SubprocessFailedError(cmd, result.exit_code, result.stderr)

    return result


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub("", s)
