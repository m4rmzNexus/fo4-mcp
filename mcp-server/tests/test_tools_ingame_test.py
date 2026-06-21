"""fo4_run_ingame_test tests — job rendering, dry_run gating, simulated run.

No real game launch: it's long + machine-locked + needs Steam. We test the pure
job-file renderer (validation + exact output), the dry_run plan (no launch), and
a fully monkeypatched execute path that simulates appear -> exit and exercises
the success-judging logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fo4_mcp.ingame_test as ingame_test
from fo4_mcp.config import Config
from fo4_mcp.errors import ErrorCode, Fo4McpError
from fo4_mcp.ingame_test import fo4_run_ingame_test, render_job


def _cfg(tmp_path: Path, *, mo2: Path | None = None, docs: Path | None = None) -> Config:
    return Config(
        repo_root=tmp_path, fo4_install_dir=None, fo4_user_docs=docs,
        fo4_localappdata=None, mo2_instance_dir=mo2, tools_dir=tmp_path / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


# ---------------- render_job: output ----------------

def test_render_default_mcploop():
    job = render_job({
        "commands": ["startquest {Q}", "setstage {Q} 10"],
        "resolves": [{"key": "Q", "plugin": "MCPLoopTest.esp", "form_id": "0x800"}],
    })
    lines = job.splitlines()
    assert lines[0].startswith("#")
    assert "save quickload" in lines
    assert "resolve Q MCPLoopTest.esp 0x800" in lines
    assert "settle_ms 4000" in lines
    assert "gap_ms 1500" in lines
    assert "post_ms 8000" in lines
    assert "cmd startquest {Q}" in lines
    assert "cmd setstage {Q} 10" in lines
    assert job.endswith("\n")


def test_render_save_modes():
    assert "save mostrecent" in render_job({"commands": ["qqq"], "save": "mostrecent"})
    assert "save coc qasmoke" in render_job({"commands": ["qqq"], "save": "coc:qasmoke"})


def test_render_custom_timings_and_int_formid():
    job = render_job({
        "commands": ["setstage {Q} 20"],
        "resolves": [{"key": "Q", "plugin": "My.esp", "form_id": 0x800}],
        "settle_ms": 1000, "gap_ms": 500, "post_ms": 2000,
    })
    assert "settle_ms 1000" in job
    assert "gap_ms 500" in job
    assert "post_ms 2000" in job
    assert "resolve Q My.esp 0x800" in job  # int 0x800 normalized to hex


def test_render_formid_bare_string_is_hex():
    job = render_job({
        "commands": ["startquest {Q}"],
        "resolves": [{"key": "Q", "plugin": "My.esp", "form_id": "f99"}],
    })
    assert "resolve Q My.esp 0xF99" in job


# ---------------- render_job: validation ----------------

@pytest.mark.parametrize("spec", [
    {},                                              # no commands
    {"commands": []},                                # empty
    {"commands": [""]},                              # blank command
    {"commands": ["ok", "bad\ninject"]},             # newline injection
    {"commands": ["qqq"], "save": "bogus"},          # bad save mode
    {"commands": ["qqq"], "save": "coc:two words"},  # coc cell with space
    {"commands": ["setstage {Z} 10"],                # placeholder w/o resolve
     "resolves": [{"key": "Q", "plugin": "M.esp", "form_id": "0x1"}]},
    {"commands": ["qqq"],                             # bad plugin suffix
     "resolves": [{"key": "Q", "plugin": "M.txt", "form_id": "0x1"}]},
    {"commands": ["qqq"],                             # form_id out of range
     "resolves": [{"key": "Q", "plugin": "M.esp", "form_id": "0x1000000"}]},
    {"commands": ["qqq"],                             # duplicate key
     "resolves": [{"key": "Q", "plugin": "A.esp", "form_id": "0x1"},
                  {"key": "Q", "plugin": "B.esp", "form_id": "0x2"}]},
    {"commands": ["qqq"], "settle_ms": -5},           # negative timing
])
def test_render_validation_errors(spec):
    with pytest.raises(Fo4McpError) as ei:
        render_job(spec)
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


# ---------------- render_job: navtest ----------------

def test_render_navtest_line():
    job = render_job({
        "commands": ["prid {N}", "startcombat 14"],
        "resolves": [{"key": "N", "plugin": "FO4MCP_NavTest.esp", "form_id": "0x800"}],
        "save": "coc:MCPNavTest",
        "navtest": {"npc": "N", "sample_ms": 500, "duration_s": 20},
    })
    lines = job.splitlines()
    assert "save coc MCPNavTest" in lines
    assert "navtest N 500 20" in lines
    assert "cmd startcombat 14" in lines


def test_render_navtest_defaults():
    job = render_job({
        "commands": ["prid {N}"],
        "resolves": [{"key": "N", "plugin": "M.esp", "form_id": "0x800"}],
        "navtest": {"npc": "N"},
    })
    assert "navtest N 1000 15" in job  # default sample_ms / duration_s


@pytest.mark.parametrize("nav", [
    {"npc": "Z"},               # npc not a declared resolve key
    {"npc": "N", "sample_ms": 0},   # non-positive sample_ms
    {"npc": "N", "duration_s": -1},  # negative duration
    "notadict",                 # wrong type
])
def test_render_navtest_validation_errors(nav):
    with pytest.raises(Fo4McpError) as ei:
        render_job({
            "commands": ["prid {N}"],
            "resolves": [{"key": "N", "plugin": "M.esp", "form_id": "0x800"}],
            "navtest": nav,
        })
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


def test_execute_parses_navmesh_verdict(tmp_path, monkeypatch):
    cfg, diag, _papyrus = _prep_execute(tmp_path)
    diag.write_text(
        "[NAVTEST] poll start npc=N samples=15\n"
        "[NAVTEST] sample 1 ok=1 pos=(-448.0,0.0,0.0) pathing=1 valid=1 complete=0\n"
        "[NAVTEST] samples=15 anyPathing=1 anyPathValid=1 moved=312.4 on_navmesh=1 VERDICT=PASS\n"
        "[seq] UI: qqq (auto-quit)\n"
    )
    _patch_runtime(monkeypatch, [2000, None])

    out = fo4_run_ingame_test(
        cfg,
        {"commands": ["prid {N}", "startcombat 14"],
         "resolves": [{"key": "N", "plugin": "FO4MCP_NavTest.esp", "form_id": "0x800"}],
         "save": "coc:MCPNavTest",
         "navtest": {"npc": "N", "sample_ms": 1000, "duration_s": 15}},
        dry_run=False,
    )
    v = out["data"]["navmesh_verdict"]
    assert v is not None
    assert v["verdict"] == "PASS"
    assert v["on_navmesh"] is True
    assert v["any_path_valid"] is True
    assert v["moved"] == pytest.approx(312.4)
    assert v["samples"] == 15


# ---------------- dry_run plan (no launch) ----------------

def test_dry_run_returns_plan_without_launching(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("dry_run must NOT launch")

    monkeypatch.setattr(ingame_test, "_launch_detached", _boom)
    mo2 = tmp_path / "mo2"
    mo2.mkdir()
    docs = tmp_path / "docs"
    out = fo4_run_ingame_test(
        _cfg(tmp_path, mo2=mo2, docs=docs),
        {"commands": ["startquest {Q}"],
         "resolves": [{"key": "Q", "plugin": "MCPLoopTest.esp", "form_id": "0x800"}],
         "success_pattern": "FAZ22"},
        dry_run=True,
    )
    data = out["data"]
    assert data["dry_run"] is True
    assert data["success_pattern"] == "FAZ22"
    assert data["launch_argv"][1] == "moshortcut://:F4SE"
    assert "cmd startquest {Q}" in data["job_text"]
    # job file must NOT have been written
    assert not (tmp_path / "tools" / "commonlibf4-template" / "ingame-job.txt").exists()


# ---------------- simulated execute (monkeypatched) ----------------

def _prep_execute(tmp_path: Path) -> tuple[Config, Path, Path]:
    """Build a cfg whose paths exist; return (cfg, diag_path, papyrus_path)."""
    mo2 = tmp_path / "mo2"
    mo2.mkdir()
    (mo2 / "ModOrganizer.exe").write_bytes(b"MZ")
    docs = tmp_path / "docs"
    (docs / "Logs" / "Script").mkdir(parents=True)
    papyrus = docs / "Logs" / "Script" / "Papyrus.0.log"
    tmpl = tmp_path / "tools" / "commonlibf4-template"
    tmpl.mkdir(parents=True)
    diag = tmpl / "runner-diag.log"
    return _cfg(tmp_path, mo2=mo2, docs=docs), diag, papyrus


def _patch_runtime(monkeypatch, ws_seq):
    """No-op sleeps, logged-in Steam, no real kills, recorded launch, WS sequence."""
    monkeypatch.setattr(ingame_test.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(ingame_test, "_steam_active_user", lambda: 1)
    monkeypatch.setattr(ingame_test, "_kill", lambda *_a, **_k: None)
    launches: list[tuple[object, str]] = []
    monkeypatch.setattr(ingame_test, "_launch_detached",
                        lambda exe, arg: launches.append((exe, arg)))
    seq = iter(ws_seq)
    monkeypatch.setattr(ingame_test, "_tasklist_ws_mb", lambda _img: next(seq, None))
    return launches


def test_execute_success_with_papyrus_match(tmp_path, monkeypatch):
    cfg, diag, papyrus = _prep_execute(tmp_path)
    diag.write_text("[load] plugin loaded\n[seq] cmd: setstage 07000800 10\n[seq] UI: qqq (auto-quit)\n")
    papyrus.write_text("[06/20/2026] [FAZ22] QF_MCPLoopTest Fragment_Stage_0010_Item_00 fired\n")
    launches = _patch_runtime(monkeypatch, [2000, None])  # appear, then gone

    out = fo4_run_ingame_test(
        cfg,
        {"commands": ["setstage {Q} 10"],
         "resolves": [{"key": "Q", "plugin": "MCPLoopTest.esp", "form_id": "0x800"}],
         "success_pattern": "FAZ22"},
        dry_run=False,
    )
    data = out["data"]
    assert data["success"] is True
    assert data["appeared"] is True
    assert data["exited"] is True
    assert data["sequence_completed"] is True
    assert data["papyrus_matches"] and "FAZ22" in data["papyrus_matches"][0]
    assert launches and launches[0][1] == "moshortcut://:F4SE"  # (exe, arg)
    # job file WAS written for the live run
    assert (tmp_path / "tools" / "commonlibf4-template" / "ingame-job.txt").exists()


def test_execute_failure_when_pattern_absent(tmp_path, monkeypatch):
    cfg, diag, papyrus = _prep_execute(tmp_path)
    diag.write_text("[seq] UI: qqq (auto-quit)\n")
    papyrus.write_text("[06/20/2026] nothing interesting here\n")
    _patch_runtime(monkeypatch, [2000, None])

    out = fo4_run_ingame_test(
        cfg,
        {"commands": ["setstage {Q} 10"],
         "resolves": [{"key": "Q", "plugin": "MCPLoopTest.esp", "form_id": "0x800"}],
         "success_pattern": "FAZ22"},
        dry_run=False,
    )
    assert out["data"]["success"] is False
    assert out["data"]["appeared"] is True


def test_execute_no_pattern_success_on_clean_exit(tmp_path, monkeypatch):
    cfg, diag, _papyrus = _prep_execute(tmp_path)
    diag.write_text("[seq] UI: qqq (auto-quit)\n")
    _patch_runtime(monkeypatch, [2000, None])

    out = fo4_run_ingame_test(
        cfg, {"commands": ["qqq"]}, dry_run=False,
    )
    # no success_pattern -> success = appeared & exited & sequence_completed
    assert out["data"]["success"] is True
    assert out["data"]["sequence_completed"] is True


def test_execute_steam_logged_out_raises(tmp_path, monkeypatch):
    cfg, _diag, _papyrus = _prep_execute(tmp_path)
    monkeypatch.setattr(ingame_test, "_steam_active_user", lambda: 0)
    monkeypatch.setattr(ingame_test, "_launch_detached",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not launch")))
    with pytest.raises(Fo4McpError) as ei:
        fo4_run_ingame_test(cfg, {"commands": ["qqq"]}, dry_run=False)
    assert ei.value.code == ErrorCode.ENV_FO4_NOT_DETECTED


def test_execute_killed_hang_when_no_exit(tmp_path, monkeypatch):
    cfg, diag, _papyrus = _prep_execute(tmp_path)
    diag.write_text("[poll] TIMEOUT 120s; never reached in-game — forcing qqq\n")
    # appears, then stays present for the whole short run_timeout
    monkeypatch.setattr(ingame_test.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(ingame_test, "_steam_active_user", lambda: 1)
    monkeypatch.setattr(ingame_test, "_kill", lambda *_a, **_k: None)
    monkeypatch.setattr(ingame_test, "_launch_detached", lambda *a, **k: None)
    monkeypatch.setattr(ingame_test, "_tasklist_ws_mb", lambda _img: 2000)  # never gone

    out = fo4_run_ingame_test(
        cfg, {"commands": ["qqq"], "run_timeout_s": 3}, dry_run=False,
    )
    data = out["data"]
    assert data["appeared"] is True
    assert data["exited"] is False
    assert data["killed_hung"] is True
    assert data["plugin_timed_out"] is True
    assert data["success"] is False
