"""Integration test for fo4_papyrus_build — runs real Caprica subprocess.

The test uses the live fixture at `fixtures/papyrus-test/src/TestScript.psc`
and the extracted Base scripts under `tools/papyrus-source/Base`. If
either is missing (fresh checkout, Session 4 prereqs not run), the test
is skipped — it's an integration smoke check, not a unit boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fo4_mcp.config import load_config
from fo4_mcp.errors import NotImplementedYetError
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import fo4_papyrus_build, _papyrus_import_root


_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _REPO_ROOT / "fixtures" / "papyrus-test" / "src" / "TestScript.psc"
_FRAG_FIXTURE = (
    _REPO_ROOT / "fixtures" / "papyrus-test" / "src"
    / "Fragments" / "Quests" / "QF_MCPLoopQuest_01000800.psc"
)
_BASE = _REPO_ROOT / "tools" / "papyrus-source" / "Base"
_CAPRICA = _REPO_ROOT / "tools" / "caprica" / "Caprica.exe"


@pytest.fixture
def env():
    cfg = load_config()
    manifest = parse_manifest(_REPO_ROOT / "tools" / "MANIFEST.md")
    return cfg, manifest


def _skip_if_no_caprica():
    if not _CAPRICA.exists():
        pytest.skip(f"caprica not extracted at {_CAPRICA}")
    if not _FIXTURE.exists():
        pytest.skip(f"papyrus fixture missing at {_FIXTURE}")
    if not _BASE.exists():
        pytest.skip(f"Base scripts not extracted at {_BASE}")


def test_papyrus_import_root_derives_namespace_root():
    """Faz 2.2: a namespaced fragment ("Fragments:Quests:QF_...") resolves to its
    namespace ROOT so Caprica's declared-namespace check passes; a flat script
    resolves to its own dir (prior behaviour). No toolchain needed — pure parse."""
    if not _FRAG_FIXTURE.exists() or not _FIXTURE.exists():
        pytest.skip("papyrus fixtures missing")
    assert Path(_papyrus_import_root(_FRAG_FIXTURE)) == (
        _REPO_ROOT / "fixtures" / "papyrus-test" / "src"
    ).resolve()
    assert Path(_papyrus_import_root(_FIXTURE)) == _FIXTURE.resolve().parent


def test_caprica_compiles_namespaced_quest_fragment(env):
    """Faz 2.2 — the .pex loop: a real (namespaced) quest fragment compiles via the
    default import path, and the produced .pex lands at the namespace subdir. The
    produced path mirrors the metadata ScriptName (':' -> '/'), which is exactly
    what fo4_create_record (2.1f) writes into QuestAdapter.Script.Name — so the
    compiled .pex is the one FO4 loads for that quest. (In-game firing is a
    separate, user-gated check; this proves the authoring->compile binding.)"""
    _skip_if_no_caprica()
    if not _FRAG_FIXTURE.exists():
        pytest.skip(f"fragment fixture missing at {_FRAG_FIXTURE}")
    cfg, manifest = env
    # No import_paths: exercise the default (MCP-wrapper) code path, which must
    # derive the namespace root itself — the bug Faz 2.2 fixed.
    envelope = fo4_papyrus_build(
        cfg, manifest,
        source_paths=[str(_FRAG_FIXTURE)],
        output_dir=str(_REPO_ROOT / "staging" / "faz22-fragment-test"),
    )
    data = envelope["data"]
    assert data["ok"] is True, f"diagnostics: {data['diagnostics']}"
    script_name = "Fragments:Quests:QF_MCPLoopQuest_01000800"  # the VMAD metadata Name
    expected_pex = script_name.replace(":", "/") + ".pex"
    assert expected_pex in data["produced"]
    assert data["diagnostics"] == []


def test_caprica_backend_compiles_test_script(tmp_path, env):
    _skip_if_no_caprica()
    cfg, manifest = env
    envelope = fo4_papyrus_build(
        cfg, manifest,
        source_paths=[str(_FIXTURE)],
        output_dir=str(_REPO_ROOT / "staging" / "papyrus-build-test"),
        backend="caprica",
    )
    assert envelope["ok"] is True
    data = envelope["data"]
    assert data["backend"] == "caprica"
    assert data["ok"] is True
    assert data["produced"], "Caprica should have produced TestScript.pex"
    assert "TestScript.pex" in data["produced"]
    assert data["diagnostics"] == [], f"Unexpected diagnostics: {data['diagnostics']}"


def test_ck_backend_raises_not_implemented(env):
    cfg, manifest = env
    with pytest.raises(NotImplementedYetError):
        fo4_papyrus_build(
            cfg, manifest,
            source_paths=[str(_FIXTURE)],
            output_dir="staging/ignored",
            backend="ck",
        )


def test_unknown_backend_rejected(env):
    cfg, manifest = env
    from fo4_mcp.errors import Fo4McpError
    with pytest.raises(Fo4McpError) as exc:
        fo4_papyrus_build(
            cfg, manifest,
            source_paths=[str(_FIXTURE)],
            output_dir="staging/ignored",
            backend="caprique",  # type: ignore[arg-type]
        )
    assert "unknown backend" in str(exc.value).lower()


def test_empty_source_paths_rejected(env):
    cfg, manifest = env
    from fo4_mcp.errors import Fo4McpError
    with pytest.raises(Fo4McpError) as exc:
        fo4_papyrus_build(
            cfg, manifest,
            source_paths=[],
            output_dir="staging/ignored",
        )
    assert "source_paths" in str(exc.value).lower()


def test_output_outside_safe_zone_blocked(env, tmp_path):
    _skip_if_no_caprica()
    cfg, manifest = env
    from fo4_mcp.errors import PathForbiddenError
    forbidden = Path(r"C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/Scripts")
    with pytest.raises(PathForbiddenError):
        fo4_papyrus_build(
            cfg, manifest,
            source_paths=[str(_FIXTURE)],
            output_dir=str(forbidden),
        )
