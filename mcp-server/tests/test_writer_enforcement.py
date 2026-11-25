"""Meta-test for the OS-06 writer-enforcement gate.

Proves that the shared require_or_skip_writer helper flips behavior on the
FO4MCP_REQUIRE_WRITER env-var WITHOUT needing the real binary: with the writer
forced absent (monkeypatch -> None), the helper skips by default but FAILS
loudly when the flag is set. This is the regression guard the rest of the suite
relies on -- if someone breaks the enforcement branch, a writer-absent
FO4MCP_REQUIRE_WRITER=1 run would silently go back to skipping.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import conftest
from conftest import require_or_skip_mutagen_cli, require_or_skip_writer


def _force_no_writer(monkeypatch):
    """Make the writer resolve as absent regardless of the dev box's state."""
    monkeypatch.setattr(conftest, "_mutagen_cli_binary", lambda *a, **k: None)


def test_skips_when_writer_absent_and_flag_unset(monkeypatch):
    _force_no_writer(monkeypatch)
    monkeypatch.delenv("FO4MCP_REQUIRE_WRITER", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_or_skip_writer(None, None)


def test_fails_when_writer_absent_and_flag_set(monkeypatch):
    _force_no_writer(monkeypatch)
    monkeypatch.setenv("FO4MCP_REQUIRE_WRITER", "1")
    with pytest.raises(pytest.fail.Exception):
        require_or_skip_writer(None, None)


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "Yes", " yes "])
def test_truthy_flag_values_all_fail(monkeypatch, val):
    _force_no_writer(monkeypatch)
    monkeypatch.setenv("FO4MCP_REQUIRE_WRITER", val)
    with pytest.raises(pytest.fail.Exception):
        require_or_skip_writer(None, None)


@pytest.mark.parametrize("val", ["0", "false", "no", "", "off"])
def test_falsey_flag_values_still_skip(monkeypatch, val):
    _force_no_writer(monkeypatch)
    monkeypatch.setenv("FO4MCP_REQUIRE_WRITER", val)
    with pytest.raises(pytest.skip.Exception):
        require_or_skip_writer(None, None)


def test_no_skip_or_fail_when_writer_present(monkeypatch):
    """When the binary resolves, the helper returns cleanly even with the flag set."""
    monkeypatch.setattr(conftest, "_mutagen_cli_binary", lambda *a, **k: Path("mutagen-cli.exe"))
    monkeypatch.setenv("FO4MCP_REQUIRE_WRITER", "1")
    require_or_skip_writer(None, None)  # must not raise


def test_mutagen_cli_alias_mirrors_writer_gate(monkeypatch):
    """The inspect-backend alias shares the same enforcement semantics."""
    _force_no_writer(monkeypatch)
    monkeypatch.setenv("FO4MCP_REQUIRE_WRITER", "1")
    with pytest.raises(pytest.fail.Exception):
        require_or_skip_mutagen_cli(None, None)
    monkeypatch.delenv("FO4MCP_REQUIRE_WRITER", raising=False)
    with pytest.raises(pytest.skip.Exception):
        require_or_skip_mutagen_cli(None, None)
