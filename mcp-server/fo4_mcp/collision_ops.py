"""Pure-Python FO4 convex-collision authoring — the Blender->FO4 asset-pipeline Faz D prototype
(asset-pipeline-completion-roadmap). MIT: scipy (BSD) + numpy (BSD) for the hull math + our own
struct codec; no GPL, no import contagion, lands beside bgsm_ops.py / nif_ops.py.

PREMISE CORRECTION (disk-proven against Foundation_BrickRed01.nif, NOT from the task's name):
FO4 does **not** use the Skyrim-era `bhkConvexVerticesShape` block — `find(b"bhkConvexVerticesShape")
== -1` in the donors. FO4 (bsVersion 130, Havok hk_2014.1.0) stores collision as a binary
**hkPackfile** (magic 0x57e0e057/0x10c0c010, fileVersion 11) embedded inside the `bhkPhysicsSystem`
nif block after a u32 dataSize prefix, and the convex shape is an **hknpConvexPolytopeShape** living
in an hknpPhysicsSystemData. The task's "vertex array + face-plane array" maps cleanly onto that
shape, which decodes as:

  * a 16-byte u16 mini-header `(vertexCount, _, planeCount, _, faceLinkCount, _, 0, 0)`, immediately
    followed by
  * VERTEX ARRAY = vertexCount x hkVector4 float32 LE = (x, y, z, w)  — w = the convex radius/shell
    (0.5 in the donor), NOT a scale; verts are in HAVOK METRIC units (game units = metric * 69.99),
  * PLANE ARRAY  = planeCount  x hkVector4 float32 LE = (nx, ny, nz, d) — UNIT outward normal +
    signed offset; an interior point satisfies nx*x + ny*y + nz*z + d <= 0 (scipy's exact convention).

The separate face/index connectivity tables that the mini-header's byte-offsets point at are left
UNTOUCHED — this module ships the proven, robust path only:

  TIER 1 (here, pure-Python, shippable): TEMPLATE FLOAT-SWAP. Compute a hull with scipy, and when its
  vertex/plane COUNTS match a donor hknpConvexPolytopeShape, overwrite ONLY the contiguous vec4
  vertex+plane region in the donor's packfile in place (counts / topology / relocation tables
  unchanged), then re-emit the patched bhkPhysicsSystem into a target nif via
  nif_ops.transplant_physics_system. Correct for boxes/simple prisms (settlement pieces, the coupon
  board) where the hull shares the donor's topology.

  TIER 2 (arbitrary topology, NOT here — gated): a NEW vertex/plane count needs the hkPackfile
  section-relocation + virtual-fixup + face/vertex-index tables rebuilt from scratch; pure-Python
  authoring of those is unproven/fragile and the robust route leans on subprocess-isolated Havok
  tooling (CLAUDE.md isolation rule). Opened as a user-gated TASKS.md item, not coded here.

MCP wrappers (fo4_make_convex_collision / fo4_inspect_collision) live at the bottom.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial import ConvexHull

from . import nif_ops
from .config import Config
from .errors import Fo4McpError, ErrorCode, ok
from .safety import check_write

# hkPackfile (the blob inside bhkPhysicsSystem, after a u32 dataSize prefix)
PACK_MAGIC0 = 0x57E0E057
PACK_MAGIC1 = 0x10C0C010
HKVEC4 = 16                         # hkVector4 = 4 x float32 LE
HAVOK_TO_GAME = 69.99               # havok metric * 69.99 = FO4 game units
DEFAULT_CONVEX_RADIUS = 0.5         # the donor's w (per-vertex shell thickness)
_PLANE_DEDUP_DECIMALS = 4           # round (a,b,c,d) to collapse scipy's coplanar triangle facets


# ---------------------------------------------------------------- scipy hull -> verts + planes
def compute_hull(verts_xyz: list[list[float]] | np.ndarray,
                 in_game_units: bool = True,
                 radius: float = DEFAULT_CONVEX_RADIUS) -> dict[str, Any]:
    """Convex hull of a point cloud -> the (vertex, plane) data an hknpConvexPolytopeShape stores.

    verts_xyz       : Nx3 mesh vertices.
    in_game_units   : True (default) divides by 69.99 so the output verts/planes are in HAVOK METRIC
                      space (what the packfile stores) — pass the raw verts of a typical Blender FO4
                      export. Pass False if your points are ALREADY in havok-metric units.
    radius          : the per-vertex convex shell (hkVector4 .w); donor uses 0.5.

    Returns {hullVerts: [[x,y,z,w], ...], planes: [[nx,ny,nz,d], ...], vertexCount, planeCount}.
    Planes use scipy's `nx*x + ny*y + nz*z + d <= 0` interior convention (== FO4's, disk-proven),
    with coplanar triangle facets deduped to unique planes (a box -> 6, not 12)."""
    pts = np.asarray(verts_xyz, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"verts must be Nx3, got shape {pts.shape}", {})
    if pts.shape[0] < 4:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"need >=4 non-coplanar points for a 3D hull, got {pts.shape[0]}", {})
    if in_game_units:
        pts = pts / HAVOK_TO_GAME

    try:
        hull = ConvexHull(pts)
    except Exception as e:                                   # QhullError: coplanar / degenerate
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"convex hull failed (points may be coplanar/degenerate): {e}", {})

    hull_verts = [[float(x), float(y), float(z), float(radius)]
                  for x, y, z in pts[hull.vertices]]

    # scipy emits one [a,b,c,d] row PER triangle facet (12 for a box); dedup coplanar -> unique planes.
    seen: dict[tuple, list[float]] = {}
    for eq in hull.equations:
        key = tuple(round(float(c), _PLANE_DEDUP_DECIMALS) for c in eq)
        if key not in seen:
            seen[key] = [float(c) for c in eq]
    planes = list(seen.values())

    return {"hullVerts": hull_verts, "planes": planes,
            "vertexCount": len(hull_verts), "planeCount": len(planes)}


# ---------------------------------------------------------------- hknpConvexPolytopeShape codec
def _packfile(phys_block: bytes) -> tuple[bytes, int]:
    """Strip bhkPhysicsSystem's u32 dataSize prefix -> (packfile_bytes, prefix_len=4). Validates magic."""
    if len(phys_block) < 8 + 24:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, "bhkPhysicsSystem block too small", {})
    pack = phys_block[4:]                                    # drop u32 dataSize
    if struct.unpack_from("<I", pack, 0)[0] != PACK_MAGIC0 or \
       struct.unpack_from("<I", pack, 4)[0] != PACK_MAGIC1:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          "not an hkPackfile (bad magic) — unexpected bhkPhysicsSystem layout", {})
    return pack, 4


