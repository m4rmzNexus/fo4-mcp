"""FO4 .nif geometry writer — the arbitrary-mesh authoring half of the Blender->FO4 asset
pipeline (asset-pipeline-completion-roadmap Faz C, blokör #2 + #4).

This is the MIT-clean PYTHON ORCHESTRATION ONLY. It never imports NiflySharp (GPL-3.0): the actual
BSTriShape geometry/tangent write crosses the GPL boundary in a SEPARATE PROCESS — a standalone net9
console exe `nifsharp-cli` (built under tools/nifsharp-cli/, gitignored), driven exactly like the
proven mutagen-cli subprocess firewall (see tools.py:_cell_info / _mutagen_cli_binary). Our code only
shells out via run_tool() across the process boundary, identical to fo4_inspect_record's cell-info
backend. License rationale: docs/karar-7-license-strategy.md (Karar 7 — GPL tools subprocess-only,
never distributed → MIT stays clean).

WHY a writer at all (vs nif_ops byte-poking): nif_ops._tri_header()'s `base = 100 + nE*4` offset is a
READ-side heuristic that CANNOT safely AUTHOR a BSTriShape — FO4's packed vertex (BSVertexDesc bitfield,
half-float positions, SNORM normals/tangents, per-vertex tangent space the lit shader requires) is
exactly what NiflySharp's BSTriShape already encodes for NiVersion 20.2.0.7 / BSVERSION 130+. So the
exe owns the WRITE path; nif_ops.parse()/validate() stay the read-side decode + Layer-0 gate.

SCOPE (MVP, Faz C): TEMPLATE-EDIT geometry replacement — load a template FO4 .nif, replace ONE plain
static BSTriShape's geometry from a small JSON mesh, recompute tangents+bounds, save. Every OTHER block
(collision bhkPhysicsSystem, BSLightingShaderProperty, NiNode tree) is byte-preserved, so it does NOT
regenerate Havok the way PyNifly does. Full from-scratch nif synthesis is a V2 item (open a TASKS.md
entry first). Faz D adds a second collision-writer verb to the same exe.

GATED: the dotnet build of nifsharp-cli is a user bekleme-noktası (C1 GPL decision + heavy `dotnet
publish`). Until the user builds it, _nifsharp_cli_binary() returns None and fo4_nif_build() raises a
CLEAR Fo4McpError "geometry shim not built (gated)" — nothing here claims false capability.

MCP wrapper (fo4_nif_build) lives at the bottom, mirroring bgsm_ops.fo4_create_bgsm.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import nif_ops
from .config import Config
from .errors import ErrorCode, Fo4McpError, ok
from .manifest import Manifest
from .safety import check_write
from .subprocess_wrap import run_tool

# Mesh JSON contract written for the exe (Python writes it; the exe reads + validates it).
# {"shape": <name|index, optional>, "vertices": [[x,y,z],...], "uvs": [[u,v],...],
#  "normals": [[x,y,z],...]?, "tangents": [[x,y,z],...]?, "triangles": [[a,b,c],...]}
_MESH_REQUIRED = ("vertices", "uvs", "triangles")
_MESH_OPTIONAL = ("normals", "tangents", "shape")


def _resolve(cfg: Config, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (cfg.repo_root / q).resolve()


def _nifsharp_cli_binary(cfg: Config, manifest: Manifest) -> Path | None:
    """Resolve the optional geometry-writer CLI, or None if not built/present.

    Mirrors tools._mutagen_cli_binary EXACTLY: never raises — the binary is an opt-in,
    build-gated tool (GPL-3.0 NiflySharp wrap under tools/nifsharp-cli/), so absence just
    means "the geometry shim isn't built yet" and the caller degrades gracefully."""
    entry = manifest.get("nifsharp-cli")
    if entry is None or not entry.is_resolved:
        return None
    binary = Path(entry.binary_path)
    if not binary.is_absolute():
        binary = (cfg.repo_root / binary).resolve()
    return binary if binary.exists() else None


def validate_mesh(mesh: dict[str, Any]) -> None:
    """Reject a malformed mesh dict before we write the JSON (cheap client-side gate; the exe
    re-validates counts authoritatively and Fail()s on mismatch)."""
    if not isinstance(mesh, dict):
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, "mesh must be a JSON object", {})
    missing = [k for k in _MESH_REQUIRED if k not in mesh]
    if missing:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"mesh missing required key(s): {', '.join(missing)}",
                          {"required": list(_MESH_REQUIRED)})
    bad = [k for k in mesh if k not in _MESH_REQUIRED and k not in _MESH_OPTIONAL]
    if bad:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"unknown mesh key(s): {', '.join(sorted(bad))}",
                          {"known": list(_MESH_REQUIRED) + list(_MESH_OPTIONAL)})
    nv = len(mesh["vertices"])
    if nv == 0 or len(mesh["triangles"]) == 0:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, "mesh has no vertices or no triangles", {})
    # counts that MUST match the vertex count (the exe also enforces this, exit 2)
    for key in ("uvs", "normals", "tangents"):
        if key in mesh and len(mesh[key]) != nv:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                              f"mesh '{key}' count {len(mesh[key])} != vertices {nv}",
                              {"vertices": nv, key: len(mesh[key])})


# ---------------------------------------------------------------- MCP wrapper
def fo4_nif_build(cfg: Config, manifest: Manifest, template_nif: str, mesh: dict[str, Any],
                  output_nif: str, shape: str | int | None = None,
                  flip_bitangent: bool = False) -> dict[str, Any]:
    """Author FO4 geometry by replacing ONE BSTriShape in a template .nif from a JSON mesh, via the
    GPL-isolated nifsharp-cli subprocess. Every other block (collision, shader, node tree) is
    byte-preserved (no PyNifly Havok regen). Tangents+bitangents are derived if absent; bounds are
    recomputed. Output gated to staging/fixtures (Steam Data refused); the result is run through
    nif_ops.validate() as the Layer-0 gate before returning.

    GATED: until the user builds nifsharp-cli (`dotnet publish` under tools/nifsharp-cli/ — a GPL C1
    bekleme-noktası), this raises Fo4McpError "geometry shim not built (gated)" rather than claiming a
    capability it can't deliver.

    mesh keys: vertices[[x,y,z]], uvs[[u,v]], triangles[[a,b,c]] (required); normals/tangents (optional,
    derived if absent); shape (optional name|index, also accepted as the `shape` arg).
    """
    out = _resolve(cfg, output_nif)
    check_write(out, cfg.repo_root)                          # raises on DENY (Steam Data etc.)

    tpl = _resolve(cfg, template_nif)
    if not tpl.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"template nif not found: {tpl}", {})

    if shape is not None and "shape" not in mesh:
        mesh = {**mesh, "shape": shape}
    validate_mesh(mesh)

    cli = _nifsharp_cli_binary(cfg, manifest)
    if cli is None:
        # The gate: the geometry write crosses the GPL boundary and the exe isn't built. Be explicit
        # so nothing upstream mistakes this for a real (silent-noop) success — mirrors _cell_info's
        # TOOL_BINARY_MISSING path but names the build as a user-triggered checkpoint.
        raise Fo4McpError(
            ErrorCode.TOOL_BINARY_MISSING,
            "geometry shim not built (gated): nifsharp-cli (GPL-3.0 NiflySharp wrap) is not present "
            "under tools/nifsharp-cli/. Build it (user-triggered C1 decision): "
            "`dotnet publish tools/nifsharp-cli/src/NifSharp.Build.csproj -c Release -r win-x64 "
            "--self-contained false -o tools/nifsharp-cli`, then add the MANIFEST nifsharp-cli entry. "
            "See docs/faz-c-geometry-writer-design.md.",
            {"tool": "nifsharp-cli", "gated": True})

    # Write the mesh JSON to a staging-side temp file, shell to the exe, parse its one-line JSON.
    out.parent.mkdir(parents=True, exist_ok=True)
    mesh_json = out.with_suffix(out.suffix + ".mesh.json")
    mesh_json.write_text(json.dumps(mesh), encoding="utf-8")
    argv = ["build-trishape", "--in", str(tpl), "--mesh", str(mesh_json), "--out", str(out)]
    if shape is not None:
        argv += ["--shape", str(shape)]
    if flip_bitangent:
        argv += ["--flip-bitangent"]

    try:
        result = run_tool(cli, argv, timeout=cfg.subprocess_timeout)
    finally:
        try:
            mesh_json.unlink()
        except OSError:
            pass

    if not result.stdout.strip():
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_FAILED, "nifsharp-cli build-trishape produced no output",
            {"exit_code": result.exit_code, "stderr_tail": result.stderr[-2000:]})
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        raise Fo4McpError(
            ErrorCode.SUBPROCESS_OUTPUT_UNPARSEABLE, "nifsharp-cli emitted no JSON",
            {"stdout_tail": result.stdout[-500:], "stderr_tail": result.stderr[-500:]})

    # Layer-0 gate: re-parse + validate the exe's output with our own read-side decode (no NiflySharp
    # on the read path). Geometry is structurally checked (flags/bounds/thickness), NOT byte-compared
    # to the JSON input (the engine quantizes positions to half-float — see risks in the design doc).
    validation = nif_ops.validate(out)

    return ok({
        "output": str(out),
        "mode": "template-edit",
        "template": str(tpl),
        "shape": report.get("shape"),
        "numVerts": report.get("numVerts"),
        "numTris": report.get("numTris"),
        "vertexFlags": report.get("vertexFlags"),
        "boundsCenter": report.get("boundsCenter"),
        "boundsRadius": report.get("boundsRadius"),
        "tangentsCalculated": report.get("tangentsCalculated"),
        "validation": validation,
    })
