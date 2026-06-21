"""Karar 4 path boundary unit tests.

These are pure-function tests; no filesystem mutation, no MCP runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.errors import PathForbiddenError
from fo4_mcp.safety import WriteDisposition, check_write, is_inside


REPO = Path("C:/Modding").resolve()


def test_staging_is_allow():
    assert check_write(REPO / "staging" / "out.yml", REPO) == WriteDisposition.ALLOW


def test_research_is_allow():
    assert check_write(REPO / "research" / "p0" / "mutagen" / "x.md", REPO) == WriteDisposition.ALLOW


def test_tools_is_allow():
    assert check_write(REPO / "tools" / "spriggit" / "x.zip", REPO) == WriteDisposition.ALLOW


def test_fixtures_is_diff_gated():
    assert check_write(REPO / "fixtures" / "test.esp", REPO) == WriteDisposition.ALLOW_DIFF_GATED


def test_docs_is_diff_gated():
    assert check_write(REPO / "docs" / "x.md", REPO) == WriteDisposition.ALLOW_DIFF_GATED


def test_repo_root_unmatched_is_diff_gated():
    """Files at repo root with no rule fall through to diff-gated."""
    assert check_write(REPO / "newfile.md", REPO) == WriteDisposition.ALLOW_DIFF_GATED


def test_steam_install_forbidden():
    bad = Path("C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/foo.esp")
    with pytest.raises(PathForbiddenError) as exc:
        check_write(bad, REPO)
    assert "READ-ONLY" in exc.value.message


def test_user_docs_forbidden():
    bad = Path("C:/Users/testuser/Documents/My Games/Fallout4/plugins.txt")
    with pytest.raises(PathForbiddenError):
        check_write(bad, REPO)


def test_localappdata_forbidden():
    bad = Path("C:/Users/testuser/AppData/Local/Fallout4/plugins.txt")
    with pytest.raises(PathForbiddenError):
        check_write(bad, REPO)


def test_outside_repo_forbidden():
    """Random C:\\ path that isn't in any allowlist must be denied."""
    with pytest.raises(PathForbiddenError):
        check_write(Path("C:/SomeOtherProject/x.txt"), REPO)


def test_case_insensitive():
    """NTFS is case-insensitive — STAGING should match staging."""
    assert check_write(REPO / "STAGING" / "x.txt", REPO) == WriteDisposition.ALLOW


def test_claude_plans_is_allow():
    """Claude plan files live outside the repo in ~/.claude/plans/ but the
    PreToolUse hook routes their writes through check_write(); allow them."""
    plan = Path("~/.claude/plans/some-plan.md").expanduser()
    assert check_write(plan, REPO) == WriteDisposition.ALLOW


def test_claude_memory_is_allow():
    """Auto-memory under ~/.claude/projects/<slug>/memory/ must be writable."""
    mem = Path("~/.claude/projects/C--Modding/memory/x.md").expanduser()
    assert check_write(mem, REPO) == WriteDisposition.ALLOW


def test_claude_credentials_still_forbidden():
    """The plans exception must NOT leak to the rest of ~/.claude."""
    cred = Path("~/.claude/.credentials.json").expanduser()
    with pytest.raises(PathForbiddenError):
        check_write(cred, REPO)


def test_claude_settings_still_forbidden():
    settings = Path("~/.claude/settings.json").expanduser()
    with pytest.raises(PathForbiddenError):
        check_write(settings, REPO)


def test_is_inside_helper():
    assert is_inside(REPO / "staging" / "x", REPO)
    assert not is_inside(Path("C:/Other/x"), REPO)