def _find_polytope_header(pack: bytes) -> int | None:
    """Locate the hknpConvexPolytopeShape mini-header inside the packfile data section.

    The mini-header is the 16-byte u16 tuple (vertexCount, _, planeCount, _, faceLinkCount, _, 0, 0)
    that is IMMEDIATELY followed by `vertexCount` hkVector4 vertices then `planeCount` hkVector4
    planes. We scan for that self-consistent shape rather than hardcoding offset 1008 (which is
    donor-specific): a candidate is accepted iff the two trailing u16s are 0, the counts are sane,
    every following vertex .w is a plausible convex radius (0 < w <= 4), and every plane normal is
    unit-length. Returns the mini-header's absolute offset in `pack`, or None."""
    n = len(pack)
    for off in range(0, n - 16, 2):                          # u16-aligned
        vc, _v, pc, _p, _flc, _f, z0, z1 = struct.unpack_from("<8H", pack, off)
        if z0 or z1 or not (4 <= vc <= 256) or not (4 <= pc <= 256):
            continue
        va = off + 16
        pa = va + vc * HKVEC4
        end = pa + pc * HKVEC4
        if end > n:
            continue
        ok_verts = True
        for k in range(vc):
            w = struct.unpack_from("<f", pack, va + k * HKVEC4 + 12)[0]
            if not (0.0 < w <= 4.0):                         # convex radius / shell
                ok_verts = False
                break
        if not ok_verts:
            continue
        ok_planes = True
        for k in range(pc):
            nx, ny, nz, _d = struct.unpack_from("<4f", pack, pa + k * HKVEC4)
            if abs((nx * nx + ny * ny + nz * nz) - 1.0) > 1e-3:
                ok_planes = False
                break
        if ok_planes:
            return off
    return None


