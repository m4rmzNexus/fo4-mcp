"""fo4_analyze_crash_log + parse_crash_log unit tests.

Uses the committed fixtures under fixtures/crash-log-test/seed/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.tools import fo4_analyze_crash_log, parse_crash_log

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "fixtures" / "crash-log-test" / "seed"
BUFFOUT = SEED / "crash-2026-05-15-buffout-sample.log"
ADDICTOL = SEED / "crash-2026-05-15-addictol-sample.log"


def _cfg(tmp_path: Path) -> Config:
    return Config(
        repo_root=REPO,
        fo4_install_dir=None,
        fo4_user_docs=None,
        fo4_localappdata=None,
        mo2_instance_dir=None,
        tools_dir=tmp_path / "tools",
        log_level="INFO",
        subprocess_timeout=120,
    )


# ---- pure parser ----

def test_parse_buffout_header_and_exception():
    p = parse_crash_log(BUFFOUT.read_text(encoding="utf-8"))
    assert p["game_version"] == "1.10.984"
    assert p["crash_generator"] == {"name": "Buffout 4", "version": "1.31.1"}
    assert p["exception"]["type"] == "EXCEPTION_ACCESS_VIOLATION"
    assert p["exception"]["module"] == "Fallout4.exe"
    assert p["exception"]["offset"] == "2D5FE96"


def test_parse_buffout_culprit_is_third_party_module():
    p = parse_crash_log(BUFFOUT.read_text(encoding="utf-8"))
    # BetterConsole.dll is the only non-engine frame -> top culprit.
    assert p["probable_culprits"][0]["module"] == "BetterConsole.dll"
    assert "BetterConsole.dll" in p["verdict"]


def test_parse_buffout_xse_plugins():
    p = parse_crash_log(BUFFOUT.read_text(encoding="utf-8"))
    names = {x["name"] for x in p["xse_plugins"]}
    assert {"f4se_1_10_984.dll", "Buffout4.dll", "BetterConsole.dll"} <= names


def test_parse_buffout_plugins_and_light_flag():
    p = parse_crash_log(BUFFOUT.read_text(encoding="utf-8"))
    by_name = {pl["name"]: pl for pl in p["plugins"]}
    assert by_name["Fallout4.esm"]["load_index"] == "00"
    assert by_name["Fallout4.esm"]["light"] is False
    assert by_name["SimSettlements2.esm"]["load_index"] == "FE:001"
    assert by_name["SimSettlements2.esm"]["light"] is True
    assert by_name["MyTestArmor.esp"]["load_index"] == "06"


def test_parse_addictol_generator():
    p = parse_crash_log(ADDICTOL.read_text(encoding="utf-8"))
    assert p["crash_generator"] == {"name": "Addictol", "version": "1.2.0"}
    assert p["probable_culprits"][0]["module"] == "Workshop Framework.dll" or \
        p["probable_culprits"][0]["module"].endswith(".dll")


def test_parse_garbage_warns():
    p = parse_crash_log("this is not a crash log\njust some text\n")
    assert p["exception"] is None
    assert any("Unhandled exception" in w for w in p["warnings"])
    assert "unable to determine" in p["verdict"]


# ---- tool wrapper ----

def test_tool_reads_fixture(tmp_path):
    res = fo4_analyze_crash_log(_cfg(tmp_path), _manifest_stub(), str(BUFFOUT))
    assert res["ok"]
    d = res["data"]
    assert d["analyzer"] == "native"
    assert d["crash_log"] == str(BUFFOUT)
    assert d["plugin_count"] == 9


def test_tool_missing_file_raises(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_analyze_crash_log(_cfg(tmp_path), _manifest_stub(), str(tmp_path / "nope.log"))


# Minimal manifest stub — analyze_crash_log only checks classic presence.
class _ManifestStub:
    def get(self, name):
        return None


def _manifest_stub():
    return _ManifestStub()
