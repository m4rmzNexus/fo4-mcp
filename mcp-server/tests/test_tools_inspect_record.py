"""fo4_inspect_record tests.

Pure helpers run always; the integration test serializes the committed
fixture esp via real Spriggit and is skipped if tooling is unavailable.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import (
    _extract_record_fields,
    _norm_formid,
    fo4_inspect_record,
)

from conftest import require_or_skip_mutagen_cli

_REPO = Path(__file__).resolve().parents[2]
_SPRIGGIT = _REPO / "tools" / "spriggit" / "Spriggit.CLI.exe"
_FIXTURE_ESP = _REPO / "fixtures" / "armor-swap-test" / "seed" / "test_armor.esp"


# ---- pure helpers ----

@pytest.mark.parametrize("raw,expected", [
    ("0x24A0FE", "24A0FE"),
    ("24a0fe", "24A0FE"),
    ("800", "000800"),
    ("FE000800", "000800"),
    ("000800", "000800"),
])
def test_norm_formid_ok(raw, expected):
    assert _norm_formid(raw) == expected


@pytest.mark.parametrize("raw", ["", "TestArmorSwapFlag", "zzz", "0xGG"])
def test_norm_formid_rejects_nonhex(raw):
    assert _norm_formid(raw) is None


def test_extract_record_fields():
    body = (
        "MutagenObjectType: GlobalInt\n"
        "FormKey: 000800:test_armor.esp\n"
        "EditorID: TestArmorSwapFlag\n"
        "MajorFlags:\n- Constant\n"
    )
    f = _extract_record_fields(body)
    assert f == {
        "editor_id": "TestArmorSwapFlag",
        "form_key": "000800:test_armor.esp",
        "record_type": "GlobalInt",
    }


# ---- integration ----

def _skip_if_no_spriggit():
    if not _SPRIGGIT.exists():
        pytest.skip("Spriggit not extracted")
    if not _FIXTURE_ESP.exists():
        pytest.skip("fixture esp missing")
    if shutil.which("dotnet") is None and not (Path.home() / ".dotnet" / "dotnet.exe").exists():
        pytest.skip("dotnet not found (Spriggit needs .NET 9)")


@pytest.fixture
def real_env():
    return load_config(), parse_manifest(_REPO / "tools" / "MANIFEST.md")


def test_inspect_by_editorid(real_env):
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "TestArmorSwapFlag")["data"]
    assert res["found"] is True
    assert res["matched_as"] == "editorid"
    rec = res["records"][0]
    assert rec["editor_id"] == "TestArmorSwapFlag"
    assert rec["record_type"] == "GlobalInt"
    assert rec["form_key"].startswith("000800:")


def test_inspect_by_formid(real_env):
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "0x000800")["data"]
    assert res["found"] is True
    assert res["matched_as"] == "formid"
    assert res["records"][0]["editor_id"] == "TestArmorSwapFlag"


def test_inspect_not_found(real_env):
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "NoSuchRecord")["data"]
    assert res["found"] is False
    assert res["match_count"] == 0


def test_inspect_missing_plugin_raises(real_env, tmp_path):
    cfg, manifest = real_env
    with pytest.raises(Fo4McpError):
        fo4_inspect_record(cfg, manifest, str(tmp_path / "nope.esp"), "X")


# ---- mutagen-cli fast-path backend (V2-backlog #2) ----

def _skip_if_no_mutagen_cli(real_env):
    cfg, manifest = real_env
    require_or_skip_mutagen_cli(cfg, manifest)
    if not _FIXTURE_ESP.exists():
        pytest.skip("fixture esp missing")


def test_mutagen_cli_backend_by_editorid(real_env):
    _skip_if_no_mutagen_cli(real_env)
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "TestArmorSwapFlag")["data"]
    assert res["backend"] == "mutagen-cli"
    assert res["found"] is True
    rec = res["records"][0]
    assert rec["editor_id"] == "TestArmorSwapFlag"
    assert rec["record_type"] == "GlobalInt"
    assert rec["form_key"].startswith("000800:")


def test_mutagen_cli_backend_by_formid_prefix(real_env):
    """A load-order-prefixed FormID still resolves to the low-6 object id."""
    _skip_if_no_mutagen_cli(real_env)
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "FE000800")["data"]
    assert res["backend"] == "mutagen-cli"
    assert res["matched_as"] == "formid"
    assert res["records"][0]["editor_id"] == "TestArmorSwapFlag"


def test_mutagen_cli_backend_not_found(real_env):
    _skip_if_no_mutagen_cli(real_env)
    cfg, manifest = real_env
    res = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "NoSuchRecord")["data"]
    assert res["backend"] == "mutagen-cli"
    assert res["found"] is False
    assert res["match_count"] == 0


def test_backends_agree(real_env, monkeypatch):
    """Both backends report the same key fields for the same record."""
    _skip_if_no_mutagen_cli(real_env)
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    cli = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "TestArmorSwapFlag")["data"]
    assert cli["backend"] == "mutagen-cli"
    # Force the Spriggit fallback by hiding the CLI binary.
    monkeypatch.setattr("fo4_mcp.tools._mutagen_cli_binary", lambda *a, **k: None)
    spr = fo4_inspect_record(cfg, manifest, str(_FIXTURE_ESP), "TestArmorSwapFlag")["data"]
    assert spr["backend"] == "spriggit"
    c, s = cli["records"][0], spr["records"][0]
    assert c["editor_id"] == s["editor_id"]
    assert c["record_type"] == s["record_type"]
    assert (_norm_formid(c["form_key"].split(":", 1)[0])
            == _norm_formid(s["form_key"].split(":", 1)[0]))
