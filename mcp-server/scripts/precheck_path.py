"""Claude Code PreToolUse hook — Karar 4 path boundary enforcement.

Reads a JSON tool-call payload from stdin and rejects writes that target
forbidden zones (Steam game folder, user docs, AppData). Hooks the
already-tested `fo4_mcp.safety` policy so enforcement matches the MCP server.

Two enforcement modes:

* Edit / Write / NotebookEdit — a single, explicit file path. Full policy via
  `check_write`: outside-repo and DENY zones both block (exit 2).
* Bash / PowerShell — best-effort. We extract likely write targets from the
  command string (redirects, tee, cp/mv/rm, dd of=, and a few PowerShell
  cmdlets) and block ONLY if one clearly lands in an absolute-forbidden zone
  (`forbidden_reason`). Everything else fails open (exit 0): shell commands
  legitimately write to temp dirs, the cwd, etc., so we must not default-deny
  them — the MCP server tools remain the authoritative gate for those.

Exit codes (Claude Code convention):
- 0  : allow the tool call
- 2  : deny the tool call; stderr is shown to the user as the block reason
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]   # C:\Modding
_PKG_ROOT  = Path(__file__).resolve().parents[1]   # C:\Modding\mcp-server

# Make `fo4_mcp` importable without installing the package.
sys.path.insert(0, str(_PKG_ROOT))

from fo4_mcp.safety import check_write, forbidden_reason  # noqa: E402
from fo4_mcp.errors import PathForbiddenError  # noqa: E402


_EXPLICIT_WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
_SHELL_TOOLS = {"Bash", "PowerShell"}

# Session-scoped write authorization (marker-gated, gitignored, removed at
# session end). The user may grant a per-session exception by creating the
# marker file; its CONTENT selects the scope (fail-closed when absent):
#   * empty / "ck-only" -> only the CK install dir (`Fallout 4 1946160`) is
#     writable. The CK is a SEPARATE Steam app whose folder gets caught by the
#     Steam read-only rule; deploying tooling there is a legitimate action.
#   * "unrestricted"    -> ALL otherwise-forbidden zones are writable (Steam
#     game folder, Docs, AppData, anywhere). Granted explicitly by the user
#     for this session (2026-06-05: "sınırsız yazma yetkisi veriyorum ...
#     dosyalar hassas değil"). Needed to merge the CK into the main game dir.
# safety.py (the MCP server policy) is UNTOUCHED — this only relaxes the hook
# that gates the assistant's own Edit/Write/Bash actions. The marker path is
# env-overridable (FO4MCP_SESSION_WRITE_MARKER) so policy unit-tests stay
# deterministic regardless of any live operator marker.
_STEAM_WRITE_MARKER = Path(
    os.environ.get("FO4MCP_SESSION_WRITE_MARKER", str(_REPO_ROOT / ".session-steam-write-ok"))
)
_CK_DIR_NEEDLE = "steamapps/common/fallout 4 1946160"


def _session_write_authorized(target: str) -> bool:
    try:
        content = _STEAM_WRITE_MARKER.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return False  # marker absent/unreadable -> fail closed
    if "unrestricted" in content:
        return True  # owner-granted full bypass for this session
    norm = str(Path(target).resolve()).replace("\\", "/").lower()
    return _CK_DIR_NEEDLE in norm


def _extract_file_path(tool_name: str, tool_input: dict) -> str | None:
    if tool_name in {"Edit", "Write"}:
        return tool_input.get("file_path")
    if tool_name == "NotebookEdit":
        return tool_input.get("notebook_path")
    return None


# Redirections: > file, >> file, 2> file, &> file, 1>> file
# Target may be a quoted path with spaces or a bare token.
_REDIRECT_RE = re.compile(
    r"""(?:^|\s)(?:\d*>>?|&>>?)\s*("[^"]*"|'[^']*'|[^\s|;&<>]+)"""
)
# PowerShell cmdlet -Path / -FilePath / -Destination values
_PS_PARAM_RE = re.compile(r"-(?:File)?Path\s+([^\s|;,]+)|-Destination\s+([^\s|;,]+)", re.IGNORECASE)
# dd of=target
_DD_OF_RE = re.compile(r"\bof=([^\s|;&]+)")

# Commands whose (non-flag) operands are write/destructive targets.
_DEST_LAST_CMDS = {"cp", "mv", "copy-item", "move-item", "rename-item"}
_ALL_OPERANDS_CMDS = {"rm", "remove-item", "del", "tee", "out-file", "set-content", "add-content"}


def _strip_quotes(s: str) -> str:
    return s.strip().strip('"').strip("'")


def _extract_shell_write_targets(command: str) -> list[str]:
    """Best-effort: pull likely write/destructive path targets from a shell
    command. Over-collection is fine (we only act on forbidden-zone hits);
    under-collection is acceptable (MCP tools are the real gate)."""
    targets: list[str] = []

    for m in _REDIRECT_RE.finditer(command):
        targets.append(_strip_quotes(m.group(1)))
    for m in _DD_OF_RE.finditer(command):
        targets.append(_strip_quotes(m.group(1)))
    for m in _PS_PARAM_RE.finditer(command):
        targets.append(_strip_quotes(m.group(1) or m.group(2)))

    # Split into simple-command segments and inspect cp/mv/rm/tee operands.
    for segment in re.split(r"[;&|\n]+", command):
        seg = segment.strip()
        if not seg:
            continue
        try:
            tokens = shlex.split(seg, posix=True)
        except ValueError:
            continue  # unbalanced quotes etc. — fail open on this segment
        if not tokens:
            continue
        cmd = tokens[0].lower().lstrip("\\./")
        operands = [t for t in tokens[1:] if not t.startswith("-")]
        if cmd in _DEST_LAST_CMDS and operands:
            targets.append(_strip_quotes(operands[-1]))
        elif cmd in _ALL_OPERANDS_CMDS:
            targets.extend(_strip_quotes(o) for o in operands)

    return [t for t in targets if t]


def _check_explicit(file_path: str) -> int:
    if _session_write_authorized(file_path):
        return 0
    try:
        check_write(file_path, _REPO_ROOT)
    except PathForbiddenError as exc:
        sys.stderr.write(f"[karar-4] {exc}\n")
        return 2
    return 0


def _check_shell(command: str) -> int:
    for target in _extract_shell_write_targets(command):
        if _session_write_authorized(target):
            continue
        reason = forbidden_reason(target)
        if reason:
            sys.stderr.write(
                f"[karar-4] shell write blocked: {target} ({reason})\n"
            )
            return 2
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # fail open on malformed input

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    if tool_name in _EXPLICIT_WRITE_TOOLS:
        file_path = _extract_file_path(tool_name, tool_input)
        return _check_explicit(file_path) if file_path else 0

    if tool_name in _SHELL_TOOLS:
        command = tool_input.get("command") or ""
        return _check_shell(command) if command else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
