"""fo4_plan_plugin_format / fo4_set_master_flag tests (Faz 3 / W0).

Pure TES4 header rewrite (0x0001 ESM bit) mirroring esl_flag, plus the format
advisor. Eligibility is monkeypatched (no Spriggit/writer needed) to exercise the
new-cell verdict paths and the light+new-cell refuse guard.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp import plugin_format
from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.esl_flag import _read_tes4_flags
from fo4_mcp.plugin_format import (
    _required_format,
    _set_master_flag_bytes,
    fo4_plan_plugin_format,
    fo4_set_master_flag,
)

_MAGIC = b"TES4"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _tes4(flags: int, body: bytes = b"") -> bytes:
    return (
        _MAGIC
        + struct.pack("<I", len(body))   # dataSize
        + struct.pack("<I", flags)
        + struct.pack("<I", 0)           # formID
        + struct.pack("<I", 0)           # versionControl
        + struct.pack("<H", 131)         # formVersion (AE)
        + struct.pack("<H", 0)           # unknown
        + body
    )


def _fake_elig(verdict: str):
    return lambda cfg, path: {
        "verdict": verdict, "reasons": [f"reason for {verdict}"],
        "new_cell_or_worldspace_count": 1 if verdict == "esm-flag" else 0,
    }


# ---------------- pure helpers ----------------

def test_set_master_flag_bytes_roundtrip():
    body = b"HEDR\x0c\x00arbitrary body bytes"
    base = _tes4(0x000, body)
    patched, old, new = _set_master_flag_bytes(base, True)
    assert old is False and new is True
    assert _read_tes4_flags(patched) == 0x001
    assert patched[24:] == base[24:]            # body untouched
    assert len(patched) == len(base)
    restored, old2, new2 = _set_master_flag_bytes(patched, False)
    assert old2 is True and new2 is False
    assert restored == base                      # full round-trip


def test_set_master_flag_preserves_light_bit():
    # flipping ESM must not disturb the light bit (0x0200)
    patched, _, _ = _set_master_flag_bytes(_tes4(0x200), True)
    assert _read_tes4_flags(patched) == 0x201


def test_required_format_mapping():
    assert _required_format("esm-flag")[0] == "esm-flagged-esp"
    assert _required_format("esl-eligible")[0] == "esl-flagged-esp"
    assert _required_format("no-new-records")[0] == "override-only-esp"
    assert _required_format("bogus")[0] == "unknown"


# ---------------- set_master_flag writer ----------------

def test_set_master_flag_writes_flagged_copy(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    data = fo4_set_master_flag(cfg, str(src), "staging/master.esp", enable=True)["data"]
    assert data["old_master"] is False and data["new_master"] is True
    written = (tmp_path / "staging" / "master.esp").read_bytes()
    assert _read_tes4_flags(written) & 0x001


def test_set_master_flag_disable(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x001, b"HEDR body"))
    data = fo4_set_master_flag(cfg, str(src), "staging/cleared.esp", enable=False)["data"]
    assert data["old_master"] is True and data["new_master"] is False
    written = (tmp_path / "staging" / "cleared.esp").read_bytes()
    assert not (_read_tes4_flags(written) & 0x001)


def test_set_master_flag_forbidden_output_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000))
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.esp"
    with pytest.raises(PathForbiddenError):
        fo4_set_master_flag(cfg, str(src), forbidden, enable=True)


def test_set_master_flag_backs_up_existing(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    (tmp_path / "staging").mkdir()
    (tmp_path / "staging" / "out.esp").write_bytes(_tes4(0x001, b"old"))
    data = fo4_set_master_flag(cfg, str(src), "staging/out.esp", enable=True)["data"]
    assert data["bak_path"] is not None and Path(data["bak_path"]).exists()


def test_set_master_flag_non_tes4_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "notesp.bin"
    src.write_bytes(b"PK\x03\x04nope")
    with pytest.raises(Fo4McpError):
        fo4_set_master_flag(cfg, str(src), "staging/x.esp", enable=True)


def test_set_master_flag_refuses_light_plus_new_cell(tmp_path, monkeypatch):
    # the W0 corruption guard: light-flagged AND new cells -> hard refuse
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esm-flag"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "light_with_cell.esp"
    src.write_bytes(_tes4(0x200, b"HEDR body"))  # light-flagged
    with pytest.raises(Fo4McpError):
        fo4_set_master_flag(cfg, str(src), "staging/x.esp", enable=True)
    # nothing written on refuse
    assert not (tmp_path / "staging" / "x.esp").exists()


def test_set_master_flag_warns_when_not_required(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esl-eligible"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "esl.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    data = fo4_set_master_flag(cfg, str(src), "staging/over.esp", enable=True)["data"]
    assert data["new_master"] is True
    assert data["warning"] is not None and "not 'esm-flag'" in data["warning"]


def test_set_master_flag_new_cell_no_light_proceeds(tmp_path, monkeypatch):
    # new cells + NOT light -> correct ESM action, no refuse, no warning
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esm-flag"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "newcell.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    data = fo4_set_master_flag(cfg, str(src), "staging/esm.esp", enable=True)["data"]
    assert data["new_master"] is True and data["warning"] is None


# ---------------- plan_plugin_format advisor ----------------

def test_plan_new_cell_recommends_esm(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esm-flag"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "newcell.esp"
    src.write_bytes(_tes4(0x000))  # no flags yet
    data = fo4_plan_plugin_format(cfg, str(src))["data"]
    assert data["required_format"] == "esm-flagged-esp"
    assert data["current_matches_required"] is False
    assert any("ESM master flag is OFF" in c for c in data["conflicts"])


def test_plan_light_with_new_cell_is_critical_conflict(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esm-flag"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "light.esp"
    src.write_bytes(_tes4(0x200))  # light-flagged + (fake) new cells
    data = fo4_plan_plugin_format(cfg, str(src))["data"]
    assert any("CRITICAL" in c for c in data["conflicts"])


def test_plan_esl_eligible_recommends_light(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_format, "_eligibility", _fake_elig("esl-eligible"))
    cfg = _cfg(tmp_path)
    src = tmp_path / "esl.esp"
    src.write_bytes(_tes4(0x000))
    data = fo4_plan_plugin_format(cfg, str(src))["data"]
    assert data["required_format"] == "esl-flagged-esp"
    assert data["current_matches_required"] is True


def test_plan_degrades_without_writer(tmp_path, monkeypatch):
    monkeypatch.setattr(plugin_format, "_eligibility", lambda cfg, path: None)
    cfg = _cfg(tmp_path)
    src = tmp_path / "x.esp"
    src.write_bytes(_tes4(0x000))
    data = fo4_plan_plugin_format(cfg, str(src))["data"]
    assert data["eligibility_verdict"] == "unknown"
    assert data["warning"] is not None


def test_plan_missing_file_raises(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(Fo4McpError):
        fo4_plan_plugin_format(cfg, str(tmp_path / "nope.esp"))