def decode_polytope(phys_block: bytes) -> dict[str, Any]:
    """Decode the hknpConvexPolytopeShape inside a bhkPhysicsSystem nif block ->
    {vertexCount, planeCount, hullVerts:[[x,y,z,w]], planes:[[nx,ny,nz,d]], headerOffset, vertOffset,
    planeOffset} (offsets are absolute in the packfile, i.e. block bytes minus the 4-byte prefix)."""
    pack, prefix = _packfile(phys_block)
    hoff = _find_polytope_header(pack)
    if hoff is None:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          "no hknpConvexPolytopeShape found (concave hknpCompressedMeshShape or a "
                          "compound shape is not a convex donor)", {})
    vc, _v, pc = struct.unpack_from("<8H", pack, hoff)[:3]
    va = hoff + 16
    pa = va + vc * HKVEC4
    verts = [list(struct.unpack_from("<4f", pack, va + k * HKVEC4)) for k in range(vc)]
    planes = [list(struct.unpack_from("<4f", pack, pa + k * HKVEC4)) for k in range(pc)]
    return {"vertexCount": vc, "planeCount": pc, "hullVerts": verts, "planes": planes,
            "headerOffset": hoff, "vertOffset": va, "planeOffset": pa, "_prefix": prefix}


def patch_polytope(phys_block: bytes, hull_verts: list[list[float]],
                   planes: list[list[float]]) -> bytes:
    """TIER 1: overwrite ONLY the vertex+plane float4 region of the donor bhkPhysicsSystem block,
    in place. Counts MUST match the donor (topology/relocation tables untouched -> robust). Returns a
    new bhkPhysicsSystem block (same length) ready for nif_ops.transplant_physics_system.

    Raises if counts differ (that is the gated Tier-2 full-packfile-author case)."""
    info = decode_polytope(phys_block)
    if len(hull_verts) != info["vertexCount"] or len(planes) != info["planeCount"]:
        raise Fo4McpError(
            ErrorCode.INVALID_ARGUMENT,
            f"count mismatch: hull has {len(hull_verts)} verts / {len(planes)} planes, donor expects "
            f"{info['vertexCount']} / {info['planeCount']}. Same-count (Tier-1 float-swap) only; a "
            f"different topology needs the gated Tier-2 full-packfile author.",
            {"donorVertexCount": info["vertexCount"], "donorPlaneCount": info["planeCount"]})

    out = bytearray(phys_block)
    base = info["_prefix"]                                   # packfile starts `base` bytes into the block
    p = base + info["vertOffset"]
    for v in hull_verts:
        struct.pack_into("<4f", out, p, *(float(x) for x in v)); p += HKVEC4
    p = base + info["planeOffset"]
    for pl in planes:
        struct.pack_into("<4f", out, p, *(float(x) for x in pl)); p += HKVEC4
    return bytes(out)


# ---------------------------------------------------------------- nif-level helpers
def _phys_block(meta: dict) -> bytes:
    i = nif_ops._one(meta, "bhkPhysicsSystem")
    if i is None:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          "nif has no (single) bhkPhysicsSystem block to read collision from", {})
    return meta["blocks"][i]


def replace_convex_in_nif(target_meta: dict, hull_verts: list[list[float]],
                          planes: list[list[float]]) -> bytearray:
    """Patch target's own hknpConvexPolytopeShape verts+planes in place and re-emit the whole nif
    buffer. Same-count Tier-1 path: the bhkPhysicsSystem keeps its EXACT size (only float4 bytes
    change), so the block-size table needs no fixup — we reassemble the buffer block-by-block with the
    one patched block swapped in. (We do NOT route through transplant_physics_system, which guards on a
    single bhkNPCollisionObject — many pieces, incl. the Foundation donor, carry two.)"""
    tp = nif_ops._one(target_meta, "bhkPhysicsSystem")
    if tp is None:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, "target nif has no (single) bhkPhysicsSystem block", {})
    patched = patch_polytope(target_meta["blocks"][tp], hull_verts, planes)  # length-preserving
    new_blocks = list(target_meta["blocks"]); new_blocks[tp] = patched
    out = bytearray(target_meta["buf"][:target_meta["blocks_start"]])        # header + size table unchanged
    for blk in new_blocks:
        out += blk
    out += target_meta["tail"]
    return out


