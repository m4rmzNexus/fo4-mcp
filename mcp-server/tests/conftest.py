"""Shared test helpers for the mcp-server suite.

Consolidates the writer-availability skip logic that was duplicated across the
round-trip test modules. The key behavior change (OS-06): when the mutagen-cli
writer binary is absent, these helpers normally `pytest.skip` so the pure-Python
CI lane stays green — but if FO4MCP_REQUIRE_WRITER is truthy they `pytest.fail`
loudly instead, so a writer-enforcing run (local pre-commit gate) catches a
missing binary rather than silently masking a Program.cs serialization
regression.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.tools import _mutagen_cli_binary


def _require_writer_enforced() -> bool:
    """True when FO4MCP_REQUIRE_WRITER demands the writer actually run."""
    return os.environ.get("FO4MCP_REQUIRE_WRITER", "").strip().lower() in {"1", "true", "yes"}


def require_or_skip_writer(cfg, manifest) -> None:
    """Skip (or, under FO4MCP_REQUIRE_WRITER, fail) when the writer is absent."""
    if _mutagen_cli_binary(cfg, manifest) is not None:
        return
    if _require_writer_enforced():
        pytest.fail(
            "mutagen-cli writer not built but FO4MCP_REQUIRE_WRITER demands it",
            pytrace=False,
        )
    pytest.skip("mutagen-cli not built")


def require_or_skip_mutagen_cli(cfg, manifest) -> None:
    """Alias of require_or_skip_writer for the inspect-record fast-path backend.

    Same binary, same enforcement; named for the call site that gates the
    optional mutagen-cli inspect backend rather than the authoring writer.
    """
    require_or_skip_writer(cfg, manifest)
