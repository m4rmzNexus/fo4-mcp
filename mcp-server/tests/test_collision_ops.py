"""collision_ops — FO4 convex-collision (hknpConvexPolytopeShape) authoring tests.

All fixtures here are SYNTHETIC (a unit cube + a tetrahedron, built in-test), never Bethesda assets,
so the suite stays copyright-clean. The byte-exact proof against the real vanilla
Foundation_BrickRed01.nif donor (decode -> scipy-regenerate planes from the donor's own hull verts ->
order-independent plane-set match -> Tier-1 patch round-trip, block length unchanged) was run live
in-session and printed PASS; here we lock the codec/math invariants without any game data.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.collision_ops import (
    compute_hull, decode_polytope, patch_polytope, _planes_match, _find_polytope_header,
    HKVEC4, HAVOK_TO_GAME, PACK_MAGIC0, PACK_MAGIC1,
)
from fo4_mcp.errors import Fo4McpError


# ---- synthetic geometry ----
def _unit_cube() -> list[list[float]]:
    """8 corners of a cube spanning [-1, +1] on every axis (in havok-metric units)."""
    return [[x, y, z] for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)]


def _tetra() -> list[list[float]]:
    return [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


# ---- compute_hull: a cube -> 8 verts, 6 planes with the right normals/offsets ----
def test_unit_cube_yields_8_verts_6_planes():
    h = compute_hull(_unit_cube(), in_game_units=False)
    assert h["vertexCount"] == 8
    assert h["planeCount"] == 6                      # coplanar triangle facets deduped (not 12)


def test_unit_cube_plane_normals_and_offsets():
    """The 6 unique planes are the +-X/+-Y/+-Z axis faces; each is a UNIT normal with offset -1, and
    every input corner is interior (n.x + d <= 0). This is FO4's stored convention (disk-proven)."""
    h = compute_hull(_unit_cube(), in_game_units=False)
    axis = {(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)}
    got = set()
    for nx, ny, nz, d in h["planes"]:
        n = (round(nx), round(ny), round(nz))
        assert abs(nx * nx + ny * ny + nz * nz - 1.0) < 1e-6      # unit normal
        assert abs(d - (-1.0)) < 1e-6                              # face at distance 1 from origin
        got.add(n)
    assert got == axis
    # interior test: all 8 corners satisfy n.x + d <= eps for every plane
    for vx, vy, vz in _unit_cube():
        for nx, ny, nz, d in h["planes"]:
            assert nx * vx + ny * vy + nz * vz + d <= 1e-6


def test_unit_cube_vert_w_is_radius():
    h = compute_hull(_unit_cube(), in_game_units=False, radius=0.25)
    assert all(abs(v[3] - 0.25) < 1e-9 for v in h["hullVerts"])    # hkVector4 .w = convex radius


def test_game_units_are_divided_by_69_99():
    """A cube given in GAME units is stored in havok-metric (game / 69.99)."""
    cube_game = [[c * HAVOK_TO_GAME for c in v] for v in _unit_cube()]
    h = compute_hull(cube_game, in_game_units=True)
    assert max(abs(v[i]) for v in h["hullVerts"] for i in range(3)) == pytest.approx(1.0, abs=1e-4)


def test_tetra_yields_4_verts_4_planes():
    h = compute_hull(_tetra(), in_game_units=False)
    assert h["vertexCount"] == 4 and h["planeCount"] == 4


def test_too_few_points_raises():
    with pytest.raises(Fo4McpError):
        compute_hull([[0, 0, 0], [1, 0, 0], [0, 1, 0]], in_game_units=False)


def test_bad_shape_raises():
    with pytest.raises(Fo4McpError):
        compute_hull([[0, 0], [1, 0], [0, 1], [1, 1]], in_game_units=False)


