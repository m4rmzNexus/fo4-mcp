"""W12 support tools — fo4_navmesh_handoff + fo4_release_preflight (read-only).

Gating tests run always; integration tests drive the real mutagen-cli writer +
cell-navmesh-list verb and are skipped if it is not built.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import (
    _mutagen_cli_binary,
    fo4_create_record,
    fo4_navmesh_handoff,
    fo4_release_preflight,
    fo4_voice_handoff,
)

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = parse_manifest(_REPO / "tools" / "MANIFEST.md")


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


# ---------------- gating ----------------

def test_navmesh_handoff_missing_plugin(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_navmesh_handoff(_cfg(tmp_path), _MANIFEST, "staging/does-not-exist.esp")


def test_release_preflight_missing_plugin(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_release_preflight(_cfg(tmp_path), _MANIFEST, "staging/nope.esp")


def test_voice_handoff_missing_plugin(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_voice_handoff(_cfg(tmp_path), _MANIFEST, "staging/no-voice.esp")


# ---------------- integration: real writer + cell-navmesh-list verb ----------------

@pytest.fixture
def real_env():
    return load_config(), _MANIFEST


@pytest.fixture
def staging_out():
    d = _REPO / "staging" / "w12-handoff-test"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _skip_if_no_writer(cfg, manifest):
    if _mutagen_cli_binary(cfg, manifest) is None:
        pytest.skip("mutagen-cli not built")


def _navmesh_cell_spec(editor_id):
    return {"records": [{
        "type": "Cell", "editorId": editor_id, "lightingTemplate": "0300E2:Fallout4.esm",
        "placedObjects": [{"base": "01BA19:Fallout4.esm", "position": [0, 0, 0]}],
        "navmesh": {"floor": [-256, -256, 256, 256], "z": 0, "divisionsX": 2, "divisionsY": 2},
    }]}


def test_navmesh_handoff_interior_with_navmesh_is_clean(real_env, staging_out):
    """A fresh interior cell authored with navmesh:{...} now also carries the NAVI override
    (A-in-game freeze) -> handoff verdict 'clean', no CK tasks."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "NmClean.esp"
    fo4_create_record(cfg, manifest, _navmesh_cell_spec("NmCleanRoom"), str(out))
    data = fo4_navmesh_handoff(cfg, manifest, str(out))["data"]
    assert data["cell_count"] == 1
    assert data["verdict"] == "clean"
    assert data["error_count"] == 0 and data["warning_count"] == 0
    assert data["ck_checklist"] == []
    assert data["findings"][0]["rule"] == "interior_navmesh_ingame_valid"


def test_navmesh_handoff_interior_without_navmesh_warns(real_env, staging_out):
    """An interior cell with no navmesh is an agent-authorable gap (not a CK task)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "NmGap.esp"
    spec = {"records": [{"type": "Cell", "editorId": "NmGapRoom",
        "lightingTemplate": "0300E2:Fallout4.esm",
        "placedObjects": [{"base": "01BA19:Fallout4.esm", "position": [0, 0, 0]}]}]}
    fo4_create_record(cfg, manifest, spec, str(out))
    data = fo4_navmesh_handoff(cfg, manifest, str(out))["data"]
    assert data["verdict"] == "agent-authorable-gaps"
    assert data["warning_count"] == 1
    assert data["ck_checklist"] == []          # interior gap is NOT a CK task
    assert data["findings"][0]["rule"] == "interior_navmesh_missing"


def _voice_quest_spec():
    """A speaker NPC (record 0 -> FormID 000800) + a quest whose INFO is spoken by it, 2 lines.
    The NPC's Voice = MaleEvenToned (013AD2) so voice-handoff can resolve the folder."""
    return {"records": [
        {"type": "npc", "editorId": "VHSpeaker", "name": "Speaker",
         "voice": "013AD2:Fallout4.esm"},
        {"type": "quest", "editorId": "VHQuest", "name": "VQ", "questType": "SideQuests",
         "topics": [
            {"editorId": "VHGreet", "name": "Greet", "subtype": "Custom0",
             "responses": [
                {"speaker": "000800:VoiceLines.esp",
                 "lines": [{"text": "Hello there.", "responseNumber": 1},
                           {"text": "Need something?", "responseNumber": 2}]}
             ]}
         ]},
    ]}


def test_voice_handoff_lists_lines(real_env, staging_out):
    """Every dialogue response line is surfaced with its .fuz path + a recording checklist;
    no .fuz on disk -> verdict 'voice-incomplete'. Voice type resolves to the speaker's folder."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "VoiceLines.esp"
    fo4_create_record(cfg, manifest, _voice_quest_spec(), str(out))
    data = fo4_voice_handoff(cfg, manifest, str(out))["data"]
    assert data["line_count"] == 2
    assert data["verdict"] == "voice-incomplete"   # no .fuz recorded yet
    assert data["warning_count"] == 2
    assert len(data["recording_checklist"]) == 2
    # each .fuz path embeds the INFO FormID + response number under the plugin's voice tree
    paths = sorted(f["fuzPath"] for f in data["findings"])
    assert all(p.startswith("Sound/Voice/VoiceLines.esp/") for p in paths)
    assert paths[0].endswith("_1.fuz") and paths[1].endswith("_2.fuz")
    # if the FO4 install is present the speaker's voice type resolves to its folder
    if cfg.fo4_install_dir is not None and (cfg.fo4_install_dir / "Data" / "Fallout4.esm").is_file():
        assert all("/MaleEvenToned/" in p for p in paths)
        assert all(f["rule"] == "voice_line_missing" for f in data["findings"])


def test_voice_handoff_present_fuz_is_ok(real_env, staging_out):
    """Dropping the expected .fuz under audio_root flips that line to OK."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "Data" / "Fallout4.esm").is_file():
        pytest.skip("FO4 install needed to resolve the voice-type folder")
    out = staging_out / "VoiceLines.esp"
    fo4_create_record(cfg, manifest, _voice_quest_spec(), str(out))
    data = fo4_voice_handoff(cfg, manifest, str(out))["data"]
    # materialize the first line's .fuz under the audio root (the plugin dir) and re-check
    first = data["findings"][0]["fuzPath"]
    fuz = staging_out / first
    fuz.parent.mkdir(parents=True, exist_ok=True)
    fuz.write_bytes(b"FUZE")
    again = fo4_voice_handoff(cfg, manifest, str(out))["data"]
    present = [f for f in again["findings"] if f["rule"] == "voice_line_present"]
    assert len(present) == 1
    assert again["warning_count"] == 1


def test_release_preflight_composes_sections(real_env, staging_out):
    """Preflight rolls up eligibility + navmesh + previs. A new interior cell -> ESM-flag
    required (warning) but a clean navmesh -> overall 'review' (not ship-blocked)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Preflight.esp"
    fo4_create_record(cfg, manifest, _navmesh_cell_spec("PreflightRoom"), str(out))
    data = fo4_release_preflight(cfg, manifest, str(out))["data"]
    assert data["verdict"] in ("review", "ship-ready")
    assert data["error_count"] == 0           # nothing CK-blocking for an interior navmesh cell
    assert "navmesh" in data["sections"]
    assert "eligibility" in data["sections"]
    assert "previs" in data["sections"]
    assert "voice" in data["sections"]
    # the new-cell ESM-flag advisory surfaces as a review-level finding
    rules = {f["rule"] for f in data["findings"]}
    assert "esm_flag_required" in rules
