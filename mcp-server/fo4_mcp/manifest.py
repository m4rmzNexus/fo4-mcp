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

import hashlib
import logging
import re
from dataclasses import dataclass, field, replace
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
        """A usable path is RECORDED — NOT proof the file is on disk.

        Deliberately a string check only: binaries live under the gitignored
        tools/ tree and are absent in CI, so callers must be able to run unit
        tests without the file present. Use exists()/sha256_matches() for the
        on-disk integrity layer (OS-20)."""
        return self.binary_path not in ("", "TBD", "N/A") and not self.binary_path.startswith("TBD")

    @property
    def expected_sha256(self) -> str | None:
        """The recorded provenance hash, lowercased — or None if absent/N/A.

        Takes the first whitespace token so a `sha256: ABC123 (note)` line still
        yields the bare hex. Multi-line `sha256: |` blocks (dir-of-dlls entries)
        collapse to their first token, which won't match a single file — that
        path's sha256_matches() returns None (a dir is not a file)."""
        raw_val = (self.raw.get("sha256") or "").strip()
        token = raw_val.split()[0].lower() if raw_val else ""
        if not token or token in ("n/a", "tbd"):
            return None
        return token

    def resolved_path(self, repo_root: Path) -> Path | None:
        """Absolute path to the recorded binary (repo-root-relative resolved), or
        None if the entry isn't is_resolved."""
        if not self.is_resolved:
            return None
        p = Path(self.binary_path)
        return p if p.is_absolute() else (repo_root / p)

    def exists(self, repo_root: Path) -> bool:
        """True only if the recorded path resolves to an existing FILE on disk."""
        p = self.resolved_path(repo_root)
        return bool(p and p.is_file())

    def sha256_matches(self, repo_root: Path) -> bool | None:
        """True/False if a hash is recorded AND the file exists (compare them);
        None if there's nothing to compare (no recorded hash, or file absent/dir)."""
        expected = self.expected_sha256
        p = self.resolved_path(repo_root)
        if expected is None or p is None or not p.is_file():
            return None
        actual = hashlib.sha256(p.read_bytes()).hexdigest().lower()
        return actual == expected


@dataclass
class Manifest:
    tools: dict[str, ToolEntry]
    source_path: Path

    def get(self, name: str) -> ToolEntry | None:
        return self.tools.get(name.lower())

    def check_selected(self, repo_root: Path, names: list[str]) -> dict:
        """Check only requested tools. A matching .NET launcher cannot identify its managed code."""
        result = {}
        for name in dict.fromkeys(names):
            entry = self.get(name)
            if entry is None:
                result[name] = {"listed": False}
                continue
            path = entry.resolved_path(repo_root)
            status = {"listed": True, "path": str(path) if path else None,
                      "present": entry.exists(repo_root), "sha256_matches": entry.sha256_matches(repo_root)}
            expected = entry.raw.get("managed_dll_sha256")
            if path and expected:
                dll = replace(entry, binary_path=str(path.with_suffix(".dll")), raw={"sha256": expected})
                status["managed_dll"] = {"path": dll.binary_path, "present": dll.exists(repo_root),
                                         "sha256_matches": dll.sha256_matches(repo_root)}
            result[name] = status
        return result

    def integrity_report(self, repo_root: Path) -> dict[str, dict[str, object]]:
        """Per-tool resolution health (OS-20): does the manifest record a usable
        path, is that file actually present, and does it match the recorded
        sha256. 'resolved' (path recorded) ≠ 'present' (file on disk) ≠ verified.

        sha256_ok is True/False only when a hash is recorded AND the file exists;
        otherwise None. Pure read — never raises on a missing file."""
        return {
            slug: {
                "resolved":        entry.is_resolved,
                "present":         entry.exists(repo_root),
                "sha256_recorded": entry.expected_sha256 is not None,
                "sha256_ok":       entry.sha256_matches(repo_root),
            }
            for slug, entry in self.tools.items()
        }


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
