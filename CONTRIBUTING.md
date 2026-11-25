# Contributing to fo4-mcp

Thanks for your interest. fo4-mcp is an MCP server that exposes a Fallout 4
modding toolchain (Mutagen, Spriggit, Caprica, Buffout/Addictol, …) to AI
agents. This guide covers setup and the few hard rules that keep the project's
license clean and its writes safe.

## Project layout

- `mcp-server/` — the server (Python, FastMCP). All tool logic + tests live here.
- `tools/` — third-party binaries, **downloaded, never committed** (gitignored).
  Inventory + provenance: `tools/MANIFEST.md`; fetch instructions:
  `tools/MANUAL-DOWNLOADS.txt`.
- `skills/` — Claude Code skill pack.
- `fixtures/` — minimal, copyright-free test inputs.
- `docs/` — decisions (`phase-0-decisions.md`), backlog, license strategy.

## Dev setup

Requires **Python ≥ 3.11**. For the full toolchain-backed tests you also need
the .NET 8 **and** 9 SDKs (Spriggit serialization targets net9.0) plus the
binaries described in `tools/MANIFEST.md` — but the pure-Python suite runs
without any of that.

```bash
cd mcp-server
pip install -e ".[dev]"
pytest -q
```

Tests that need an external tool (Spriggit, mutagen-cli, Caprica, JDK, MO2) are
`pytest.skip`-gated and simply skip when the binary is absent — which is also
how CI runs them. Compiled artifacts under `fixtures/` (`.pex`, `.pas`) are
**regenerated** by the tests from their `.psc` sources; don't commit build
output.

When you have the mutagen-cli writer built locally, run the writer-enforcing
variant before committing changes to the authoring path:

```bash
FO4MCP_REQUIRE_WRITER=1 pytest -q
```

`FO4MCP_REQUIRE_WRITER` (truthy: `1`/`true`/`yes`, case-insensitive) flips the
writer-gated round-trip tests from *skip* to *fail* when the binary is missing,
so a silently-absent writer can't hide a `Program.cs` serialization regression.
Leave it unset for the pure-Python lane (the default, and how CI runs).

## Hard rules

These are enforced by CI and a local PreToolUse hook — please don't work around
them:

1. **No in-process GPL.** GPL-3.0 tools are invoked **subprocess-only**
   (`subprocess_wrap.run_tool()`). Never `import` them and never link via
   pythonnet/`clr`. This is what keeps fo4-mcp itself MIT-licensed — see
   `docs/karar-7-license-strategy.md`. CI fails on a forbidden import.
2. **Safe-write boundary.** Never write into the Steam game folder, the user's
   `Documents/My Games/Fallout4`, or `LocalAppData/Fallout4` — they are
   read-only data sources. Generated output goes to `staging/`; tracked edits
   to `fixtures/` are diff-gated. Policy: `docs/phase-0-decisions.md` (Karar 4),
   enforced by `mcp-server/fo4_mcp/safety.py`.
3. **No secrets, no copyrighted game assets.** `secrets/` is gitignored; never
   commit API keys. Fixtures must be original/synthetic — no vanilla Bethesda
   meshes, textures, voice, or dialogue.

## Conventions

- Match the surrounding style; `ruff` config is in `mcp-server/pyproject.toml`
  (line length 100).
- Add a test for every behavior change; keep `pytest -q` green.
- Surgical diffs — change only what the task needs.

## Pull requests

Keep PRs focused, describe the change and how you verified it, and make sure the
three CI jobs (pytest, GPL-import firewall, privacy guard) pass.