# ---------------------------------------------------------------- MCP wrappers (optional for proto)
def _resolve(cfg: Config, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (cfg.repo_root / q).resolve()


def fo4_inspect_collision(cfg: Config, nif: str) -> dict[str, Any]:
    """Read-only: decode the hknpConvexPolytopeShape in a nif's bhkPhysicsSystem and report its hull
    vertices (havok-metric + game-unit) and face planes, plus a scipy self-check (does the hull of
    the donor's own vertices reproduce the donor's plane set?)."""
    p = _resolve(cfg, nif)
    if not p.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"nif not found: {p}", {})
    meta = nif_ops.parse(p)
    dec = decode_polytope(_phys_block(meta))
    regen = compute_hull([v[:3] for v in dec["hullVerts"]], in_game_units=False,
                          radius=dec["hullVerts"][0][3])
    return ok({
        "path": str(p),
        "vertexCount": dec["vertexCount"], "planeCount": dec["planeCount"],
        "convexRadius": dec["hullVerts"][0][3],
        "hullVertsMetric": [[round(c, 4) for c in v] for v in dec["hullVerts"]],
        "hullVertsGame": [[round(c * HAVOK_TO_GAME, 2) for c in v[:3]] for v in dec["hullVerts"]],
        "planes": [[round(c, 4) for c in pl] for pl in dec["planes"]],
        "scipyReproducesPlanes": _planes_match(dec["planes"], regen["planes"]),
    })


def fo4_make_convex_collision(cfg: Config, donor_nif: str, output_nif: str,
                              verts: list[list[float]], in_game_units: bool = True,
                              radius: float = DEFAULT_CONVEX_RADIUS) -> dict[str, Any]:
    """TIER 1 author: compute the convex hull of `verts`, and IF its vertex/plane counts match the
    donor's hknpConvexPolytopeShape, write a copy of `donor_nif` to `output_nif` with the hull's
    vertices+planes swapped in (donor packfile/topology otherwise byte-preserved). Output gated to
    staging/fixtures (Steam Data refused); .bak on overwrite. NOT in-game validated (Faz E gate)."""
    don = _resolve(cfg, donor_nif)
    out = _resolve(cfg, output_nif)
    if not don.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"donor nif not found: {don}", {})
    check_write(out, cfg.repo_root)                          # raises on DENY (Steam Data etc.)

    hull = compute_hull(verts, in_game_units=in_game_units, radius=radius)
    target_meta = nif_ops.parse(don)
    patched = replace_convex_in_nif(target_meta, hull["hullVerts"], hull["planes"])

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())
    out.write_bytes(patched)

    re = decode_polytope(_phys_block(nif_ops.parse(out)))    # verify the written bytes re-decode
    return ok({"output": str(out), "bytes": len(patched), "backup": str(backup) if backup else None,
               "vertexCount": hull["vertexCount"], "planeCount": hull["planeCount"],
               "writtenVerts": [[round(c, 4) for c in v] for v in re["hullVerts"]],
               "ingameValidated": False, "note": "collision geometry swapped; in-game validity is Faz-E gated"})


# ---------------------------------------------------------------- plane-set comparison (proof helper)
def _canon_plane(pl: list[float]) -> tuple:
    return tuple(round(float(c), _PLANE_DEDUP_DECIMALS) for c in pl)


def _planes_match(a: list[list[float]], b: list[list[float]], tol: float = 1e-3) -> bool:
    """Order-independent plane-set equality within tolerance (each plane in `a` has a near match in
    `b` and vice-versa). Used by the offline donor proof + inspect self-check."""
    if len(a) != len(b):
        return False

    def has_match(pl, pool):
        for q in pool:
            if all(abs(float(x) - float(y)) <= tol for x, y in zip(pl, q)):
                return True
        return False

    return all(has_match(pl, b) for pl in a) and all(has_match(pl, a) for pl in b)
