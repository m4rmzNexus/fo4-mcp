"""fo4_check_esl_eligibility tests.

Two layers:
  * pure-logic tests for _esl_verdict + _record_data_modkey (no Spriggit needed)
  * one integration test against the committed fixture esp; skipped if the
    Spriggit binary / fixture / net9 dotnet is unavailable.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import load_config
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import (
    _esl_verdict,
    _record_data_modkey,
    fo4_check_esl_eligibility,
)

_REPO = Path(__file__).resolve().parents[2]
_SPRIGGIT = _REPO / "tools" / "spriggit" / "Spriggit.CLI.exe"
_FIXTURE_ESP = _REPO / "fixtures" / "armor-swap-test" / "seed" / "test_armor.esp"


# ---------------- pure logic ----------------

def test_record_data_modkey():
    body = "SpriggitSource:\n  PackageName: x\nModKey: test_armor.esp\nGameRelease: Fallout4\n"
    assert _record_data_modkey(body) == "test_armor.esp"
    assert _record_data_modkey("GameRelease: Fallout4\n") is None
    # ModKey nested under another key must NOT match (top-level only)
    assert _record_data_modkey("ModHeader:\n  ModKey: nope.esp\n") is None


def test_verdict_esl_eligible_clean():
    verdict, reasons = _esl_verdict(new_count=10, max_object_id=0x900, new_cell_count=0)
    assert verdict == "esl-eligible"
    assert not any("WARN" in r for r in reasons)


def test_verdict_esl_eligible_but_below_spid_floor():
    verdict, reasons = _esl_verdict(new_count=1, max_object_id=0x200, new_cell_count=0)
    assert verdict == "esl-eligible"
    assert any("0x800" in r and "SPID" in r for r in reasons)


def test_verdict_esm_when_new_cells():
    verdict, _ = _esl_verdict(new_count=5, max_object_id=0x810, new_cell_count=2)
    assert verdict == "esm-flag"  # cells win over everything


def test_verdict_needs_compaction_over_ceiling():
    verdict, _ = _esl_verdict(new_count=100, max_object_id=0x1234, new_cell_count=0)
    assert verdict == "esl-needs-compaction"


def test_verdict_plain_esp_too_many_records():
    verdict, _ = _esl_verdict(new_count=5000, max_object_id=0x500, new_cell_count=0)
    assert verdict == "plain-esp"


def test_verdict_no_new_records():
    verdict, _ = _esl_verdict(new_count=0, max_object_id=-1, new_cell_count=0)
    assert verdict == "no-new-records"


def test_verdict_boundary_2048_records_at_ceiling():
    # exactly at both limits is still eligible (<=)
    verdict, _ = _esl_verdict(new_count=2048, max_object_id=0xFFF, new_cell_count=0)
    assert verdict == "esl-eligible"


# ---------------- integration (real Spriggit) ----------------

def _skip_if_no_spriggit():
    if not _SPRIGGIT.exists():
        pytest.skip(f"Spriggit not extracted at {_SPRIGGIT}")
    if not _FIXTURE_ESP.exists():
        pytest.skip(f"fixture esp missing at {_FIXTURE_ESP}")
    if shutil.which("dotnet") is None and not (Path.home() / ".dotnet" / "dotnet.exe").exists():
        pytest.skip("dotnet not found (Spriggit needs .NET 9)")


def test_check_esl_eligibility_real_fixture():
    _skip_if_no_spriggit()
    cfg = load_config()
    manifest = parse_manifest(_REPO / "tools" / "MANIFEST.md")
    res = fo4_check_esl_eligibility(cfg, manifest, str(_FIXTURE_ESP))
    assert res["ok"] is True
    data = res["data"]
    assert data["mod_key"] == "test_armor.esp"
    assert data["new_record_count"] == 1
    assert data["max_object_id"] == "0x800"
    assert data["new_cell_or_worldspace_count"] == 0
    assert data["verdict"] == "esl-eligible"


def test_scan_serialized_records_counts_folder_layout(tmp_path):
    """Regression: Spriggit serializes complex records (quests/cells/npcs) as a
    FOLDER `<Type>/<rec>/RecordData.yaml`, simple ones as a flat file. The scan
    must count BOTH (skipping only the top-level mod header by path), and detect a
    new cell via its type folder. Reproduces the bug where every folder-style
    record was dropped (skip-by-name) -> 'no-new-records' for any real quest mod."""
    from fo4_mcp.tools import _scan_serialized_records

    out = tmp_path / "yaml"
    (out).mkdir()
    header = out / "RecordData.yaml"
    header.write_text("ModKey: MyMod.esp\n", encoding="utf-8")            # mod header (skip)

    (out / "Globals").mkdir()
    (out / "Globals" / "MyFlag - 000801_MyMod.esp.yaml").write_text(      # flat simple record
        "FormKey: 000801:MyMod.esp\nEditorID: MyFlag\n", encoding="utf-8")

    qd = out / "Quests" / "MyQuest - 000802_MyMod.esp"; qd.mkdir(parents=True)
    (qd / "RecordData.yaml").write_text(                                  # folder-style (the bug case)
        "FormKey: 000802:MyMod.esp\nEditorID: MyQuest\n", encoding="utf-8")

    cd = out / "Cells" / "0" / "MyCell - 000803_MyMod.esp"; cd.mkdir(parents=True)
    (cd / "RecordData.yaml").write_text(                                  # NEW cell -> forces esm
        "FormKey: 000803:MyMod.esp\nEditorID: MyCell\n", encoding="utf-8")

    od = out / "Weapons" / "VanillaGun - 0001F3_Fallout4.esm"; od.mkdir(parents=True)
    (od / "RecordData.yaml").write_text(                                  # override -> master, not new
        "FormKey: 0001F3:Fallout4.esm\nEditorID: VanillaGun\n", encoding="utf-8")

    new_count, max_oid, cells, masters = _scan_serialized_records(out, header, "MyMod.esp")
    assert new_count == 3                  # global + quest + cell (NOT the header, NOT the override)
    assert max_oid == 0x803
    assert len(cells) == 1                 # the new cell, detected via the "Cells" type folder
    assert "Fallout4.esm" in masters
