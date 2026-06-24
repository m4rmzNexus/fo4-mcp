"""fo4_create_record tests — Mutagen authoring writer (Faz 1 MVP).

Gating tests (spec validation, forbidden output, bad suffix, missing binary)
run always against a tmp repo. The integration tests drive the real mutagen-cli
writer and are skipped if it is not built.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import (
    _mutagen_cli_binary,
    _norm_conditions,
    fo4_check_previs_safety,
    fo4_create_record,
    fo4_inspect_record,
    fo4_inspect_sm_tree,
    fo4_place_into_cell,
    fo4_spriggit_export,
)

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = parse_manifest(_REPO / "tools" / "MANIFEST.md")


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


_OK_SPEC = {"records": [{"type": "Npc", "editorId": "X", "name": "x"}]}


# ---------------- spec validation (raises before the CLI / binary check) ----------------

def test_create_rejects_non_dict_spec(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, ["not", "a", "dict"], "staging/x.esp")


def test_create_rejects_empty_records(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, {"records": []}, "staging/x.esp")


def test_create_rejects_unsupported_type(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q1"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_missing_editorid(tmp_path):
    spec = {"records": [{"type": "Npc", "name": "no id"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 1.1 NPC field validation (raises before the CLI) ----------------

def test_create_rejects_non_list_factions(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X", "factions": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_faction_without_formkey(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X", "factions": [{"rank": 1}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_faction_rank_out_of_range(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X",
                         "factions": [{"faction": "068043:Fallout4.esm", "rank": 999}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 2 Quest field validation (raises before the CLI) ----------------

def test_create_rejects_quest_non_list_stages(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "stages": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_quest_stage_without_index(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
                         "stages": [{"logEntry": "no index"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_quest_objective_index_out_of_range(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
                         "objectives": [{"index": 99999, "text": "too big"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 2.1 dialogue validation (raises before the CLI) ----------------

def test_create_rejects_quest_non_list_topics(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "topics": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_quest_non_list_branches(tmp_path):
    """Kerem-polish: a quest's branches must be a list (Python-level shape check)."""
    spec = {"records": [{"type": "Quest", "editorId": "Q", "branches": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_branch_without_starting_topic(tmp_path):
    """Kerem-polish: a DLBR branch must name a startingTopic (the entry topic it surfaces)."""
    spec = {"records": [{"type": "Quest", "editorId": "Q", "branches": [{"editorId": "B"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_armor_non_list_armatures(tmp_path):
    """Kerem-polish: armor armatures must be a list (Python-level shape check)."""
    spec = {"records": [{"type": "Armor", "editorId": "A", "armatures": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_quest_topic_response_number_out_of_range(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "topics": [
        {"editorId": "T", "responses": [{"lines": [{"text": "hi", "responseNumber": 999}]}]}
    ]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_condition_without_function(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "topics": [
        {"editorId": "T", "responses": [{"conditions": [{"comparison": "EqualTo"}]}]}
    ]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_quest_non_list_aliases(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "aliases": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_alias_id_out_of_range(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "aliases": [{"id": -1, "name": "Bad"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_script_without_name(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "scripts": [{"properties": [{"name": "p", "type": "int", "value": 1}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_script_property_bad_type(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "scripts": [
        {"name": "S", "properties": [{"name": "p", "type": "vector"}]}
    ]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_scene_without_editorid(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "scenes": [{"actors": [{"id": 0}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_scene_action_bad_type(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "scenes": [
        {"editorId": "Sc", "actions": [{"type": "Teleport", "actor": 0}]}
    ]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 2.1f fragment validation (raises before the CLI) ----------------

def test_create_rejects_fragments_missing_script_name(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "fragments": {
        "stages": [{"stage": 10, "fragmentName": "Fragment_Stage_0010_Item_00"}]}}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_fragment_stage_without_fragment_name(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q", "fragments": {
        "scriptName": "QF_Q_000800", "stages": [{"stage": 10}]}}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 2.1g alias-fragment validation (raises before the CLI) ----------------

def test_create_rejects_alias_fragment_without_scripts(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "aliasFragments": [{"alias": 0}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_alias_fragment_out_of_range(tmp_path):
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "aliasFragments": [{"alias": 40000, "scripts": [{"name": "S"}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 1.2 ARMO field validation (raises before the CLI) ----------------

def test_create_rejects_armor_negative_value(tmp_path):
    spec = {"records": [{"type": "Armor", "editorId": "A", "value": -5}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_armor_bad_biped_slot(tmp_path):
    spec = {"records": [{"type": "Armor", "editorId": "A",
        "bipedSlots": ["TorsoArmor", "Teleport"]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- output gating ----------------

def test_create_forbidden_output_raises(tmp_path):
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.esp"
    with pytest.raises(PathForbiddenError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, _OK_SPEC, forbidden)


def test_create_rejects_bad_suffix(tmp_path):
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, _OK_SPEC, "staging/x.txt")


def test_create_missing_binary_raises(tmp_path, monkeypatch):
    monkeypatch.setattr("fo4_mcp.tools._mutagen_cli_binary", lambda *a, **k: None)
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, _OK_SPEC, "staging/x.esp")


# ---------------- integration: real mutagen-cli writer ----------------

@pytest.fixture
def real_env():
    return load_config(), _MANIFEST


@pytest.fixture
def staging_out():
    d = _REPO / "staging" / "faz1-create-test"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _skip_if_no_writer(cfg, manifest):
    if _mutagen_cli_binary(cfg, manifest) is None:
        pytest.skip("mutagen-cli not built")


def test_create_npc_and_armor_roundtrip(real_env, staging_out):
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz1Mod.esp"
    spec = {"records": [
        {"type": "Npc", "editorId": "Faz1RtNpc", "name": "Round Trip NPC"},
        {"type": "Armor", "editorId": "Faz1RtArmor"},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert out.exists()
    assert data["record_count"] == 2
    # ModKey-relative FormKeys land in the FO4 ESL-safe range (>= 0x800).
    for rec in data["records"]:
        assert int(rec["formKey"].split(":", 1)[0], 16) >= 0x800

    # read each authored record back through the inspect path (independent parse)
    npc = fo4_inspect_record(cfg, manifest, str(out), "Faz1RtNpc")["data"]
    assert npc["found"] is True
    assert npc["records"][0]["record_type"] == "Npc"
    armo = fo4_inspect_record(cfg, manifest, str(out), "Faz1RtArmor")["data"]
    assert armo["found"] is True
    assert armo["records"][0]["record_type"] == "Armor"


def test_create_npc_with_race_and_faction(real_env, staging_out):
    """Faz 1.1: NPC Race + faction FormLinks persist and auto-add the master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz11RtMod.esp"
    spec = {"records": [{
        "type": "Npc", "editorId": "Faz11RtNpc", "name": "Settler",
        "race": "013746:Fallout4.esm",                      # HumanRace
        "factions": [{"faction": "068043:Fallout4.esm", "rank": 0}],  # MinutemenFaction
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    # a FormLink into Fallout4.esm auto-added it to the master list
    assert "Fallout4.esm" in data["masters"]
    # the written FormLink fields are read back from the on-disk binary
    rec = data["records"][0]
    assert rec["race"] == "013746:Fallout4.esm"
    assert rec["factionCount"] == 1


def test_create_armor_rich(real_env, staging_out):
    """Faz 1.2: ARMO keywords + value/weight/armorRating + biped slots persist,
    read back from the on-disk binary, and keyword FormLinks auto-add the master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz12RtArmor.esp"
    spec = {"records": [{
        "type": "Armor", "editorId": "Faz12RtArmor", "name": "Combat Chestpiece",
        "value": 250, "weight": 12.5, "armorRating": 110,
        "keywords": ["0AEC5B:Fallout4.esm", "01CB2E:Fallout4.esm"],
        "bipedSlots": ["TorsoArmor", "LeftArmArmor", "RightArmArmor"],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    # keyword FormLinks into Fallout4.esm auto-added it to the master list
    assert "Fallout4.esm" in data["masters"]
    rec = data["records"][0]
    # all fields read back from the on-disk binary (round-trip proof)
    assert rec["value"] == 250
    assert rec["weight"] == 12.5
    assert rec["armorRating"] == 110
    assert rec["keywordCount"] == 2
    assert rec["bipedSlotCount"] == 3
    # the ARMO is independently queryable through the inspect path
    armo = fo4_inspect_record(cfg, manifest, str(out), "Faz12RtArmor")["data"]
    assert armo["found"] is True
    assert armo["records"][0]["record_type"] == "Armor"


def test_create_armor_visible_armatures(real_env, staging_out):
    """Kerem-polish: an ARMO with no Armatures renders NOTHING equipped (invisible-armor bug).
    Referencing existing vanilla ARMA addons + Race makes it visible with zero new art; both
    round-trip from the on-disk binary and the ARMA FormLink auto-adds the master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "KeremVisArmor.esp"
    spec = {"records": [{
        "type": "Armor", "editorId": "VisArmor", "name": "Visible Vest",
        "value": 50, "weight": 2.0, "armorRating": 20, "bipedSlots": ["TorsoArmor"],
        "armatures": ["07B9C8:Fallout4.esm"],     # vanilla leather-torso ARMA (HumanRace, world model on disk)
        "race": "013746:Fallout4.esm",            # HumanRace — matches the addon
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]      # the ARMA FormLink auto-added the master
    rec = data["records"][0]
    assert rec["armatureCount"] == 1              # the worn-mesh chain is wired (not 0 = invisible)
    assert rec["race"] == "013746:Fallout4.esm"


def test_create_quest_skeleton(real_env, staging_out):
    """Faz 2: QUST with type/flags/stages/objectives persists and reads back."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz2RtQuest.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz2RtQuest", "name": "Errand",
        "questType": "SideQuests",
        "flags": ["StartGameEnabled", "RunOnce"],
        "stages": [
            {"index": 10, "logEntry": "Begin."},
            {"index": 20, "logEntry": "Continue."},
            {"index": 100, "logEntry": "Done."},
        ],
        "objectives": [
            {"index": 10, "text": "Step one"},
            {"index": 20, "text": "Step two"},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    # read back from the on-disk binary
    assert rec["questType"] == "SideQuests"
    assert rec["stageCount"] == 3
    assert rec["objectiveCount"] == 2
    assert rec["name"] == "Errand"
    # Faz 2.2a: every log entry gets a QSDT marker (engine-required opener).
    assert rec["logEntryQsdtCount"] == 3
    assert rec["runOnStartStageCount"] == 0  # none requested here


def test_create_quest_stage_runonstart_and_qsdt(real_env, staging_out):
    """Faz 2.2a: a startup stage gets INDX RunOnStart (0x02) and every log entry a
    QSDT marker — the structure the engine needs to bring a quest to running-state so
    stage fragments bind/fire. Without these the binary is a CNAM-orphan the engine
    can't parse (the Faz 2.2 in-game root cause)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz22aRunOnStart.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz22aRunOnStart", "name": "Loop",
        "questType": "SideQuests", "flags": ["StartGameEnabled"],
        "stages": [
            {"index": 0, "logEntry": "Test started.", "runOnStart": True},
            {"index": 10, "logEntry": "Stage 10 reached."},
        ],
    }]}
    rec = fo4_create_record(cfg, manifest, spec, str(out))["data"]["records"][0]
    assert rec["stageCount"] == 2
    assert rec["logEntryQsdtCount"] == 2          # QSDT on both log entries
    assert rec["runOnStartStageCount"] == 1       # only stage 0 is a startup stage


def test_create_quest_with_dialogue(real_env, staging_out):
    """Faz 2.1: quest-nested DIAL -> INFO -> lines persist and read back as counts."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21RtQuest.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21RtQuest", "name": "Errand",
        "questType": "SideQuests",
        "topics": [
            {"editorId": "Faz21Greet", "name": "Greeting", "subtype": "Custom0",
             "responses": [{"prompt": "So you made it.", "lines": [
                 {"text": "You made it. Good.", "responseNumber": 1},
                 {"text": "Watch yourself."},
             ]}]},
            {"editorId": "Faz21Bye", "name": "Farewell",
             "responses": [{"lines": [{"text": "Safe travels."}]}]},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["topicCount"] == 2   # two DialogTopics
    assert rec["infoCount"] == 2    # one INFO per topic
    assert rec["lineCount"] == 3    # 2 greeting lines + 1 farewell line
    # the DIAL record is independently queryable as a DialogTopic
    dial = fo4_inspect_record(cfg, manifest, str(out), "Faz21Greet")["data"]
    assert dial["found"] is True
    assert dial["records"][0]["record_type"] == "DialogTopic"


def test_create_quest_dialogue_branch(real_env, staging_out):
    """Kerem-polish: a DLBR DialogBranch (Player/TopLevel) + topic.Branch link is what makes a topic
    surface in the dialogue wheel — a bare DIAL+INFO never appears. The branch and the topic->branch
    link both round-trip from the on-disk binary (writer re-reads the binary and counts them)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "KeremDlgBranch.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "BranchQuest", "name": "Talker", "questType": "SideQuests",
        "branches": [{"editorId": "GreetBranch", "startingTopic": "BGreet",
                      "category": "Player", "flags": ["TopLevel"]}],
        "topics": [{"editorId": "BGreet", "name": "Hello there", "subtype": "Custom0",
                    "branch": "GreetBranch",
                    "responses": [{"prompt": "Hello there", "lines": [{"text": "Well met, traveler."}]}]}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["topicCount"] == 1
    assert rec["branchCount"] == 1            # the DLBR was authored under the quest
    assert rec["branchedTopicCount"] == 1     # the topic links back to it (it will surface)


def test_create_quest_dialogue_with_conditions(real_env, staging_out):
    """Faz 2.1b: INFO conditions persist; a record-param FormKey auto-adds its master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21bGated.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21bQuest", "name": "Gated", "questType": "SideQuests",
        "topics": [{"editorId": "Faz21bGreet", "name": "Greeting", "responses": [{
            "lines": [{"text": "Past stage 10."}],
            "conditions": [
                {"function": "GetStage", "comparison": "GreaterThanOrEqualTo", "value": 10,
                 "param1": "01CA7D:Fallout4.esm"},
                {"function": "GetIsID", "value": 1, "param1": "0750A3:Fallout4.esm"},
            ],
        }]}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # condition record-param auto-added it
    rec = data["records"][0]
    assert rec["topicCount"] == 1
    assert rec["conditionCount"] == 2


def test_create_quest_with_aliases(real_env, staging_out):
    """Faz 2.1c: quest aliases persist; a ForcedReference FormKey auto-adds its master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21cAliases.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21cQuest", "name": "Cast", "questType": "SideQuests",
        "aliases": [
            {"id": 0, "name": "QuestGiver", "flags": ["Optional", "QuestObject"],
             "forcedReference": "01CA7D:Fallout4.esm"},
            {"name": "TargetActor", "flags": ["Optional"], "conditions": [
                {"function": "GetIsID", "value": 1, "param1": "0750A3:Fallout4.esm"},
            ]},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # ForcedReference + condition param auto-added it
    rec = data["records"][0]
    assert rec["aliasCount"] == 2


def test_create_rejects_alias_bad_type(tmp_path):
    """W6.7: alias type must be reference/location."""
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "aliases": [{"id": 0, "name": "X", "type": "package"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_collection_alias(tmp_path):
    """W6.7: collection aliases are blocked — Mutagen v0.53.1 can't round-trip a
    multi-member QuestCollectionAlias (it duplicates the last member on reopen)."""
    spec = {"records": [{"type": "Quest", "editorId": "Q",
        "aliases": [{"type": "collection", "collection": [{"aliasId": 0}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_quest_with_location_and_event_aliases(real_env, staging_out):
    """W6.7: location aliases (SpecificLocation) + event-fill (FindMatchingRefFromEvent)
    persist + round-trip; FormLinks auto-add their master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "W67Aliases.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "W67Quest", "name": "Gather", "questType": "SideQuests",
        "aliases": [
            {"id": 0, "name": "Giver", "type": "reference",
             "forcedReference": "01CA7D:Fallout4.esm"},
            {"id": 1, "name": "Area", "type": "location",
             "specificLocation": "00DF55:Fallout4.esm"},   # a Location FormLink (round-trips)
            {"id": 2, "name": "Spawned", "type": "reference", "flags": ["Optional"],
             "fromEvent": "ADIE"},                          # FindMatchingRefFromEvent
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # forcedReference + specificLocation auto-added it
    rec = data["records"][0]
    assert rec["aliasCount"] == 3              # ref + location + event-fill ref
    # independently queryable through the inspect path
    q = fo4_inspect_record(cfg, manifest, str(out), "W67Quest")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "Quest"


def test_create_quest_with_vmad_script(real_env, staging_out):
    """Faz 2.1d: a Papyrus VMAD script binding persists; an object property's FormKey
    auto-adds its master, and all typed properties read back."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21dScript.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21dQuest", "name": "Scripted", "questType": "SideQuests",
        "aliases": [{"id": 0, "name": "QuestGiver", "flags": ["Optional"]}],
        "scripts": [{"name": "MyQuestScript", "flags": "Local", "properties": [
            {"name": "pTarget", "type": "object", "value": "0750A3:Fallout4.esm"},
            {"name": "pGiver", "type": "object", "alias": 0},
            {"name": "pCount", "type": "int", "value": 3},
            {"name": "pChance", "type": "float", "value": 0.5},
            {"name": "pDone", "type": "bool", "value": False},
            {"name": "pLabel", "type": "string", "value": "hi"},
        ]}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # object property FormKey auto-added it
    rec = data["records"][0]
    assert rec["scriptCount"] == 1
    assert rec["scriptPropertyCount"] == 6


def test_create_quest_with_scene(real_env, staging_out):
    """Faz 2.1e: a SCEN scene persists — actors map to aliases, a dialogue action
    resolves its topic by editorId (within this spec), and a phase condition
    auto-adds its master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21eScene.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21eQuest", "name": "Staged", "questType": "SideQuests",
        "aliases": [{"id": 0, "name": "Speaker", "forcedReference": "01CA7D:Fallout4.esm"}],
        "topics": [{"editorId": "F21e_Hello", "name": "Hello", "responses": [
            {"prompt": "", "lines": [{"text": "Hello there.", "responseNumber": 1}]}]}],
        "scenes": [{"editorId": "F21e_Scene", "flags": ["BeginOnQuestStart", "StopOnQuestEnd"],
            "actors": [{"id": 0}],
            "phases": [{"name": "P0", "startConditions": [
                {"function": "GetStage", "comparison": "GreaterThanOrEqualTo", "value": 10,
                 "param1": "01CA7D:Fallout4.esm"}]}],
            "actions": [{"type": "Dialog", "actor": 0, "topic": "F21e_Hello",
                "startPhase": 0, "endPhase": 0, "flags": ["FaceTarget"]}]}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # ForcedReference + phase condition param
    rec = data["records"][0]
    assert rec["sceneCount"] == 1
    assert rec["sceneActionCount"] == 1
    assert rec["topicCount"] == 1   # the scene action resolved this topic by editorId


def test_create_quest_with_fragments(real_env, staging_out):
    """Faz 2.1f: quest stage script fragments persist — the QF fragment script
    (QuestAdapter.Script) and per-stage entries (QuestAdapter.Fragments) read back,
    coexisting with a Faz 2.1d whole-script binding. Metadata only (no .pex)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21fFragments.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21fQuest", "name": "Fragmented", "questType": "SideQuests",
        "stages": [{"index": 10, "logEntry": "Started."}, {"index": 20, "logEntry": "Mid."}],
        "scripts": [{"name": "Faz21fQuestScript", "flags": "Local",
            "properties": [{"name": "pFlag", "type": "bool", "value": True}]}],
        "fragments": {
            "scriptName": "STF:Fragments:Quests:QF_Faz21fQuest_01000800",
            "properties": [{"name": "pCount", "type": "int", "value": 3}],
            "stages": [
                {"stage": 10, "fragmentName": "Fragment_Stage_0010_Item_00"},
                {"stage": 20, "stageIndex": 0, "fragmentName": "Fragment_Stage_0020_Item_00"},
                {"stage": 20, "stageIndex": 1, "fragmentName": "Fragment_Stage_0020_Item_01"},
            ],
        },
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["fragmentCount"] == 3
    assert rec["fragmentScriptName"] == "STF:Fragments:Quests:QF_Faz21fQuest_01000800"
    assert rec["scriptCount"] == 1            # Faz 2.1d whole-script binding coexists
    assert rec["scriptPropertyCount"] == 1


def test_create_quest_with_alias_fragments(real_env, staging_out):
    """Faz 2.1g: quest alias script fragments persist — each binds a quest alias
    (by ID) to its fragment script(s) via QuestAdapter.Aliases, coexisting with the
    quest's own aliases. The binding Object is the quest itself (no extra master).
    Metadata only (no .pex)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz21gAliasFragments.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz21gQuest", "name": "AliasFragmented",
        "aliases": [{"id": 0, "name": "AliasA"}, {"id": 1, "name": "AliasB"}],
        "aliasFragments": [
            {"alias": 0, "scripts": [{"name": "STG:Fragments:Aliases:AliasA"}]},
            {"alias": 1, "scripts": [{"name": "STG:Fragments:Aliases:AliasB",
                "properties": [{"name": "pCount", "type": "int", "value": 5}]}]},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["aliasFragmentCount"] == 2
    assert rec["aliasCount"] == 2             # the quest's own aliases coexist
    assert data["masters"] == []             # binding Object = the quest itself


def test_create_refuses_existing_without_confirm(real_env, staging_out):
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Exists.esp"
    fo4_create_record(cfg, manifest, _OK_SPEC, str(out))
    again = fo4_create_record(cfg, manifest, _OK_SPEC, str(out))["data"]
    assert again["wrote"] is False
    assert again["overwrite_required"] is True
    assert not out.with_suffix(".esp.bak").exists()


def test_create_overwrite_with_confirm_makes_bak(real_env, staging_out):
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Over.esp"
    fo4_create_record(cfg, manifest, _OK_SPEC, str(out))
    data = fo4_create_record(cfg, manifest, _OK_SPEC, str(out), confirm_overwrite=True)["data"]
    assert data["wrote"] is True
    assert data["backup_path"] is not None
    assert Path(data["backup_path"]).exists()


# ---------------- Faz 3 / W1: condition run-on slots (validation, pure) ----------------

def test_norm_conditions_quest_alias_zero_is_valid():
    # alias ids are 0-based -> an explicit aliasRunOn=0 is a legal target, not the
    # silent default the guard rejects.
    out = _norm_conditions(
        [{"function": "GetDead", "runOn": "QuestAlias", "aliasRunOn": 0}], "x")
    assert out[0]["aliasRunOn"] == 0
    assert out[0]["runOn"] == "QuestAlias"


def test_norm_conditions_alias_run_on_requires_questalias():
    with pytest.raises(Fo4McpError):
        _norm_conditions([{"function": "GetDead", "aliasRunOn": 1}], "x")


def test_norm_conditions_questalias_requires_explicit_alias():
    # the footgun guard: QuestAlias with no aliasRunOn would silently mean alias-0.
    with pytest.raises(Fo4McpError):
        _norm_conditions([{"function": "GetDead", "runOn": "QuestAlias"}], "x")


def test_norm_conditions_reference_requires_reference_runon():
    with pytest.raises(Fo4McpError):
        _norm_conditions(
            [{"function": "GetDistance", "reference": "000014:Fallout4.esm"}], "x")


def test_norm_conditions_reference_slot_ok():
    out = _norm_conditions(
        [{"function": "GetDistance", "runOn": "Reference",
          "reference": "000014:Fallout4.esm"}], "x")
    assert out[0]["reference"] == "000014:Fallout4.esm"
    assert out[0]["runOn"] == "Reference"


# ---------------- Faz 3 / W1: round-trip proof via Spriggit (writer + 2nd engine) ----------------

def test_create_quest_condition_run_on_slots(real_env, staging_out):
    """Faz 3 / W1: QuestAlias run-on writes the alias id to Unknown3; Reference run-on
    writes the FormLink to the Reference slot (separate from the function params).
    Proven by serializing the on-disk esp with Spriggit (independent 2nd engine)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if not (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        pytest.skip("Spriggit not extracted")
    out = staging_out / "Faz3W1RunOn.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz3W1Quest", "name": "RunOn", "questType": "SideQuests",
        "aliases": [
            {"id": 0, "name": "Giver", "flags": ["Optional"]},
            {"id": 2, "name": "Tracked", "flags": ["Optional"], "conditions": [
                {"function": "GetDead", "runOn": "QuestAlias", "aliasRunOn": 2},
                {"function": "GetDistance", "runOn": "Reference",
                 "reference": "000014:Fallout4.esm"},
            ]},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert data["records"][0]["aliasCount"] == 2

    yaml_dir = staging_out / "w1-yaml"
    exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
    assert exp["data"]["ok"]
    blob = "\n".join(
        p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml")
    )
    # QuestAlias run-on: alias id 2 lands in Unknown3
    assert "RunOnType: QuestAlias" in blob
    assert "Unknown3: 2" in blob
    # Reference run-on: PlayerRef FormLink in the Reference slot, NOT a param
    assert "RunOnType: Reference" in blob
    assert "Reference: 000014:Fallout4.esm" in blob


# ---------------- Faz 3 / W1.5: glue record validation (raises before the CLI) ----------------

def test_create_rejects_global_bad_type(tmp_path):
    spec = {"records": [{"type": "Global", "editorId": "G", "globalType": "double"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_global_bad_value(tmp_path):
    spec = {"records": [{"type": "Global", "editorId": "G", "globalValue": "lots"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_formlist_non_list_items(tmp_path):
    spec = {"records": [{"type": "FormList", "editorId": "F", "items": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_formlist_empty_item(tmp_path):
    spec = {"records": [{"type": "FormList", "editorId": "F", "items": ["  "]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 3 / W1.5: glue record round-trip (writer + read-back) ----------------

def test_create_glue_records_roundtrip(real_env, staging_out):
    """Faz 3 / W1.5: the four glue records (Keyword/FormList/Message/Global) write and
    read back from the on-disk binary; FormList item FormLinks auto-add the master; the
    abstract Global builds a concrete subclass and the fractional float is NOT truncated
    (proving the dedicated double? GlobalValue field, distinct from armor's int? Value)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W15Glue.esp"
    spec = {"records": [
        {"type": "Keyword", "editorId": "Faz3W15Kw", "name": "Glue Keyword"},
        {"type": "FormList", "editorId": "Faz3W15Fl", "name": "Glue List",
         "items": ["0AEC5B:Fallout4.esm", "01CB2E:Fallout4.esm"]},
        {"type": "Message", "editorId": "Faz3W15Msg",
         "text": "You found the hidden cache.", "title": "Cache Found"},
        {"type": "Global", "editorId": "Faz3W15GInt", "globalType": "int", "globalValue": 42},
        {"type": "Global", "editorId": "Faz3W15GFloat", "globalType": "float", "globalValue": 3.5},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert data["record_count"] == 5
    # FLST item FormLinks into Fallout4.esm auto-added it to the master list
    assert "Fallout4.esm" in data["masters"]
    by_eid = {r["editorId"]: r for r in data["records"]}
    # Keyword: bare KYWD, name persisted
    assert by_eid["Faz3W15Kw"]["name"] == "Glue Keyword"
    # FormList: both item FormLinks survived + name
    assert by_eid["Faz3W15Fl"]["itemCount"] == 2
    assert by_eid["Faz3W15Fl"]["name"] == "Glue List"
    # Message: text -> Description, title -> Name (title aliases name)
    assert by_eid["Faz3W15Msg"]["text"] == "You found the hidden cache."
    assert by_eid["Faz3W15Msg"]["name"] == "Cache Found"
    # Global: subclass + scalar survived; the float keeps its fraction (double? field)
    assert by_eid["Faz3W15GInt"]["globalType"] == "int"
    assert by_eid["Faz3W15GInt"]["value"] == 42
    assert by_eid["Faz3W15GFloat"]["globalType"] == "float"
    assert by_eid["Faz3W15GFloat"]["value"] == 3.5
    # each glue record is independently queryable through the inspect path
    kw = fo4_inspect_record(cfg, manifest, str(out), "Faz3W15Kw")["data"]
    assert kw["found"] is True


def test_create_glue_records_spriggit(real_env, staging_out):
    """Faz 3 / W1.5: serialize the glue records with Spriggit (independent 2nd engine)
    and confirm the on-disk field shapes — the Global SHORT subclass (the round-trip
    proof of globalType=short), the FormList item FormKey, and the Message body."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if not (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        pytest.skip("Spriggit not extracted")
    out = staging_out / "Faz3W15GlueSp.esp"
    spec = {"records": [
        {"type": "Keyword", "editorId": "Faz3W15SpKw"},
        {"type": "FormList", "editorId": "Faz3W15SpFl", "items": ["0AEC5B:Fallout4.esm"]},
        {"type": "Message", "editorId": "Faz3W15SpMsg", "text": "Hidden cache found."},
        {"type": "Global", "editorId": "Faz3W15SpGShort", "globalType": "short", "globalValue": 7},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True

    yaml_dir = staging_out / "w15-yaml"
    exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
    assert exp["data"]["ok"]
    blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
    # Keyword: bare KYWD serialized by EditorID
    assert "Faz3W15SpKw" in blob
    # FormList: the item FormLink appears as a flat FormKey scalar under Items
    assert "0AEC5B:Fallout4.esm" in blob
    # Message: the body landed in Description (TranslatedString String)
    assert "Hidden cache found." in blob
    # Global: the short subclass is serialized as MutagenObjectType GlobalShort
    assert "GlobalShort" in blob


# ---------------- Faz 3 / W3.5: Faction validation (raises before the CLI) ----------------

def test_create_rejects_faction_non_list_relations(tmp_path):
    spec = {"records": [{"type": "Faction", "editorId": "F", "interfactionRelations": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_faction_relation_without_faction(tmp_path):
    spec = {"records": [{"type": "Faction", "editorId": "F",
        "interfactionRelations": [{"reaction": "Enemy"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_faction_relation_without_reaction(tmp_path):
    spec = {"records": [{"type": "Faction", "editorId": "F",
        "interfactionRelations": [{"faction": "068043:Fallout4.esm"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


# ---------------- Faz 3 / W3.5: Faction round-trip (writer + read-back + Spriggit) ----------------

def test_create_faction_record(real_env, staging_out):
    """Faz 3 / W3.5: author a FACT with flags + an interfaction relation (Enemy toward a
    vanilla faction — what makes a placed hostile NPC actually hostile). Read back
    flagCount/relationCount; the relation Target auto-adds the master; Spriggit (independent
    engine) confirms the Relations{Target,Reaction} + Flags shape vs Remnants ground-truth."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W35Faction.esp"
    spec = {"records": [{
        "type": "Faction", "editorId": "Faz3W35Enemies", "name": "Hostile Raiders",
        "flags": ["TrackCrime"],
        "interfactionRelations": [
            {"faction": "068043:Fallout4.esm", "reaction": "Enemy"},  # Enemy toward MinutemenFaction
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    # the relation Target FormLink into Fallout4.esm auto-added it to the master list
    assert "Fallout4.esm" in data["masters"]
    rec = data["records"][0]
    # read back from the on-disk binary (round-trip proof)
    assert rec["flagCount"] == 1
    assert rec["relationCount"] == 1
    # Spriggit (independent 2nd engine): the Relation + Flags shape matches Remnants
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w35-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
        assert "Relations:" in blob
        assert "Reaction: Enemy" in blob
        assert "Target: 068043:Fallout4.esm" in blob
        assert "TrackCrime" in blob


# ---------------- Faz 3 / W3b NPC full-field ----------------

def test_create_rejects_npc_non_list_inventory(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X", "inventory": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_npc_inventory_without_item(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X",
                         "inventory": [{"count": 3}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_npc_perk_rank_out_of_range(tmp_path):
    spec = {"records": [{"type": "Npc", "editorId": "X",
                         "perks": [{"perk": "01D2C7:Fallout4.esm", "rank": 999}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_npc_bad_aggression(real_env, staging_out):
    """The CLI is authoritative for AI enum names: a bad aggression name fails the write."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3bBad.esp"
    spec = {"records": [{"type": "Npc", "editorId": "BadAggro",
                         "aggression": "Bezerk"}]}  # not a real AggressionType member
    with pytest.raises(Fo4McpError):
        fo4_create_record(cfg, manifest, spec, str(out))


def test_create_npc_full_field(real_env, staging_out):
    """Faz 3 / W3b: a full-field NPC — FormLink scalars (voice/combatStyle/defaultOutfit/
    attackRace/skin) + AI personality enums + keywords + inventory (CNTO) + perks. Every
    field reads back from the on-disk binary; FormLinks auto-add the master; Spriggit
    (independent 2nd engine) confirms the enum + Items/Perks shape."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3bNpc.esp"
    spec = {"records": [{
        "type": "Npc", "editorId": "Faz3W3bTrooper", "name": "Enclave Trooper",
        "race": "013746:Fallout4.esm",
        # FormLink scalars — round-trip targets (the writer stores links without
        # type-checking the target record; attackRace reuses the real HumanRace).
        "voice": "0712D0:Fallout4.esm",
        "combatStyle": "0334A7:Fallout4.esm",
        "defaultOutfit": "01EFE5:Fallout4.esm",
        "attackRace": "013746:Fallout4.esm",
        "skin": "0170BC:Fallout4.esm",
        # AI personality (CLI-authoritative enum names)
        "aggression": "Aggressive", "confidence": "Brave",
        "assistance": "HelpsAllies", "responsibility": "ViolenceAgainstEnemies",
        "mood": "Angry",
        # keywords + inventory (CNTO, count) + perks (rank); 00000F = Caps (real)
        "keywords": ["0AEC5B:Fallout4.esm", "01CB2E:Fallout4.esm"],
        "inventory": [{"item": "00000F:Fallout4.esm", "count": 100},
                      {"item": "0001F2:Fallout4.esm", "count": 1}],
        "perks": [{"perk": "01D2C7:Fallout4.esm", "rank": 2}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    # FormLinks into Fallout4.esm auto-added it to the master list
    assert "Fallout4.esm" in data["masters"]
    rec = data["records"][0]
    # FormLink scalars round-trip from the on-disk binary
    assert rec["voice"] == "0712D0:Fallout4.esm"
    assert rec["combatStyle"] == "0334A7:Fallout4.esm"
    assert rec["defaultOutfit"] == "01EFE5:Fallout4.esm"
    assert rec["attackRace"] == "013746:Fallout4.esm"
    assert rec["skin"] == "0170BC:Fallout4.esm"
    # AI personality enums round-trip by name
    assert rec["aggression"] == "Aggressive"
    assert rec["confidence"] == "Brave"
    assert rec["assistance"] == "HelpsAllies"
    assert rec["responsibility"] == "ViolenceAgainstEnemies"
    assert rec["mood"] == "Angry"
    # structured list counts
    assert rec["keywordCount"] == 2
    assert rec["itemCount"] == 2
    assert rec["perkCount"] == 1
    # the NPC is independently queryable through the inspect path
    npc = fo4_inspect_record(cfg, manifest, str(out), "Faz3W3bTrooper")["data"]
    assert npc["found"] is True
    assert npc["records"][0]["record_type"] == "Npc"
    # Spriggit (independent 2nd engine): enum names + FormLinks persist
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w3b-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
        assert "Aggressive" in blob
        assert "Brave" in blob
        assert "0712D0:Fallout4.esm" in blob   # voice FormLink
        assert "01D2C7:Fallout4.esm" in blob   # perk FormLink


def test_create_rejects_npc_non_list_use_template_actors(tmp_path):
    """useTemplateActors must be a list of flag names (Python-level shape check)."""
    spec = {"records": [{"type": "Npc", "editorId": "BadUTA",
                         "useTemplateActors": "Traits"}]}  # a string, not a list
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_npc_bad_template_flag(real_env, staging_out):
    """The CLI is authoritative for TemplateActorType names: a bad flag fails the write."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3cBad.esp"
    spec = {"records": [{"type": "Npc", "editorId": "BadFlag",
                         "useTemplateActors": ["Traits", "Bogus"]}]}  # Bogus not a member
    with pytest.raises(Fo4McpError):
        fo4_create_record(cfg, manifest, spec, str(out))


def test_create_npc_template_chain(real_env, staging_out):
    """Faz 3 / W3c: template-chain — DefaultTemplate (a real Fallout4.esm LeveledNpc,
    LCharWorkshopNPC) + UseTemplateActors flag bitfield. The two NPCs reproduce the
    byte-verified disk archetypes from the W3a probe: a 7999 trooper (11 flags) and an
    8127 turret (7999 + BaseData; ModelOrAnimation stays OFF). The raw bitfield int
    round-trips byte-exact from the on-disk binary; Spriggit (independent 2nd engine)
    serializes the same bare int + the DefaultTemplate FormLink."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3cNpc.esp"
    flags11 = ["Traits", "Stats", "Factions", "SpellList", "AiData", "AiPackages",
               "Inventory", "Script", "DefPackList", "AttackData", "Keywords"]
    spec = {"records": [
        {"type": "Npc", "editorId": "Faz3W3cTrooper", "name": "Enclave Trooper",
         "race": "013746:Fallout4.esm",
         "defaultTemplate": "113341:Fallout4.esm",     # LCharWorkshopNPC (real LeveledNpc)
         "useTemplateActors": flags11},                 # -> 7999
        {"type": "Npc", "editorId": "Faz3W3cTurret", "name": "Sentry Turret",
         "defaultTemplate": "113341:Fallout4.esm",
         "useTemplateActors": flags11 + ["BaseData"]},  # -> 8127
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]          # FormLinks auto-added the master
    trooper, turret = data["records"][0], data["records"][1]
    # byte-exact bitfield round-trip from the on-disk binary (reproduces W3a disk raws)
    assert trooper["useTemplateActors"] == 7999
    assert turret["useTemplateActors"] == 8127
    # DefaultTemplate FormLink round-trips
    assert trooper["defaultTemplate"] == "113341:Fallout4.esm"
    assert turret["defaultTemplate"] == "113341:Fallout4.esm"
    # independently queryable through the inspect path
    npc = fo4_inspect_record(cfg, manifest, str(out), "Faz3W3cTrooper")["data"]
    assert npc["found"] is True
    assert npc["records"][0]["record_type"] == "Npc"
    # Spriggit (independent 2nd engine): the bare-int bitfield + DefaultTemplate FormLink
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w3c-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
        assert "UseTemplateActors: 7999" in blob
        assert "UseTemplateActors: 8127" in blob
        assert "DefaultTemplate: 113341:Fallout4.esm" in blob


def test_create_rejects_leveled_non_list_entries(tmp_path):
    """A leveled list's entries must be a list (Python-level shape check)."""
    spec = {"records": [{"type": "LeveledNpc", "editorId": "BadLvln",
                         "entries": "notalist"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_leveled_entry_without_reference(tmp_path):
    """Each leveled entry needs a 'reference' FormKey."""
    spec = {"records": [{"type": "LeveledItem", "editorId": "BadLvli",
                         "entries": [{"level": 1, "count": 1}]}]}  # no reference
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_leveled_entry_bad_level(tmp_path):
    """Leveled entry level is 1..32767 (Int16 positive); 0 is rejected."""
    spec = {"records": [{"type": "LeveledNpc", "editorId": "BadLevel",
                         "entries": [{"reference": "0179FF:Fallout4.esm", "level": 0}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_leveled_bad_flag(real_env, staging_out):
    """The CLI is authoritative for LeveledNpc.Flag/LeveledItem.Flag names: bad flag fails."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3deBad.esp"
    spec = {"records": [{"type": "LeveledItem", "editorId": "BadFlag",
                         "flags": ["CalculateAll"]}]}  # CalculateAll is LVLN-only; LVLI has UseAll
    with pytest.raises(Fo4McpError):
        fo4_create_record(cfg, manifest, spec, str(out))


def test_create_leveled_npc_and_item(real_env, staging_out):
    """Faz 3 / W3d+W3e: a LeveledNpc + LeveledItem. Each entry's reference/level/count
    round-trips from the on-disk binary (proving the Leveled*EntryData persisted); calc
    flags reuse the shared 'flags' key (LVLN CalculateForEachItemInCount=2, LVLI UseAll=4);
    FormLinks auto-add the master; Spriggit (independent 2nd engine) confirms the Entries
    structure + flag names."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W3deLists.esp"
    spec = {"records": [
        {"type": "LeveledNpc", "editorId": "Faz3W3dList",
         "flags": ["CalculateForEachItemInCount"],
         "entries": [{"reference": "0179FF:Fallout4.esm", "level": 1, "count": 1},   # Codsworth (NPC_)
                     {"reference": "113341:Fallout4.esm", "level": 5, "count": 2}]},  # LCharWorkshopNPC (LVLN)
        {"type": "LeveledItem", "editorId": "Faz3W3eList",
         "flags": ["UseAll"],
         "entries": [{"reference": "00000F:Fallout4.esm", "level": 1, "count": 100}]},  # Caps
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    lvln, lvli = data["records"][0], data["records"][1]
    # LeveledNpc: 2 entries, CalculateForEachItemInCount = bit 2
    assert lvln["entryCount"] == 2
    assert lvln["flags"] == 2
    assert lvln["entries"][0]["reference"] == "0179FF:Fallout4.esm"
    assert lvln["entries"][1]["level"] == 5
    assert lvln["entries"][1]["count"] == 2
    # LeveledItem: 1 entry, UseAll = bit 4
    assert lvli["entryCount"] == 1
    assert lvli["flags"] == 4
    assert lvli["entries"][0]["reference"] == "00000F:Fallout4.esm"
    assert lvli["entries"][0]["count"] == 100
    # independently queryable through the inspect path
    q = fo4_inspect_record(cfg, manifest, str(out), "Faz3W3dList")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "LeveledNpc"
    # Spriggit (independent 2nd engine): Entries structure + flag names persist
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w3de-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
        assert "CalculateForEachItemInCount" in blob
        assert "UseAll" in blob
        assert "Reference: 113341:Fallout4.esm" in blob   # LVLN entry FormLink
        assert "Reference: 00000F:Fallout4.esm" in blob    # LVLI entry FormLink


def test_create_rejects_objective_target_without_alias(tmp_path):
    """A QSTA target needs an integer 'aliasId' (Python-level shape check)."""
    spec = {"records": [{"type": "Quest", "editorId": "BadObjTgt",
                         "objectives": [{"index": 10, "targets": [{"flags": ["Hostile"]}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_objective_non_list_targets(tmp_path):
    """objectives[].targets must be a list."""
    spec = {"records": [{"type": "Quest", "editorId": "BadObjTgt2",
                         "objectives": [{"index": 10, "targets": "notalist"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_objective_bad_target_flag(real_env, staging_out):
    """The CLI is authoritative for Quest.TargetFlag names: a bad target flag fails the write."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W2Bad.esp"
    spec = {"records": [{"type": "Quest", "editorId": "BadTgtFlag",
                         "objectives": [{"index": 10,
                             "targets": [{"aliasId": 0, "flags": ["NotARealFlag"]}]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(cfg, manifest, spec, str(out))


def test_create_quest_objective_targets(real_env, staging_out):
    """Faz 3 / W2: a quest objective with flags + a QSTA target — alias ID (compass marker),
    target flags, an LCRT keyword, and a find-ref condition. The target + objective flags
    round-trip from the on-disk binary; Spriggit (2nd engine) confirms the full QSTA shape
    (objective Flags, target Flags/Keyword/AliasID, and the reused condition builder)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W2Quest.esp"
    spec = {"records": [{
        "type": "Quest", "editorId": "Faz3W2Quest", "name": "W2 Marker Quest",
        "questType": "SideQuests", "flags": ["StartGameEnabled"],
        "aliases": [{"id": 0, "name": "Giver", "uniqueActor": "0179FF:Fallout4.esm"},
                    {"id": 1, "name": "Target", "uniqueActor": "019FD9:Fallout4.esm"}],
        "objectives": [
            {"index": 10, "text": "Reach the target",
             "flags": ["OrWithPrevious", "NoStatsTracking"],
             "targets": [{"aliasId": 1,
                          "flags": ["CompassMarkerIgnoresLocks", "Hostile"],
                          "keyword": "0AEC5B:Fallout4.esm",
                          "conditions": [{"function": "GetIsID", "value": 1.0,
                                          "param1": "019FD9:Fallout4.esm"}]}]},
            {"index": 20, "text": "No marker here"},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    q = data["records"][0]
    assert q["objectiveCount"] == 2
    assert q["objectiveTargetCount"] == 1     # one QSTA target round-tripped
    assert q["objectiveFlaggedCount"] == 1    # objective 10 carries flags, 20 does not
    # independently queryable through the inspect path
    insp = fo4_inspect_record(cfg, manifest, str(out), "Faz3W2Quest")["data"]
    assert insp["found"] is True
    assert insp["records"][0]["record_type"] == "Quest"
    # Spriggit (independent 2nd engine): the full QSTA shape persists
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w2-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yaml_dir.rglob("*.yaml"))
        assert "OrWithPrevious" in blob            # objective flag
        assert "CompassMarkerIgnoresLocks" in blob  # target flag
        assert "AliasID: 1" in blob                 # the target's alias (nonzero -> visible)
        assert "Keyword: 0AEC5B:Fallout4.esm" in blob
        assert "GetIsID" in blob                    # target condition (reused builder)


# ---------------- Faz 3 / W4: interior CELL + placed refs (REFR/ACHR) ----------------

def test_create_rejects_cell_non_list_placed_objects(tmp_path):
    """A cell's placedObjects must be a list (Python-level shape check)."""
    spec = {"records": [{"type": "Cell", "editorId": "BadCell",
                         "placedObjects": "notalist"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_placed_ref_without_base(tmp_path):
    """Each placed ref needs a 'base' FormKey."""
    spec = {"records": [{"type": "Cell", "editorId": "BadCell",
                         "placedObjects": [{"position": [0, 0, 0]}]}]}  # no base
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_placed_ref_bad_position(tmp_path):
    """position must be an [x,y,z] triple (3 numbers), not 2."""
    spec = {"records": [{"type": "Cell", "editorId": "BadCell",
                         "placedNpcs": [{"base": "0179FF:Fallout4.esm", "position": [0, 0]}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_cell_bad_water_height(tmp_path):
    """waterHeight must be a number."""
    spec = {"records": [{"type": "Cell", "editorId": "BadCell",
                         "waterHeight": "deep"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_interior_cell_with_refs(real_env, staging_out):
    """Faz 3 / W4: a new INTERIOR cell with nested placed refs (REFR + ACHR), modeled on
    the verify-target SanctuaryRosaHouse. Proves: the cell is flagged IsInteriorCell, lands
    in the right block/subblock (FormID-hash: 0x800 -> block 8, sub 4), carries its
    LightingTemplate (LTMP), and its refs round-trip from the on-disk binary (base/position/
    scale; scale omitted -> default). The cell is independently queryable (inspect path) and
    Spriggit (2nd engine) confirms the Cell + PlacedObject/PlacedNpc + IsInteriorCell + the
    Cells/<block>/<subblock>/ folder nesting."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W4Cell.esp"
    spec = {"records": [{
        "type": "Cell", "editorId": "Faz3W4Room", "name": "Test Shack",
        "lightingTemplate": "0300E2:Fallout4.esm",   # a real LGTM (Rosa Residence's)
        "location": "01F3DA:Fallout4.esm",
        "imageSpace": "0016C4:Fallout4.esm",
        "placedObjects": [
            {"editorId": "W4Floor", "base": "01BA19:Fallout4.esm", "position": [0, 0, 0]},
            {"editorId": "W4Wall",  "base": "01BA2E:Fallout4.esm", "position": [256, 0, 0],
             "rotation": [0, 0, 1.5708]},
            {"base": "01BA44:Fallout4.esm", "position": [-320, 352, 0], "scale": 1.25},
        ],
        "placedNpcs": [
            {"editorId": "W4Settler", "base": "0179FF:Fallout4.esm", "position": [64, 64, 0]},
        ],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    c = data["records"][0]
    # ESL-safe FormID + interior flag + FormID-hash block placement
    assert int(c["formKey"].split(":", 1)[0], 16) >= 0x800
    assert c["interior"] is True
    assert c["block"] == 8 and c["subBlock"] == 4   # 0x800 -> block=id%10, sub=(id/10)%10
    assert c["lightingTemplate"] == "0300E2:Fallout4.esm"
    assert c["location"] == "01F3DA:Fallout4.esm"
    # refs nest in Temporary (vanilla furnished residences keep refs there)
    assert c["persistentCount"] == 0
    assert c["temporaryCount"] == 4
    assert len(c["placedObjects"]) == 3
    assert len(c["placedNpcs"]) == 1
    # per-ref round-trip from the on-disk binary
    assert c["placedObjects"][0]["editorId"] == "W4Floor"
    assert c["placedObjects"][0]["base"] == "01BA19:Fallout4.esm"
    assert c["placedObjects"][2]["scale"] == pytest.approx(1.25)
    assert c["placedObjects"][0]["scale"] is None    # 1.0 default -> XSCL omitted
    assert c["placedNpcs"][0]["editorId"] == "W4Settler"
    assert c["placedNpcs"][0]["base"] == "0179FF:Fallout4.esm"
    # independently queryable through the inspect path (EnumerateMajorRecords finds it)
    q = fo4_inspect_record(cfg, manifest, str(out), "Faz3W4Room")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "Cell"
    # Spriggit (independent 2nd engine): Cell + placed refs + the block/subblock folder nesting
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w4-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        yamls = list(yaml_dir.rglob("*.yaml"))
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yamls)
        assert "IsInteriorCell" in blob
        assert "Faz3W4Room" in blob
        assert "PlacedObject" in blob               # REFR MutagenObjectType
        assert "PlacedNpc" in blob                  # ACHR MutagenObjectType
        assert "01BA19:Fallout4.esm" in blob        # a REFR base FormLink
        assert "0300E2:Fallout4.esm" in blob        # the LightingTemplate
        # Spriggit nests interior cells as Cells\<block>\<subblock>\ — independent block proof
        assert any(("Cells" in str(p) and f"{8}" in p.parts and f"{4}" in p.parts) for p in yamls)


def test_create_cell_persistent_ref(real_env, staging_out):
    """W4: a placed ref with persistent=true routes to Cell.Persistent, not Temporary."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W4Persist.esp"
    spec = {"records": [{
        "type": "Cell", "editorId": "Faz3W4PersistRoom",
        "placedObjects": [
            {"base": "01BA19:Fallout4.esm", "position": [0, 0, 0], "persistent": True},
            {"base": "01BA2E:Fallout4.esm", "position": [128, 0, 0]},  # -> Temporary
        ],
    }]}
    c = fo4_create_record(cfg, manifest, spec, str(out))["data"]["records"][0]
    assert c["persistentCount"] == 1
    assert c["temporaryCount"] == 1


# ---------------- Faz 3 / W5: place refs into an existing cell (cell-override) ----------------

_ROSA = "01F398:Fallout4.esm"  # SanctuaryRosaHouse — a real precombined interior


def _skip_if_no_fo4(cfg):
    p = cfg.fo4_install_dir
    if p is None or not (p / "Data" / "Fallout4.esm").exists():
        pytest.skip("FO4 install / Fallout4.esm not available")


def test_place_into_cell_rejects_no_refs(real_env, staging_out):
    """place_into_cell needs at least one ref (Python-level shape check, before any I/O)."""
    cfg, manifest = real_env
    with pytest.raises(Fo4McpError):
        fo4_place_into_cell(cfg, manifest, _ROSA, str(staging_out / "x.esp"))


def test_create_rejects_celloverride_without_source(tmp_path):
    """A cellOverride needs a sourcePlugin (the plugin holding the target cell)."""
    spec = {"records": [{"type": "cellOverride", "cell": _ROSA,
                         "placedObjects": [{"base": "01BA19:Fallout4.esm"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_celloverride_without_cell(tmp_path):
    """A cellOverride needs a target 'cell' FormKey."""
    spec = {"records": [{"type": "cellOverride", "sourcePlugin": "Fallout4.esm",
                         "placedObjects": [{"base": "01BA19:Fallout4.esm"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_check_previs_safety_precombined(real_env):
    """W5 BLOCKING precondition: SanctuaryRosaHouse is precombined/previs'd -> unsafe to edit."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    s = fo4_check_previs_safety(cfg, manifest, _ROSA)["data"]
    assert s["found"] is True
    assert s["hasPrecombines"] is True
    assert s["safe"] is False
    assert "UNSAFE" in s["verdict"]


def test_place_into_cell_blocks_precombined(real_env, staging_out):
    """W5: placing into a precombined cell without acknowledge_previs is BLOCKED (no write)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    out = staging_out / "W5Blocked.esp"
    r = fo4_place_into_cell(cfg, manifest, _ROSA, str(out),
                            placed_objects=[{"base": "01BA19:Fallout4.esm", "position": [0, 0, 0]}])["data"]
    assert r["wrote"] is False
    assert r["blocked"] is True
    assert r["reason"] == "previs_unsafe"
    assert not out.exists()


def test_place_into_cell_override_roundtrip(real_env, staging_out):
    """W5: acknowledge_previs -> the override is written; the master cell FormKey is preserved
    (a true override, not a new record), lighting/data carry forward (deep copy). SAFE DEFAULT is
    ADDITIVE (clear_existing=False) — the master's own refs are preserved and the new refs appended."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    out = staging_out / "W5Override.esp"
    r = fo4_place_into_cell(
        cfg, manifest, _ROSA, str(out),
        placed_objects=[{"editorId": "W5Ref", "base": "01BA19:Fallout4.esm", "position": [50, 60, 0]}],
        placed_npcs=[{"base": "0179FF:Fallout4.esm", "position": [20, 20, 0]}],
        acknowledge_previs=True)["data"]                     # clear_existing defaults to False
    assert r["wrote"] is True
    assert "Fallout4.esm" in r["masters"]
    c = r["records"][0]
    assert c["formKey"] == _ROSA                              # true override: master FormKey kept
    assert c["name"] == "Rosa Residence"                     # deep copy carried the name forward
    assert c["lightingTemplate"] == "0300E2:Fallout4.esm"    # lighting preserved (no black cell)
    assert c["temporaryCount"] > 2                           # additive: master's own refs + the 2 new
    # additive readback lists ALL refs; assert the 2 NEW ones are present among the master's
    assert any(o.get("editorId") == "W5Ref" for o in c["placedObjects"])
    assert any(n.get("base") == "0179FF:Fallout4.esm" for n in c["placedNpcs"])
    assert "previs_safety" in r                              # verdict threaded into the response
    q = fo4_inspect_record(cfg, manifest, str(out), "01F398")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "Cell"


def test_place_into_cell_clear_existing_is_destructive_optin(real_env, staging_out):
    """W5 regression: the safe default keeps the master's refs (additive); clear_existing=True is an
    explicit destructive opt-in that wipes the deep-copied master refs, leaving only the new ones.
    Guards the bug where the default wiped a populated cell (the Kerem RedRocketExt incident — 482
    master refs lost)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    new_ref = [{"base": "01BA19:Fallout4.esm", "position": [50, 60, 0]}]
    add = fo4_place_into_cell(cfg, manifest, _ROSA, str(staging_out / "W5Add.esp"),
                              placed_objects=new_ref, acknowledge_previs=True)["data"]
    wipe = fo4_place_into_cell(cfg, manifest, _ROSA, str(staging_out / "W5Wipe.esp"),
                               placed_objects=new_ref, acknowledge_previs=True,
                               clear_existing=True)["data"]
    add_temp = add["records"][0]["temporaryCount"]
    wipe_temp = wipe["records"][0]["temporaryCount"]
    assert wipe_temp == 1                 # explicit clear -> only the single new ref survives
    assert add_temp > wipe_temp           # safe default kept the master's refs (no silent data loss)


def test_place_into_cell_safe_when_no_precombines(real_env, staging_out):
    """W5 safe path: a freshly-authored cell has no precombines -> place_into_cell succeeds
    WITHOUT acknowledge_previs, using the authored plugin as the source."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    base = staging_out / "W5Base.esp"
    spec = {"records": [{"type": "Cell", "editorId": "W5SafeRoom", "name": "Safe Room",
                         "lightingTemplate": "0300E2:Fallout4.esm"}]}
    made = fo4_create_record(cfg, manifest, spec, str(base))["data"]
    cell_fk = made["records"][0]["formKey"]                  # e.g. 000800:W5Base.esp
    s = fo4_check_previs_safety(cfg, manifest, cell_fk, str(base))["data"]
    assert s["safe"] is True                                 # new cell is previs-free
    out = staging_out / "W5SafePlace.esp"
    r = fo4_place_into_cell(cfg, manifest, cell_fk, str(out), source_plugin=str(base),
                            placed_objects=[{"base": "01BA19:Fallout4.esm", "position": [0, 0, 0]}])["data"]
    assert r["wrote"] is True
    assert r["records"][0]["formKey"] == cell_fk


# ---------------- Faz 3 / W6: Story Manager Quest Node (SMQN) auto-start ----------------

_DMND_EVENT = "029152:Fallout4.esm"   # parent event node of DmndSchoolhouseEvents
_DMND_QUEST = "14EA88:Fallout4.esm"   # a real quest under that node


def test_create_rejects_smqn_non_list_quests(tmp_path):
    """An smqn's quests must be a list (Python-level shape check)."""
    spec = {"records": [{"type": "smqn", "editorId": "BadNode", "quests": "nope"}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_smqn_quest_without_quest(tmp_path):
    """Each smqn quest entry needs a 'quest' FormKey."""
    spec = {"records": [{"type": "smqn", "editorId": "BadNode",
                         "quests": [{"hoursUntilReset": 24}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_smqn_roundtrip(real_env, staging_out):
    """Faz 3 / W6: a Story Manager Quest Node. parent/flags/conditions/quests round-trip from
    the on-disk binary; FormLinks auto-add the master; Spriggit (2nd engine) confirms the
    StoryManagerQuestNode + the quest FormLink + the Random flag. Ground-truth shape =
    DmndSchoolhouseEvents (Parent + Random flag + MaxConcurrentQuests + per-quest reset)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W6Smqn.esp"
    spec = {"records": [{
        "type": "smqn", "editorId": "Faz3W6Node",
        "parent": _DMND_EVENT,
        "flags": ["Random"],
        "maxConcurrentQuests": 1,
        "conditions": [{"function": "GetRandomPercent", "comparison": "LessThan", "value": 50}],
        "quests": [{"quest": _DMND_QUEST, "hoursUntilReset": 24}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    n = data["records"][0]
    assert n["parent"] == _DMND_EVENT
    assert n["flags"] == 1                       # AStoryManagerNode.Flag.Random = 1
    assert n["maxConcurrentQuests"] == 1
    assert n["conditionCount"] == 1
    assert n["questCount"] == 1
    assert n["quests"] == [_DMND_QUEST]
    q = fo4_inspect_record(cfg, manifest, str(out), "Faz3W6Node")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "StoryManagerQuestNode"
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w6-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        yamls = list(yaml_dir.rglob("*.yaml"))
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yamls)
        # Spriggit nests records by type folder -> StoryManagerQuestNodes/ (type proof)
        assert any("StoryManagerQuestNode" in str(p) for p in yamls)
        assert _DMND_QUEST in blob               # the quest FormLink
        assert "Random" in blob                  # the node flag
        assert "MaxConcurrentQuests" in blob     # node-level field round-tripped


def test_inspect_sm_tree_lists_event_nodes(real_env):
    """W6: fo4_inspect_sm_tree (no node) lists the vanilla SM event nodes (auto-start anchors)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    d = fo4_inspect_sm_tree(cfg, manifest, "Fallout4.esm")["data"]
    assert d["eventNodeCount"] >= 1
    assert all("formKey" in n for n in d["eventNodes"])


def test_inspect_sm_tree_node_children(real_env):
    """W6: querying a specific event node returns it + its direct children."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    _skip_if_no_fo4(cfg)
    d = fo4_inspect_sm_tree(cfg, manifest, "Fallout4.esm", "ActorHelloEvent")["data"]
    assert d["found"] is True
    assert d["node"]["kind"] == "event"
    assert d["childCount"] >= 1


# ---------------- Faz 3 / W6.5 + W8: ACTI / LCTN / LCRT / ECZN base records ----------------

def test_create_rejects_encounterzone_bad_level(tmp_path):
    """ECZN min/max level + rank are bytes (0..255)."""
    spec = {"records": [{"type": "encounterZone", "editorId": "BadZone", "minLevel": 999}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_world_base_records(real_env, staging_out):
    """Faz 3 / W6.5 + W8: a script-bound ACTI + a Location + a LocationRefType + an
    EncounterZone in one plugin. Each round-trips from the on-disk binary; FormLinks auto-add
    the master; Spriggit (2nd engine) confirms the record types + ECZN flags."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W8Base.esp"
    spec = {"records": [
        {"type": "activator", "editorId": "Faz3W65Trigger", "name": "Test Trigger",
         "keywords": ["01CA72:Fallout4.esm"]},
        {"type": "locationRefType", "editorId": "Faz3W8RefType"},
        {"type": "location", "editorId": "Faz3W8Loc", "name": "Test Location",
         "parentLocation": "01F3DA:Fallout4.esm", "keywords": ["01CA72:Fallout4.esm"]},
        {"type": "encounterZone", "editorId": "Faz3W8Zone",
         "flags": ["NeverResets", "Workshop"], "location": "01F3DA:Fallout4.esm",
         "minLevel": 5, "maxLevel": 20, "rank": 2},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    acti, lcrt, lctn, eczn = data["records"]
    assert acti["name"] == "Test Trigger" and acti["keywordCount"] == 1
    assert lctn["parentLocation"] == "01F3DA:Fallout4.esm" and lctn["keywordCount"] == 1
    assert eczn["flags"] == 9                 # NeverResets(1) | Workshop(8)
    assert eczn["minLevel"] == 5 and eczn["maxLevel"] == 20 and eczn["rank"] == 2
    # independently queryable
    for eid, rtype in (("Faz3W65Trigger", "Activator"), ("Faz3W8Loc", "Location"),
                       ("Faz3W8RefType", "LocationReferenceType"), ("Faz3W8Zone", "EncounterZone")):
        q = fo4_inspect_record(cfg, manifest, str(out), eid)["data"]
        assert q["found"] is True
        assert q["records"][0]["record_type"] == rtype
    # Spriggit (2nd engine): record-type folders + ECZN flags
    if (_REPO / "tools" / "spriggit" / "Spriggit.CLI.exe").exists():
        yaml_dir = staging_out / "w8-yaml"
        exp = fo4_spriggit_export(cfg, manifest, str(out), str(yaml_dir))
        assert exp["data"]["ok"]
        yamls = list(yaml_dir.rglob("*.yaml"))
        blob = "\n".join(p.read_text(encoding="utf-8") for p in yamls)
        assert any("Activators" in str(p) for p in yamls)
        assert any("EncounterZones" in str(p) for p in yamls)
        assert "NeverResets" in blob and "Workshop" in blob


def test_create_activator_control_script(real_env, staging_out):
    """Faz 3 / W6.5-gap: an ACTI with a VMAD control-script binding (scripts[] = compiled .psc
    class name + typed properties). The .pex is compiled separately (fo4_papyrus_build); this
    writes the VMAD metadata, which round-trips from the on-disk binary + auto-adds the object
    property's master."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W65Script.esp"
    spec = {"records": [{
        "type": "activator", "editorId": "Faz3W65ScriptTrigger", "name": "Scripted Trigger",
        "scripts": [{"name": "MCPControlScript", "properties": [
            {"name": "TargetQuest", "type": "object", "value": "01CA7D:Fallout4.esm"},
            {"name": "Threshold", "type": "int", "value": 3},
        ]}],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]   # the object property's FormKey auto-added it
    rec = data["records"][0]
    assert rec["scriptCount"] == 1             # VMAD round-tripped from the on-disk binary


# ---------------- Faz 3 / W8.5: door-link (XTEL) teleport ----------------

def test_create_rejects_teleport_without_door(tmp_path):
    """A placedObject teleport needs a destination 'door' FormKey."""
    spec = {"records": [{"type": "Cell", "editorId": "BadDoor",
                         "placedObjects": [{"base": "0001A4:Fallout4.esm",
                                            "teleport": {"position": [0, 0, 0]}}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_cell_door_teleport(real_env, staging_out):
    """Faz 3 / W8.5: a door REFR with an XTEL teleport (destination door + spawn position/
    rotation) round-trips from the on-disk binary — the link that makes a new interior reachable."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W85Door.esp"
    spec = {"records": [{
        "type": "Cell", "editorId": "Faz3W85Room", "lightingTemplate": "0300E2:Fallout4.esm",
        "placedObjects": [{
            "editorId": "Faz3W85Door", "base": "0001A4:Fallout4.esm", "position": [0, 0, 0],
            "teleport": {"door": "01F3BC:Fallout4.esm", "position": [100, 200, 0],
                         "rotation": [0, 0, 1.57]},
        }],
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    c = data["records"][0]
    assert c["placedObjects"][0]["teleportDoor"] == "01F3BC:Fallout4.esm"


# ---------- A-disk (RE finding): isolated-interior navmesh on a new cell ----------

def test_create_cell_navmesh_rejects_bad_floor(tmp_path):
    """navmesh.floor must be a 4-element [minX,minY,maxX,maxY] box (Python-level shape check)."""
    spec = {"records": [{"type": "Cell", "editorId": "NavBad",
                         "navmesh": {"floor": [0, 0, 256]}}]}  # only 3
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_cell_with_navmesh(real_env, staging_out):
    """A-disk: a NEW interior cell carrying an AUTHORED navmesh — a rectangular floor that the
    CLI auto-triangulates into a vertex grid + 2 tris/grid-cell with edge-link adjacency. A 2x2
    grid -> 9 vertices, 8 triangles. Proves disk-authorability (round-trips from the on-disk
    binary); in-game pathing is the separate §4 freeze gate (not asserted here)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3NavmeshCell.esp"
    spec = {"records": [{
        "type": "Cell", "editorId": "NavmeshRoom", "lightingTemplate": "0300E2:Fallout4.esm",
        "placedObjects": [{"base": "01BA19:Fallout4.esm", "position": [0, 0, 0]}],
        "navmesh": {"floor": [-256, -256, 256, 256], "z": 0, "divisionsX": 2, "divisionsY": 2},
    }]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    c = data["records"][0]
    assert c["navmeshCount"] == 1
    assert c["navmeshVerts"] == 9   # (2+1)*(2+1)
    assert c["navmeshTris"] == 8    # 2 per grid cell * 4 cells
    # 2nd engine: Spriggit serializes the NAVM record
    ydir = staging_out / "navmesh_yaml"
    fo4_spriggit_export(cfg, manifest, str(out), str(ydir))
    blob = "\n".join(p.read_text(encoding="utf-8") for p in ydir.rglob("*.yaml"))
    assert "NavigationMesh" in blob


# ---------------- Faz 3 / W7: AI Package (PACK) template-bind + NPC binding ----------------

def test_create_package_and_npc_binding(real_env, staging_out):
    """Faz 3 / W7: a PACK template-bind (PackageTemplate + type + flags + ownerQuest) + an NPC
    that binds an existing package (npc.Packages). Both round-trip; FormLinks auto-add the
    master. The Data input-map (per-template semantic index) is the deferred research gate."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W7Pack.esp"
    spec = {"records": [
        {"type": "package", "editorId": "Faz3W7Patrol",
         "packageTemplate": "0655AE:Fallout4.esm", "packageType": "PackageTemplate",
         "flags": ["MustComplete"], "ownerQuest": "01F398:Fallout4.esm"},
        {"type": "npc", "editorId": "Faz3W7Guard", "name": "Guard",
         "packages": ["0655AE:Fallout4.esm"]},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert "Fallout4.esm" in data["masters"]
    pack, npc = data["records"]
    assert pack["packageTemplate"] == "0655AE:Fallout4.esm"
    assert pack["type"] == "PackageTemplate"
    assert pack["flagCount"] == 1
    assert pack["ownerQuest"] == "01F398:Fallout4.esm"
    assert npc["packageCount"] == 1
    q = fo4_inspect_record(cfg, manifest, str(out), "Faz3W7Patrol")["data"]
    assert q["found"] is True
    assert q["records"][0]["record_type"] == "Package"


def test_create_package_rejects_data_location_without_template(real_env, staging_out):
    """W7-Data: a location data-input needs a packageTemplate (the slot index is defined by
    the template) — reject fail-closed before any write."""
    import pytest
    from fo4_mcp.errors import Fo4McpError
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Faz3W7DataBad.esp"
    spec = {"records": [
        {"type": "package", "editorId": "Faz3W7DataBad",
         "dataLocation": {"target": "000014:Fallout4.esm", "radius": 256}},
    ]}
    with pytest.raises(Fo4McpError, match="packageTemplate"):
        fo4_create_record(cfg, manifest, spec, str(out))
    assert not out.exists()


def test_create_package_with_location_data_input(real_env, staging_out):
    """W7-Data: a Travel PACK with a 'Place to Travel' location data-input. The slot index is
    resolved by name against the live Fallout4.esm template (002CB0), so the child's Data key +
    DataInputVersion stay aligned with the engine binding. Needs the FO4 install for the lookup."""
    import pytest
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "Data" / "Fallout4.esm").is_file():
        pytest.skip("FO4 install (Fallout4.esm) not available for template lookup")
    out = staging_out / "Faz3W7DataTravel.esp"
    spec = {"records": [
        {"type": "package", "editorId": "Faz3W7TravelToPlayer",
         "packageTemplate": "002CB0:Fallout4.esm", "packageType": "Package",
         "dataLocation": {"input": "Place to Travel", "targetType": "reference",
                          "target": "000014:Fallout4.esm", "radius": 256}},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    pack = data["records"][0]
    assert pack["dataInputCount"] == 1
    assert pack["dataLocationCount"] == 1
    # the template's input version carried over (proves we read the live template)
    assert pack["dataInputVersion"] >= 1


# ---------------- Faz 3 / W11a: integration assembly (multi-system single plugin) ----------------

def test_integration_assembly_single_plugin(real_env, staging_out):
    """Faz 3 / W11a: a whole world-content slice assembled in ONE plugin from one spec —
    Quest + NPC + interior Cell (with the NPC placed inside it) + Story Manager node (that
    auto-starts the quest). Proves the locked rule 'binary-write serializes to one plugin,
    single FormID allocator': records get sequential FormIDs (0x800+), and INTRA-spec cross-
    references (cell.placedNpc -> the NPC; smqn.quest -> the quest) resolve as self-mod refs
    (the plugin is NOT added as its own master; only Fallout4.esm for the vanilla links)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "W11aIntegration.esp"
    spec = {"records": [
        {"type": "quest", "editorId": "W11aQuest", "name": "Test Quest",
         "questType": "SideQuests", "stages": [{"index": 10, "logEntry": "Begin."}]},
        {"type": "npc", "editorId": "W11aNpc", "name": "Quest Giver", "race": "013746:Fallout4.esm"},
        {"type": "cell", "editorId": "W11aCell", "name": "Quest Room",
         "lightingTemplate": "0300E2:Fallout4.esm",
         "placedNpcs": [{"base": "000801:W11aIntegration.esp", "position": [0, 0, 0]}]},
        {"type": "smqn", "editorId": "W11aNode", "parent": "029152:Fallout4.esm",
         "flags": ["Random"], "quests": [{"quest": "000800:W11aIntegration.esp"}]},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    # only Fallout4.esm is a master — self-references do NOT add the plugin as its own master
    assert data["masters"] == ["Fallout4.esm"]
    recs = {r["editorId"]: r for r in data["records"]}
    assert recs["W11aQuest"]["formKey"] == "000800:W11aIntegration.esp"
    assert recs["W11aNpc"]["formKey"] == "000801:W11aIntegration.esp"
    # intra-spec cross-references resolved to the same plugin
    assert recs["W11aCell"]["placedNpcs"][0]["base"] == "000801:W11aIntegration.esp"
    assert recs["W11aNode"]["quests"] == ["000800:W11aIntegration.esp"]
    # all four record types are independently queryable from the one plugin
    for eid, rtype in (("W11aQuest", "Quest"), ("W11aNpc", "Npc"),
                       ("W11aCell", "Cell"), ("W11aNode", "StoryManagerQuestNode")):
        q = fo4_inspect_record(cfg, manifest, str(out), eid)["data"]
        assert q["found"] is True and q["records"][0]["record_type"] == rtype


# ---------------- Book/Note (coupon MVP) + LeveledItem override (loot injection) ----------------

def test_create_rejects_book_negative_value(tmp_path):
    """A book's value reuses the shared item range (>= 0)."""
    spec = {"records": [{"type": "book", "editorId": "BadBook", "value": -5}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_leveleditemoverride_without_source(tmp_path):
    """A leveledItemOverride needs a sourcePlugin (the plugin holding the target list)."""
    spec = {"records": [{"type": "leveledItemOverride", "target": "067396:Fallout4.esm",
                         "entries": [{"reference": "000800:X.esp"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_leveleditemoverride_without_target(tmp_path):
    """A leveledItemOverride needs a 'target' (the LVLI FormKey to override)."""
    spec = {"records": [{"type": "leveledItemOverride", "sourcePlugin": "Fallout4.esm",
                         "entries": [{"reference": "000800:X.esp"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_book_note_roundtrip(real_env, staging_out):
    """Coupon MVP: a BOOK authored as a readable note. The body (BookText) round-trips
    byte-exact — including non-ASCII (cent / em-dash / trademark), which proves the writer's
    1252 string encoding (InvariantGlobalization removed) survives serialize->disk."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponBook.esp"
    body = "Save 10¢ on your next tin of CRAM™ — now with 15% more meat-like product!"
    spec = {"records": [
        {"type": "book", "editorId": "TestCouponCram", "name": "Cram Rebate",
         "text": body, "value": 0, "weight": 0},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["formKey"].endswith(":CouponBook.esp")
    assert rec["bookText"] == body          # byte-exact, non-ASCII preserved
    assert rec["value"] == 0
    # independently queryable as a Book
    q = fo4_inspect_record(cfg, manifest, str(out), "TestCouponCram")["data"]
    assert q["found"] is True and q["records"][0]["record_type"] == "Book"


def test_create_leveleditem_override_injection(real_env, staging_out):
    """Loot injection: a coupon LVLI grafted onto vanilla LL_Food_Packaged (067396) via a
    leveledItemOverride. ADDITIVE — the 14 vanilla entries (incl. SugarBombs 0330F2) survive
    and our coupon sub-list is appended; Fallout4.esm auto-adds as master from the preserved
    FormKey. Needs the FO4 install (the override DeepCopies the live vanilla list)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "Data" / "Fallout4.esm").is_file():
        pytest.skip("FO4 install (Fallout4.esm) not available for the override DeepCopy")
    esm = str(cfg.fo4_install_dir / "Data" / "Fallout4.esm")
    out = staging_out / "CouponInject.esp"
    spec = {"records": [
        {"type": "book", "editorId": "InjCouponA", "name": "Coupon A", "text": "free A", "value": 0},
        {"type": "leveledItem", "editorId": "InjCouponLL",
         "entries": [{"reference": "000800:CouponInject.esp"}]},   # -> the book at 0x800
        {"type": "leveledItemOverride", "sourcePlugin": esm, "target": "067396:Fallout4.esm",
         "entries": [{"reference": "000801:CouponInject.esp"}]},   # -> the LVLI at 0x801
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    assert data["masters"] == ["Fallout4.esm"]
    ov = [r for r in data["records"] if r["type"] == "leveledItemOverride"][0]
    assert ov["formKey"] == "067396:Fallout4.esm"          # true override (master FormKey kept)
    assert ov["entryCount"] == 15                          # 14 vanilla + our coupon list
    refs = [e["reference"] for e in ov["entries"]]
    assert "0330F2:Fallout4.esm" in refs                   # vanilla SugarBombs preserved (additive)
    assert "000801:CouponInject.esp" in refs               # our coupon sub-list injected


def test_create_rejects_materialswap_without_substitutions(tmp_path):
    """An MSWP needs a non-empty 'substitutions' list (nothing to swap otherwise)."""
    spec = {"records": [{"type": "materialSwap", "editorId": "EmptySwap", "substitutions": []}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_rejects_materialswap_substitution_missing_path(tmp_path):
    """Each substitution needs BOTH original and replacement .bgsm paths."""
    spec = {"records": [{"type": "materialSwap", "editorId": "HalfSwap",
                         "substitutions": [{"original": "Materials\\a.bgsm"}]}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_materialswap_roundtrip(real_env, staging_out):
    """Coupon visual: an MSWP retexture map. The original->replacement .bgsm pair round-trips,
    proving the swap survives serialize->disk so a model can reference it."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponSwap.esp"
    orig = "Materials\\Interface\\Newspaper\\DN101Note.bgsm"
    repl = "Materials\\PrewarCoupons\\coupon_cram.bgsm"
    spec = {"records": [
        {"type": "materialSwap", "editorId": "TestCouponMSWP",
         "substitutions": [{"original": orig, "replacement": repl}]},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["formKey"].endswith(":CouponSwap.esp")
    assert rec["substitutionCount"] == 1
    sub = rec["substitutions"][0]
    assert sub["original"] == orig and sub["replacement"] == repl


def test_create_book_with_model_and_materialswap_roundtrip(real_env, staging_out):
    """Coupon visual end-to-end: a book carries a world-model nif (MODL) + a MaterialSwap link
    to an in-plugin MSWP (minted at 0x800, so the book at 0x801 references it). modelFile and
    the swap FormKey both round-trip — the on-disk wiring that makes the coupon show its art."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponVisual.esp"
    spec = {"records": [
        {"type": "materialSwap", "editorId": "VisCouponMSWP",
         "substitutions": [{"original": "Materials\\Interface\\Newspaper\\DN101Note.bgsm",
                            "replacement": "Materials\\PrewarCoupons\\coupon_cram.bgsm"}]},
        {"type": "book", "editorId": "VisCoupon", "name": "Cram Coupon", "text": "5¢ off",
         "value": 0, "weight": 0.1, "model": "Props\\DN101Note.nif",
         "materialSwap": "000800:CouponVisual.esp"},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    book = [r for r in data["records"] if r["type"] == "book"][0]
    assert book["modelFile"] == "Props\\DN101Note.nif"
    assert book["materialSwap"] == "000800:CouponVisual.esp"   # links the MSWP minted first


def test_create_rejects_misc_negative_value(tmp_path):
    """MISC shares the item value range with book/armor: a negative value is rejected."""
    spec = {"records": [{"type": "misc", "editorId": "BadMisc", "value": -5}]}
    with pytest.raises(Fo4McpError):
        fo4_create_record(_cfg(tmp_path), _MANIFEST, spec, "staging/x.esp")


def test_create_misc_clutter_roundtrip(real_env, staging_out):
    """Coupon-as-MISC (pickupable clutter, the BOOK->MISC pivot — books don't pair with DYNAMIC
    havok). name + world-model nif (MODL) + value/weight round-trip, and the record is
    independently queryable as a MiscItem (proves the new writer case + readback)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponMisc.esp"
    spec = {"records": [
        {"type": "misc", "editorId": "TestCouponMisc", "name": "Cram™ Rebate",
         "value": 0, "weight": 0.0, "model": "PrewarCoupons\\coupon_cram.nif"},
    ]}
    data = fo4_create_record(cfg, manifest, spec, str(out))["data"]
    assert data["wrote"] is True
    rec = data["records"][0]
    assert rec["type"] == "misc"
    assert rec["formKey"].endswith(":CouponMisc.esp")
    assert rec["name"] == "Cram™ Rebate"                       # non-ASCII preserved
    assert rec["modelFile"] == "PrewarCoupons\\coupon_cram.nif"
    assert rec["value"] == 0
    # independently queryable as a MiscItem (not a Book)
    q = fo4_inspect_record(cfg, manifest, str(out), "TestCouponMisc")["data"]
    assert q["found"] is True and q["records"][0]["record_type"] == "MiscItem"


def test_create_misc_obnd_nonzero(real_env, staging_out):
    """OBND regression guard: a model-bearing MISC must NOT ship all-zero Object Bounds — that was
    the coupon no-show / dead-Inspect root cause (FO4 frames the inventory preview camera from OBND).
    Explicit objectBounds round-trips; omitting it still yields a non-zero default (never zero)."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponObnd.esp"
    spec = {"records": [
        {"type": "misc", "editorId": "ObndExplicit", "name": "Bounded",
         "model": "PrewarCoupons\\coupon_cram.nif", "objectBounds": [-5, -4, -1, 5, 4, 1]},
        {"type": "misc", "editorId": "ObndDefault", "name": "Defaulted",
         "model": "PrewarCoupons\\coupon_cram.nif"},   # no objectBounds -> writer default, still non-zero
    ]}
    recs = fo4_create_record(cfg, manifest, spec, str(out))["data"]["records"]
    explicit = [r for r in recs if r["formKey"].endswith(":CouponObnd.esp")][0]
    assert explicit["objectBounds"] == [-5, -4, -1, 5, 4, 1]
    assert all(r.get("objectBoundsZero") is False for r in recs)   # neither ships a zero box


def test_create_misc_preview_transform(real_env, staging_out):
    """PTRN regression guard: a flat-MISC's Pip-Boy/Inspect 3D preview is framed by a Preview Transform
    (TRNS record), which is SEPARATE from the world Model. Missing PTRN = blank inventory preview (the
    coupon no-show second root cause). previewTransform must round-trip onto the MISC record."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "CouponPtrn.esp"
    spec = {"records": [
        {"type": "misc", "editorId": "PtrnFramed", "name": "Framed",
         "model": "PrewarCoupons\\coupon_cram.nif", "objectBounds": [-5, -4, -1, 5, 4, 1],
         "previewTransform": "1CF028:Fallout4.esm"},
    ]}
    recs = fo4_create_record(cfg, manifest, spec, str(out))["data"]["records"]
    rec = [r for r in recs if r["formKey"].endswith(":CouponPtrn.esp")][0]
    assert rec["previewTransform"] == "1CF028:Fallout4.esm"
