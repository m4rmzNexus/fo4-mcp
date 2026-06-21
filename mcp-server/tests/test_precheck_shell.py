"""Bash/PowerShell-aware hook tests (Phase G1).

Covers the shell write-target extractor and the forbidden_reason gate. The
contract: shell gating is fail-open — only an absolute-forbidden-zone write
blocks; temp/cwd/relative writes pass.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.safety import forbidden_reason

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "precheck_path.py"

# Import the extractor from the hook script module.
import importlib.util

_spec = importlib.util.spec_from_file_location("precheck_path", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_extract = _mod._extract_shell_write_targets


STEAM = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.esp"
DOCS = "C:/Users/testuser/Documents/My Games/Fallout4/plugins.txt"


# ---- extractor ----

def test_extract_redirect():
    assert "out.txt" in _extract("echo hi > out.txt")
    assert "log.txt" in _extract("cmd 2>> log.txt")


def test_extract_tee():
    assert "file.txt" in _extract("echo x | tee file.txt")


def test_extract_cp_mv_dest():
    assert _extract("cp a.txt b.txt")[-1] == "b.txt"
    assert "dest.esp" in _extract("mv src.esp dest.esp")


def test_extract_rm_all_operands():
    got = _extract("rm a.tmp b.tmp")
    assert "a.tmp" in got and "b.tmp" in got


def test_extract_powershell_params():
    got = _extract("Set-Content -Path C:/x/y.txt -Value z")
    assert "C:/x/y.txt" in got


def test_extract_unbalanced_quotes_fails_open():
    # Should not raise; returns whatever it could parse.
    _extract('echo "unterminated > out.txt')


# ---- forbidden_reason gate ----

def test_forbidden_reason_steam():
    assert forbidden_reason(STEAM) is not None


def test_forbidden_reason_docs():
    assert forbidden_reason(DOCS) is not None


def test_forbidden_reason_temp_is_allowed():
    assert forbidden_reason("C:/Users/testuser/AppData/Local/Temp/x.txt") is None


def test_forbidden_reason_repo_is_allowed():
    assert forbidden_reason("C:/Modding/staging/x.txt") is None


# ---- end-to-end via the hook process ----

def _run_hook(payload: dict) -> int:
    # Point the session-write marker at a path that cannot exist, so these
    # policy tests assert the DEFAULT (fail-closed) behavior regardless of any
    # live operator session-override marker on disk.
    env = {**os.environ, "FO4MCP_SESSION_WRITE_MARKER": str(_SCRIPT.parent / "__no_such_marker__")}
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode


def test_hook_blocks_bash_write_to_steam():
    rc = _run_hook({"tool_name": "Bash", "tool_input": {"command": f'echo x > "{STEAM}"'}})
    assert rc == 2


def test_hook_allows_bash_write_to_temp():
    rc = _run_hook({"tool_name": "Bash", "tool_input": {"command": "echo x > $TEMP/out.txt"}})
    assert rc == 0


def test_hook_blocks_rm_in_docs():
    rc = _run_hook({"tool_name": "Bash", "tool_input": {"command": f'rm "{DOCS}"'}})
    assert rc == 2


def test_hook_allows_normal_bash():
    rc = _run_hook({"tool_name": "Bash", "tool_input": {"command": "ls -la && python -m pytest"}})
    assert rc == 0


def test_hook_blocks_powershell_setcontent_to_steam():
    rc = _run_hook({
        "tool_name": "PowerShell",
        "tool_input": {"command": f'Set-Content -Path "{STEAM}" -Value x'},
    })
    assert rc == 2
