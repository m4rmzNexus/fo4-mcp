"""fo4_lint_npc_template tests — NPC template-coherence + FaceGen-coverage lint (Faz 3 / W3f).

The orphan-flag / clean-template integration tests author a plugin with the real
mutagen-cli writer (skipped if it is not built). The FaceGen-coverage test reads a real
CC plugin (ccOTMFO4001-Remnants.esl) and is skipped if it is not installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.tools import (
    fo4_create_record,
    fo4_lint_npc_template,
)

from conftest import require_or_skip_writer

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = parse_manifest(_REPO / "tools" / "MANIFEST.md")
_REMNANTS = Path(
    "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/ccOTMFO4001-Remnants.esl"
)


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


@pytest.fixture
def real_env():
    return load_config(), _MANIFEST


@pytest.fixture
def staging_out():
    import shutil
    d = _REPO / "staging" / "faz3-lint-test"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _skip_if_no_writer(cfg, manifest):
    require_or_skip_writer(cfg, manifest)


def test_lint_npc_missing_plugin(tmp_path):
    """A nonexistent plugin path raises before any subprocess."""
    with pytest.raises(Fo4McpError):
        fo4_lint_npc_template(_cfg(tmp_path), _MANIFEST, str(tmp_path / "nope.esp"))


def test_lint_npc_orphan_template_flags(real_env, staging_out):
    """useTemplateActors flags set without a DefaultTemplate = inert (error). The writer
    can author this footgun directly (W3c); the lint must catch it."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Orphan.esp"
    spec = {"records": [{"type": "Npc", "editorId": "OrphanTmpl",
                         "useTemplateActors": ["Traits", "Stats"]}]}  # NO defaultTemplate
    assert fo4_create_record(cfg, manifest, spec, str(out))["data"]["wrote"] is True
    lint = fo4_lint_npc_template(cfg, manifest, str(out))["data"]
    assert lint["npc_count"] == 1
    assert lint["error_count"] == 1
    assert lint["verdict"] == "bug"
    orphan = [f for f in lint["findings"] if f["rule"] == "orphan_template_flags"]
    assert len(orphan) == 1
    assert orphan[0]["editorId"] == "OrphanTmpl"


def test_lint_npc_clean_template(real_env, staging_out):
    """DefaultTemplate + Traits, no authored FaceGen (the writer can't author HeadParts/
    FaceMorphs) -> no orphan flag and no facegen finding -> clean."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    out = staging_out / "Clean.esp"
    spec = {"records": [{"type": "Npc", "editorId": "CleanTmpl",
                         "defaultTemplate": "113341:Fallout4.esm",
                         "useTemplateActors": ["Traits", "Stats", "Factions"]}]}
    assert fo4_create_record(cfg, manifest, spec, str(out))["data"]["wrote"] is True
    lint = fo4_lint_npc_template(cfg, manifest, str(out))["data"]
    assert lint["npc_count"] == 1
    assert lint["error_count"] == 0
    assert lint["facegen_needed_count"] == 0
    assert lint["verdict"] == "clean"


def test_lint_npc_facegen_coverage_on_remnants(real_env):
    """Real CC plugin: every Remnants NPC carries own face data -> facegen_needed warnings,
    none orphan (CC is well-authored) -> verdict 'review'. Validates the W3f probe data path
    end-to-end. Skipped if the CC file is not installed."""
    cfg, manifest = real_env
    _skip_if_no_writer(cfg, manifest)
    if not _REMNANTS.exists():
        pytest.skip("ccOTMFO4001-Remnants.esl not installed")
    lint = fo4_lint_npc_template(cfg, manifest, str(_REMNANTS))["data"]
    assert lint["npc_count"] == 87
    assert lint["error_count"] == 0            # well-authored CC: no orphan template flags
    assert lint["facegen_needed_count"] > 0    # every NPC has own face data
    assert lint["facegen_inherits_traits_count"] > 0  # some inherit Traits from a template
    assert lint["verdict"] == "review"
    fg = [f for f in lint["findings"] if f["rule"] == "facegen_needed"]
    assert all("faceData" in f for f in fg)
