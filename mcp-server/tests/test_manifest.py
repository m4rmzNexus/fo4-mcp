"""Manifest parser tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.manifest import _parse_yaml_block, _slug, parse_manifest


def test_slug_basic():
    assert _slug("Spriggit") == "spriggit"
    assert _slug("Mutagen.Bethesda") == "mutagen"
    assert _slug("CLASSIC (evildarkarchon CLI fork)") == "classic"
    assert _slug("Mod Organizer 2") == "mod"  # acceptable: first word


def test_parse_simple_block():
    block = """name: Spriggit
version: 0.40.1
license: GPL-3.0
"""
    kv = _parse_yaml_block(block)
    assert kv["name"] == "Spriggit"
    assert kv["version"] == "0.40.1"
    assert kv["license"] == "GPL-3.0"


def test_parse_multiline_notes():
    block = """name: Spriggit
version: 0.40.1
notes: |
  ESP <-> YAML serialization.
  GPL-3.0 - subprocess-wrap zorunlu.
"""
    kv = _parse_yaml_block(block)
    assert "ESP" in kv["notes"]
    assert "subprocess-wrap" in kv["notes"]


def test_parse_real_manifest(tmp_path: Path):
    manifest_text = """# header

```yaml
name: Spriggit
version: 0.40.1
source: https://github.com/Mutagen-Modding/Spriggit/releases/tag/0.40.1
asset: SpriggitCLI.zip
binary_path: TBD
license: GPL-3.0
downloaded: 2026-05-10
sha256: abc123
```

some prose

```yaml
name: Caprica
version: v0.3.0
binary_path: tools/caprica/Caprica.exe
license: MIT
```
"""
    p = tmp_path / "MANIFEST.md"
    p.write_text(manifest_text, encoding="utf-8")

    m = parse_manifest(p)
    assert "spriggit" in m.tools
    assert "caprica" in m.tools
    assert m.tools["spriggit"].version == "0.40.1"
    assert m.tools["spriggit"].is_resolved is False  # binary_path = TBD
    assert m.tools["caprica"].is_resolved is True


def test_missing_manifest(tmp_path: Path):
    """Missing file -> empty manifest, not a crash."""
    m = parse_manifest(tmp_path / "nonexistent.md")
    assert m.tools == {}