# ---- a SYNTHETIC packfile so codec tests touch zero game data ----
def _synthetic_phys_block(verts, planes, header_off=64, tail=48) -> bytes:
    """Build a minimal byte blob shaped like a bhkPhysicsSystem nif block: [u32 dataSize][hkPackfile
    header magic][padding up to header_off][u16 mini-header][vert vec4s][plane vec4s][tail]. Only the
    parts _find_polytope_header / decode_polytope / patch_polytope read are real."""
    vc, pc = len(verts), len(planes)
    pack = bytearray(header_off + 16 + vc * HKVEC4 + pc * HKVEC4 + tail)
    struct.pack_into("<II", pack, 0, PACK_MAGIC0, PACK_MAGIC1)             # packfile magic @0
    struct.pack_into("<8H", pack, header_off, vc, 0, pc, 0, 0, 0, 0, 0)    # mini-header
    p = header_off + 16
    for v in verts:
        struct.pack_into("<4f", pack, p, *v); p += HKVEC4
    for pl in planes:
        struct.pack_into("<4f", pack, p, *pl); p += HKVEC4
    return struct.pack("<I", len(pack)) + bytes(pack)                       # u32 dataSize prefix


def test_decode_synthetic_polytope_roundtrips():
    h = compute_hull(_unit_cube(), in_game_units=False)
    blk = _synthetic_phys_block(h["hullVerts"], h["planes"])
    dec = decode_polytope(blk)
    assert dec["vertexCount"] == 8 and dec["planeCount"] == 6
    assert _planes_match(dec["planes"], h["planes"])
    for a, b in zip(dec["hullVerts"], h["hullVerts"]):
        assert all(abs(x - y) < 1e-5 for x, y in zip(a, b))


def test_find_header_skips_false_positives():
    """The scanner must land on the real mini-header (preceded by packfile magic + padding), not on
    the magic bytes at offset 0."""
    h = compute_hull(_unit_cube(), in_game_units=False)
    blk = _synthetic_phys_block(h["hullVerts"], h["planes"], header_off=80)
    pack = blk[4:]
    assert _find_polytope_header(pack) == 80


def test_patch_polytope_same_count_swaps_floats():
    """Patch a cube packfile with a SHIFTED cube (same 8/6 counts) -> only the vec4s change, block
    length is preserved, and the new geometry re-decodes."""
    base = compute_hull(_unit_cube(), in_game_units=False)
    blk = _synthetic_phys_block(base["hullVerts"], base["planes"])
    shifted = compute_hull([[c * 2 for c in v] for v in _unit_cube()], in_game_units=False)

    patched = patch_polytope(blk, shifted["hullVerts"], shifted["planes"])
    assert len(patched) == len(blk)                                   # same-size in-place swap
    dec = decode_polytope(patched)
    assert dec["vertexCount"] == 8 and dec["planeCount"] == 6
    # new verts are the doubled cube (+-2), planes still unit normals with offset -2
    assert max(abs(v[i]) for v in dec["hullVerts"] for i in range(3)) == pytest.approx(2.0, abs=1e-4)
    assert _planes_match(dec["planes"], shifted["planes"])


def test_patch_polytope_count_mismatch_raises():
    """A different topology (tetra, 4/4) cannot Tier-1-patch a cube donor (8/6) -> the Tier-2 gate."""
    cube = compute_hull(_unit_cube(), in_game_units=False)
    blk = _synthetic_phys_block(cube["hullVerts"], cube["planes"])
    tetra = compute_hull(_tetra(), in_game_units=False)
    with pytest.raises(Fo4McpError):
        patch_polytope(blk, tetra["hullVerts"], tetra["planes"])


def test_decode_rejects_non_packfile():
    with pytest.raises(Fo4McpError):
        decode_polytope(struct.pack("<I", 100) + bytes(100))          # no packfile magic


# ---- plane-set comparison helper ----
def test_planes_match_is_order_independent():
    a = [[1, 0, 0, -1], [0, 1, 0, -1], [0, 0, 1, -1]]
    b = [[0, 0, 1, -1], [1, 0, 0, -1], [0, 1, 0, -1]]               # reordered
    assert _planes_match(a, b)
    assert not _planes_match(a, [[1, 0, 0, -1], [0, 1, 0, -1], [0, 0, 1, -2]])
