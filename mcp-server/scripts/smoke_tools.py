"""Subprocess smoke test for fo4-mcp toolchain.

Runs `--help` / `--version` / `-?` against every binary the MCP server
will eventually invoke, records exit codes + first lines of stdout/stderr,
and writes a markdown report to research/p0/smoke-tests/.

Intent: prove the binary exists, the subprocess wrapper is correctly
wired, and we know the argv pattern for each tool. This unblocks Phase D
(TBD resolution) and Phase E (MCP tool stub implementation) — without it
we'd be guessing argv on the fly.

Not all tools have a CLI surface. GUI-only tools (xEdit GUI mode, BodySlide,
MaterialEditor, CAO, NifSkope) are still probed for resilience but soft-fail
is expected; the report flags them as `gui` rather than `error`.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "mcp-server"))

from fo4_mcp.subprocess_wrap import run_tool, ToolResult  # noqa: E402
from fo4_mcp.errors import ToolBinaryMissingError  # noqa: E402


@dataclass
class Probe:
    label: str
    binary: Path
    args: list[str]
    kind: str = "cli"  # "cli" | "gui" (gui = expect non-zero / GUI launch)
    timeout: int = 20


_PROBES: list[Probe] = [
    Probe(
        "spriggit",
        _REPO_ROOT / "tools" / "spriggit" / "Spriggit.CLI.exe",
        ["--help"],
    ),
    Probe(
        "synthesis",
        _REPO_ROOT / "tools" / "synthesis" / "Synthesis.exe",
        ["--help"],
        kind="gui",  # Synthesis.exe = WPF runner UI; help may pop a window or exit
    ),
    Probe(
        "caprica",
        _REPO_ROOT / "tools" / "caprica" / "Caprica.exe",
        ["--help"],
    ),
    Probe(
        "champollion",
        _REPO_ROOT / "tools" / "champollion" / "Champollion.exe",
        ["--help"],
    ),
    Probe(
        "classic",
        _REPO_ROOT / "tools" / "classic" / "CLASSIC.exe",
        ["--help"],
        timeout=30,
    ),
    Probe(
        "loot",
        _REPO_ROOT / "tools" / "loot" / "loot_0.29.1-0-g77f3ba9_0.29.1" / "LOOT.exe",
        ["--help"],
        kind="gui",
    ),
    Probe(
        "xedit",
        _REPO_ROOT / "tools" / "xedit" / "xFOEdit64.exe",
        ["-?"],
        kind="gui",
    ),
    Probe(
        "bsarch",
        _REPO_ROOT / "tools" / "xedit" / "BSArch.exe",
        [],
        timeout=10,
    ),
    Probe(
        "ck-papyrus",
        Path(r"C:/Program Files (x86)/Steam/steamapps/common/Fallout 4 1946160/Papyrus Compiler/PapyrusCompiler.exe"),
        ["/?"],
    ),
]


def _truncate(s: str, max_chars: int = 400) -> str:
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + f"\n... (+{len(s) - max_chars} more chars)"


def _format_row(p: Probe, result: ToolResult | str) -> str:
    if isinstance(result, str):
        return f"### {p.label} — `MISSING`\n\nBinary not found at `{p.binary}`. {result}\n"

    status = "ok" if result.ok else ("gui" if p.kind == "gui" else "non-zero")
    head = (
        f"### {p.label} — `{status}` (exit={result.exit_code}, timeout={result.timed_out})\n\n"
        f"**Command:** `{p.label}` `{ ' '.join(p.args) or '(no args)'}`\n"
        f"**Binary:** `{p.binary}`\n"
    )
    body = ""
    if result.stdout.strip():
        body += f"\n**stdout (first {min(len(result.stdout), 400)} chars):**\n\n```\n{_truncate(result.stdout)}\n```\n"
    if result.stderr.strip():
        body += f"\n**stderr (first {min(len(result.stderr), 400)} chars):**\n\n```\n{_truncate(result.stderr)}\n```\n"
    return head + body


def main() -> int:
    out_dir = _REPO_ROOT / "research" / "p0" / "smoke-tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{date.today().isoformat()}-results.md"

    lines: list[str] = [
        f"# Subprocess smoke test results — {date.today().isoformat()}",
        "",
        "Session 4 Phase B output. Each tool was probed with `--help` (or `-?` / `/?`) ",
        "via `fo4_mcp.subprocess_wrap.run_tool()`. GUI-only tools are tagged `gui` and ",
        "soft-fail is expected; only `error` rows need follow-up.",
        "",
        "## Summary",
        "",
        "| Tool | Status | Exit | Notes |",
        "|---|---|---|---|",
    ]

    rows: list[tuple[str, str]] = []
    details: list[str] = []

    for probe in _PROBES:
        print(f"[smoke] {probe.label} ...", end=" ", flush=True)
        try:
            result = run_tool(probe.binary, probe.args, timeout=probe.timeout)
        except ToolBinaryMissingError as exc:
            print("MISSING")
            rows.append((probe.label, f"missing | n/a | {exc.details.get('expected_path', '')}"))
            details.append(_format_row(probe, "ToolBinaryMissingError"))
            continue
        status = "ok" if result.ok else ("gui" if probe.kind == "gui" else "non-zero")
        print(f"exit={result.exit_code} status={status}")
        rows.append((probe.label, f"{status} | {result.exit_code} | timeout={result.timed_out}"))
        details.append(_format_row(probe, result))

    for label, info in rows:
        lines.append(f"| {label} | {info} |")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Detail")
    lines.append("")
    lines.extend(details)

    out_file.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[smoke] wrote {out_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
