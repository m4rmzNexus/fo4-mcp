"""Parse `tools/MANIFEST.md` to discover binary paths.

The manifest is a markdown doc with one fenced YAML block per tool. We
intentionally don't require strict schema — fields can be `TBD` and the
parser just records that. fo4-mcp tools call `manifest.get('spriggit')`
and decide what to do (raise ToolBinaryMissingError if path is TBD or
file doesn't exist).

A real implementation could lean on PyYAML, but for now we do a naive
fenced-block scan to keep dependencies minimal — if pydantic/yaml is
available later, swap in a stricter parser without touching callers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolEntry:
    name: str
    version: str
    source: str
    asset: str
    binary_path: str   # 'TBD' if not yet resolved
    license: str
    raw: dict[str, str] = field(default_factory=dict)

    @property
    def is_resolved(self) -> bool:
        return self.binary_path not in ("", "TBD", "N/A") and not self.binary_path.startswith("TBD")


@dataclass
class Manifest:
    tools: dict[str, ToolEntry]
    source_path: Path

    def get(self, name: str) -> ToolEntry | None:
        return self.tools.get(name.lower())


# ---- Parsing -----------------------------------------------------------------

_YAML_BLOCK_RE = re.compile(r"```yaml\s*(.+?)```", re.DOTALL)
_KV_RE = re.compile(r"^([a-z_][a-z0-9_]*)\s*:\s*(.*)$", re.IGNORECASE)


def _parse_yaml_block(block: str) -> dict[str, str]:
    """Naive line-oriented YAML key:value parser. Multi-line `|` blocks
    are joined with newlines, indentation stripped. Sufficient for our
    flat MANIFEST entries."""
    out: dict[str, str] = {}
    current_key: str | None = None
    multiline: list[str] = []

    for raw_line in block.splitlines():
        line = raw_line.rstrip()
        if not line:
            if current_key is not None:
                multiline.append("")
            continue

        m = _KV_RE.match(line.lstrip())
        if m and not raw_line.startswith(("  ", "\t")):
            # New top-level key — flush prior multiline.
            if current_key is not None:
                out[current_key] = "\n".join(multiline).strip()
                multiline = []
                current_key = None

            key, val = m.group(1).lower(), m.group(2).strip()
            if val == "|":
                current_key = key
                multiline = []
            else:
                out[key] = val
        elif current_key is not None:
            # Continuation of multiline block.
            multiline.append(raw_line.strip())

    if current_key is not None:
        out[current_key] = "\n".join(multiline).strip()

    return out


def parse_manifest(path: Path) -> Manifest:
    """Parse MANIFEST.md and return a Manifest with one entry per yaml block.

    Tool name is taken from the `name:` field, lowercased and slugged.
    """
    if not path.exists():
        log.warning("manifest not found: %s", path)
        return Manifest(tools={}, source_path=path)

    text = path.read_text(encoding="utf-8")
    tools: dict[str, ToolEntry] = {}

    for block in _YAML_BLOCK_RE.findall(text):
        kv = _parse_yaml_block(block)
        if "name" not in kv:
            continue
        slug = _slug(kv["name"])
        tools[slug] = ToolEntry(
            name        = kv.get("name", ""),
            version     = kv.get("version", ""),
            source      = kv.get("source", ""),
            asset       = kv.get("asset", ""),
            binary_path = kv.get("binary_path", "TBD"),
            license     = kv.get("license", ""),
            raw         = kv,
        )

    log.debug("parsed %d tools from %s", len(tools), path)
    return Manifest(tools=tools, source_path=path)


def _slug(name: str) -> str:
    """Slug a tool name to a stable lookup key.

    'Spriggit' -> 'spriggit'
    'Mutagen.Bethesda' -> 'mutagen'
    'CLASSIC (evildarkarchon CLI fork)' -> 'classic'
    """
    base = name.lower().split()[0].split(".")[0].split("(")[0]
    return base.strip()
