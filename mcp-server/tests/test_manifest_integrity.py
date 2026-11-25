"""ToolEntry/Manifest on-disk integrity layer (OS-20).

`is_resolved` only proves a path is RECORDED; these methods prove the file is
actually present and (when a provenance hash is recorded) matches it. Pure —
exercised with synthetic entries + tmp files, no real tool binaries needed."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.manifest import Manifest, ToolEntry


def _entry(binary_path: str, sha: str | None = None) -> ToolEntry:
    raw = {"sha256": sha} if sha is not None else {}
    return ToolEntry(name="X", version="1", source="", asset="",
                     binary_path=binary_path, license="", raw=raw)


def test_unresolved_entry_has_no_disk_identity(tmp_path):
    e = _entry("TBD")
    assert e.is_resolved is False
    assert e.resolved_path(tmp_path) is None
    assert e.exists(tmp_path) is False
    assert e.sha256_matches(tmp_path) is None


def test_resolved_but_absent_file(tmp_path):
    e = _entry("tools/ghost.exe")
    assert e.is_resolved is True          # path recorded ...
    assert e.exists(tmp_path) is False    # ... but not on disk
    assert e.sha256_matches(tmp_path) is None


def test_present_file_without_recorded_hash(tmp_path):
    f = tmp_path / "tools" / "real.exe"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"binary")
    e = _entry("tools/real.exe")
    assert e.exists(tmp_path) is True
    assert e.expected_sha256 is None
    assert e.sha256_matches(tmp_path) is None  # nothing to compare


def test_sha256_match_and_mismatch(tmp_path):
    f = tmp_path / "real.exe"
    f.write_bytes(b"payload")
    good = hashlib.sha256(b"payload").hexdigest().upper()  # MANIFEST stores uppercase
    e_ok = _entry(str(f), sha=good)
    assert e_ok.expected_sha256 == good.lower()
    assert e_ok.sha256_matches(tmp_path) is True
    e_bad = _entry(str(f), sha="deadbeef")
    assert e_bad.sha256_matches(tmp_path) is False


def test_expected_sha256_strips_note_and_handles_na():
    assert _entry("x", sha="ABC123 (provenance note)").expected_sha256 == "abc123"
    assert _entry("x", sha="N/A").expected_sha256 is None
    assert _entry("x", sha="").expected_sha256 is None


def test_directory_binary_path_is_not_a_file(tmp_path):
    d = tmp_path / "tools" / "vc110"
    d.mkdir(parents=True)
    e = _entry("tools/vc110")
    assert e.is_resolved is True
    assert e.exists(tmp_path) is False    # a directory is not a usable binary file


def test_integrity_report_shape(tmp_path):
    f = tmp_path / "present.exe"
    f.write_bytes(b"z")
    sha = hashlib.sha256(b"z").hexdigest()
    m = Manifest(tools={
        "good":  _entry(str(f), sha=sha),
        "ghost": _entry("tools/missing.exe"),
        "tbd":   _entry("TBD"),
    }, source_path=Path("x"))
    rep = m.integrity_report(tmp_path)
    assert rep["good"] == {
        "resolved": True, "present": True, "sha256_recorded": True, "sha256_ok": True}
    assert rep["ghost"]["resolved"] is True and rep["ghost"]["present"] is False
    assert rep["ghost"]["sha256_ok"] is None
    assert rep["tbd"]["resolved"] is False and rep["tbd"]["present"] is False
