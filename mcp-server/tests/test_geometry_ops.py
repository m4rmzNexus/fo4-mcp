"""geometry_ops — FO4 geometry-writer subprocess-shim tests (Faz C).

The geometry WRITE path crosses the GPL boundary into the nifsharp-cli exe (NiflySharp, GPL-3.0),
which is build-GATED. So the always-run tests here lock the MIT-clean orchestration invariants that
must hold WITHOUT the exe: the Steam-Data write gate, the graceful "shim not built (gated)" error,
and the client-side mesh validation. The real geometry round-trip is integration-gated behind a
require_or_skip_nifsharp_cli guard (mirrors conftest.require_or_skip_mutagen_cli), so the pure-Python
CI lane stays green until the user builds the exe.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp import geometry_ops
from fo4_mcp.config import Config
from fo4_mcp.errors import ErrorCode, Fo4McpError, PathForbiddenError
from fo4_mcp.manifest import Manifest


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _empty_manifest(repo_root: Path) -> Manifest:
    # No nifsharp-cli entry -> _nifsharp_cli_binary returns None (the gated state).
    return Manifest(tools={}, source_path=repo_root / "tools" / "MANIFEST.md")


def _good_mesh() -> dict:
    # a minimal 2-triangle quad; counts (uvs == vertices) are consistent
    return {
        "vertices": [[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
        "uvs": [[0, 0], [1, 0], [1, 1], [0, 1]],
        "triangles": [[0, 1, 2], [0, 2, 3]],
    }


# ---- mesh validation (pure, always runs) ----
def test_validate_mesh_accepts_minimal():
    geometry_ops.validate_mesh(_good_mesh())               # no raise


def test_validate_mesh_rejects_missing_required():
    m = _good_mesh()
    del m["triangles"]
    with pytest.raises(Fo4McpError):
        geometry_ops.validate_mesh(m)


def test_validate_mesh_rejects_unknown_key():
    m = _good_mesh()
    m["bogus"] = 1
    with pytest.raises(Fo4McpError):
        geometry_ops.validate_mesh(m)


def test_validate_mesh_rejects_count_mismatch():
    m = _good_mesh()
    m["normals"] = [[0, 0, 1], [0, 0, 1]]                  # 2 normals != 4 verts
    with pytest.raises(Fo4McpError):
        geometry_ops.validate_mesh(m)


def test_validate_mesh_rejects_empty():
    with pytest.raises(Fo4McpError):
        geometry_ops.validate_mesh({"vertices": [], "uvs": [], "triangles": []})


# ---- binary resolver (always runs) ----
def test_nifsharp_cli_binary_none_when_unbuilt(tmp_path):
    assert geometry_ops._nifsharp_cli_binary(_cfg(tmp_path), _empty_manifest(tmp_path)) is None


# ---- MCP wrapper gates (always run; exercise the firewall, not the exe) ----
def test_build_forbidden_output_raises(tmp_path):
    # Steam Data is refused BEFORE any subprocess/template work.
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.nif"
    with pytest.raises(PathForbiddenError):
        geometry_ops.fo4_nif_build(
            _cfg(tmp_path), _empty_manifest(tmp_path),
            template_nif="staging/tpl.nif", mesh=_good_mesh(), output_nif=forbidden)


def test_build_raises_clear_gated_error_when_shim_missing(tmp_path):
    """The headline: with no exe built, fo4_nif_build raises a CLEAR gated error and NEVER claims
    a silent success."""
    cfg = _cfg(tmp_path)
    # a present template (so we pass the template-exists check and reach the gate)
    tpl = tmp_path / "staging" / "tpl.nif"
    tpl.parent.mkdir(parents=True, exist_ok=True)
    tpl.write_bytes(b"\x00")                                # contents irrelevant — we never parse it here
    with pytest.raises(Fo4McpError) as ei:
        geometry_ops.fo4_nif_build(
            cfg, _empty_manifest(tmp_path),
            template_nif="staging/tpl.nif", mesh=_good_mesh(), output_nif="staging/out.nif")
    assert ei.value.code == ErrorCode.TOOL_BINARY_MISSING
    assert "not built" in ei.value.message and "gated" in ei.value.message
    assert ei.value.details.get("gated") is True
    # and it must NOT have written an output file (no false artifact)
    assert not (tmp_path / "staging" / "out.nif").exists()


def test_build_missing_template_raises(tmp_path):
    with pytest.raises(Fo4McpError) as ei:
        geometry_ops.fo4_nif_build(
            _cfg(tmp_path), _empty_manifest(tmp_path),
            template_nif="staging/nope.nif", mesh=_good_mesh(), output_nif="staging/out.nif")
    assert ei.value.code == ErrorCode.INVALID_ARGUMENT


# ---- integration round-trip (skipped until the exe is built) ----
def require_or_skip_nifsharp_cli(cfg, manifest) -> None:
    """Skip when the GPL-isolated geometry shim isn't built (mirrors conftest.require_or_skip_mutagen_cli)."""
    if geometry_ops._nifsharp_cli_binary(cfg, manifest) is None:
        pytest.skip("nifsharp-cli not built (geometry shim gated)")


def test_geometry_roundtrip_integration(tmp_path):
    cfg = _cfg(tmp_path)
    manifest = _empty_manifest(tmp_path)
    require_or_skip_nifsharp_cli(cfg, manifest)
    pytest.skip("template-edit round-trip needs a real FO4 BSTriShape template + the built exe; "
                "wire up once nifsharp-cli is published")
