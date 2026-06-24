"""Canonical pure-Python FO4 .nif operations — the permanent home for the coupon/flat-MISC
visual pipeline fixes (see memory: fo4-flat-misc-render-3-causes).

PyNifly cannot round-trip two FO4-specific things, and both render fine in the WORLD but break the
strict Pip-Boy/Inspect inventory preview render path:
  1. bhkPhysicsSystem Havok blob  -> regenerated (1572->1684B) -> CRASH. Fix: splice donor bytes.
  2. BSLightingShaderProperty textureClampMode (+0x3c) -> left 0xFFFFFFFF instead of 3 (WRAP) ->
     blank preview. Fix: patch to 3.
This module parses the FO4 nif container, applies both fixes (postprocess), and validates a nif so a
broken one never deploys. MCP wrappers (fo4_postprocess_nif / fo4_validate_nif) live at the bottom.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import Fo4McpError, ErrorCode, ok
from .safety import check_write

COLLISION_TYPES = ("bhkNPCollisionObject", "bhkPhysicsSystem")
CLAMP_OFFSET = 0x3C          # BSLightingShaderProperty: Texture Clamp Mode (uint)
CLAMP_WRAP_BOTH = 3          # WRAP_S_WRAP_T — the vanilla value PyNifly drops to -1


# ---------------------------------------------------------------- container parse
def parse(path: str | Path) -> dict[str, Any]:
    """Parse the FO4 nif container into block-level pieces (no per-block field decode beyond what
    the fixes/validation need). Mirrors splice_collision.py's proven parser."""
    b = bytearray(Path(path).read_bytes())
    p = b.index(b"\n") + 1
    p += 4 + 1 + 4                                   # version, endian, user version
    nblocks, = struct.unpack_from("<I", b, p); p += 4
    bsver, = struct.unpack_from("<I", b, p); p += 4
    for _ in range(3):                               # export-info shortstrings (u8 len)
        p += 1 + b[p]
    if bsver >= 130:                                 # FO4: + maxFilepath shortstring
        p += 1 + b[p]
    ntypes, = struct.unpack_from("<H", b, p); p += 2
    types: list[str] = []
    for _ in range(ntypes):
        n = struct.unpack_from("<I", b, p)[0]; types.append(b[p + 4:p + 4 + n].decode("latin1")); p += 4 + n
    tidx = list(struct.unpack_from(f"<{nblocks}H", b, p)); p += 2 * nblocks
    sizes_off = p
    sizes = list(struct.unpack_from(f"<{nblocks}I", b, p)); p += 4 * nblocks
    nstr, = struct.unpack_from("<I", b, p); p += 8   # numStrings + maxStrLen
    for _ in range(nstr):
        n = struct.unpack_from("<I", b, p)[0]; p += 4 + n
    ngroups, = struct.unpack_from("<I", b, p); p += 4 + 4 * ngroups
    blocks_start = p
    blocks = []
    for i in range(nblocks):
        blocks.append(b[p:p + sizes[i]]); p += sizes[i]
    tail = b[p:]
    return dict(buf=b, nblocks=nblocks, types=[types[i] for i in tidx], sizes=sizes,
                sizes_off=sizes_off, blocks_start=blocks_start, blocks=blocks, tail=tail, bsver=bsver)


def _one(meta: dict, typename: str) -> int | None:
    idxs = [i for i, t in enumerate(meta["types"]) if t == typename]
    return idxs[0] if len(idxs) == 1 else None


# ---------------------------------------------------------------- field decode (validation)
def clamp_mode(meta: dict) -> int | None:
    i = _one(meta, "BSLightingShaderProperty")
    if i is None:
        return None
    return struct.unpack_from("<I", meta["blocks"][i], CLAMP_OFFSET)[0]


def _tri_header(blk: bytes) -> tuple[int, int, int, int] | None:
    """BSTriShape: locate vertex data. Returns (vertDataOff, numVert, vertexSize, vertexDesc)."""
    nE = struct.unpack_from("<I", blk, 4)[0]
    base = 100 + nE * 4                       # name4 numExtra4 +extras controller4 flags4 trans12 rot36 scale4 coll4 boundC12 boundR4 skin4 shader4 alpha4
    vdesc = struct.unpack_from("<Q", blk, base)[0]
    desc_end = base + 8
    numVert = struct.unpack_from("<H", blk, desc_end + 4)[0]  # numTri(u32) numVert(u16) dataSize(u32)
    vdata = desc_end + 10
    vsize = (vdesc & 0x0F) * 4
    if vsize == 0 or numVert == 0 or vdata + numVert * vsize > len(blk):
        return None
    return vdata, numVert, vsize, vdesc


def vertex_flags(meta: dict) -> dict[str, bool]:
    i = _one(meta, "BSTriShape")
    if i is None:
        return {}
    h = _tri_header(meta["blocks"][i])
    if not h:
        return {}
    vf = (h[3] >> 44) & 0xFFF
    return {"VERTEX": bool(vf & 0x1), "UV": bool(vf & 0x2), "NORMAL": bool(vf & 0x8),
            "TANGENT": bool(vf & 0x10), "COLOR": bool(vf & 0x20)}


def mesh_z_extent(meta: dict) -> float | None:
    """Z thickness of the visible mesh (half-float positions). None if the parse is uncertain."""
    i = _one(meta, "BSTriShape")
    if i is None:
        return None
    blk = meta["blocks"][i]
    h = _tri_header(blk)
    if not h:
        return None
    vdata, numVert, vsize, _ = h
    zs = [struct.unpack_from("<e", blk, vdata + k * vsize + 4)[0] for k in range(numVert)]  # pos.z = 3rd half
    return max(zs) - min(zs)


def texture_set(meta: dict) -> list[str]:
    i = _one(meta, "BSShaderTextureSet")
    if i is None:
        return []
    blk = meta["blocks"][i]
    nt = struct.unpack_from("<I", blk, 0)[0]
    out, p = [], 4
    for _ in range(nt):
        n = struct.unpack_from("<I", blk, p)[0]; p += 4
        out.append(blk[p:p + n].decode("latin1")); p += n
    return out


# ---------------------------------------------------------------- transforms (fixes)
def splice_collision_bytes(donor: dict, target: dict) -> bytearray:
    if donor["types"] != target["types"]:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"block layout mismatch:\n donor ={donor['types']}\n target={target['types']}", {})
    new_sizes = list(target["sizes"])
    new_blocks = list(target["blocks"])
    for t in COLLISION_TYPES:
        di, ti = _one(donor, t), _one(target, t)
        if di is None or ti is None or di != ti:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"{t} block index mismatch donor={di} target={ti}", {})
        new_blocks[ti] = donor["blocks"][di]
        new_sizes[ti] = donor["sizes"][di]
    out = bytearray(target["buf"][:target["blocks_start"]])
    struct.pack_into(f"<{target['nblocks']}I", out, target["sizes_off"], *new_sizes)
    for blk in new_blocks:
        out += blk
    out += target["tail"]
    return out


def fix_clamp_in_bytes(buf: bytearray, meta: dict) -> bool:
    """Patch BSLightingShaderProperty +0x3c -> 3 in `buf` (already block-spliced). Returns True if changed."""
    i = _one(meta, "BSLightingShaderProperty")
    if i is None:
        return False
    pos = meta["blocks_start"] + sum(meta["sizes"][:i]) + CLAMP_OFFSET
    if struct.unpack_from("<I", buf, pos)[0] == CLAMP_WRAP_BOTH:
        return False
    struct.pack_into("<I", buf, pos, CLAMP_WRAP_BOTH)
    return True


# ---------------------------------------------------------------- validation
_REQUIRED = ("BSTriShape", "BSLightingShaderProperty", "BSShaderTextureSet")

def validate(target_path: str | Path, donor_path: str | Path | None = None,
             textures_root: str | Path | None = None) -> dict[str, Any]:
    """Gate a flat-MISC nif against the 3 stacked render bugs + enablers. ok=False blocks deploy."""
    return validate_meta(parse(target_path),
                         parse(donor_path) if donor_path else None,
                         textures_root)


def validate_meta(meta: dict, donor_meta: dict | None = None,
                  textures_root: str | Path | None = None) -> dict[str, Any]:
    """validate() core over already-parsed metas (so unit tests can drive it with crafted blocks)."""
    issues: list[str] = []
    info: dict[str, Any] = {}

    for t in _REQUIRED:
        if _one(meta, t) is None:
            issues.append(f"missing required block: {t}")

    # 1) collision — PyNifly regenerates it (crash). Exact donor size match is the integrity proof.
    pi = _one(meta, "bhkPhysicsSystem")
    if pi is None:
        issues.append("no bhkPhysicsSystem block (collision missing — engine may crash on a physical item)")
    else:
        info["bhkPhysicsSystem"] = meta["sizes"][pi]
        if donor_meta:
            di = _one(donor_meta, "bhkPhysicsSystem")
            if di is not None and meta["sizes"][pi] != donor_meta["sizes"][di]:
                issues.append(f"collision corrupted: bhkPhysicsSystem {meta['sizes'][pi]}B != donor "
                              f"{donor_meta['sizes'][di]}B (PyNifly havok regen — re-splice)")

    # 2) texture clamp mode — None/-1 -> blank inventory preview
    cm = clamp_mode(meta)
    info["textureClampMode"] = cm
    if cm != CLAMP_WRAP_BOTH:
        issues.append(f"BSLightingShaderProperty textureClampMode={cm if cm is None else hex(cm)} "
                      f"(expect 3=WRAP) — PyNifly leaves -1 -> blank Pip-Boy/Inspect preview")

    # 3) vertex format — lit shader needs normals + tangents
    vf = vertex_flags(meta)
    info["vertexFlags"] = [k for k, v in vf.items() if v]
    for need in ("NORMAL", "TANGENT"):
        if not vf.get(need):
            issues.append(f"vertex format missing {need}")

    # 4) diffuse texture present (+ exists, if a root is given)
    tex = texture_set(meta)
    info["diffuse"] = tex[0] if tex else None
    if not tex or not tex[0]:
        issues.append("BSShaderTextureSet diffuse slot [0] is empty")
    elif textures_root:
        dds = Path(textures_root) / tex[0].replace("\\", "/")
        if not dds.is_file():
            issues.append(f"diffuse texture not found: {tex[0]}")

    # 5) thickness — zero-Z double surface z-fights/culls in preview (best-effort)
    z = mesh_z_extent(meta)
    if z is not None:
        info["meshZExtent"] = round(z, 4)
        if z < 0.1:
            issues.append(f"mesh Z extent {z:.3f} ~flat (zero thickness z-fights/blanks the preview) — give real thickness")
    else:
        info["meshZExtent"] = "unparsed"

    return {"ok": not issues, "issues": issues, "info": info}


# ---------------------------------------------------------------- MCP entry points
def fo4_postprocess_nif(cfg: Config, target_nif: str, donor_nif: str,
                        output_nif: str | None = None) -> dict[str, Any]:
    """Apply both PyNifly FO4 fixes in one pass: splice the donor collision + patch texture clamp
    mode. Output gated to staging/fixtures (in-place if output_nif omitted). Run after every
    PyNifly FO4 export of a flat-MISC nif."""
    tgt = Path(target_nif)
    if not tgt.is_absolute():
        tgt = (cfg.repo_root / tgt).resolve()
    don = Path(donor_nif)
    if not don.is_absolute():
        don = (cfg.repo_root / don).resolve()
    if not tgt.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"target nif not found: {tgt}", {})
    if not don.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"donor nif not found: {don}", {})

    out = Path(output_nif).resolve() if output_nif else tgt
    if not Path(out).is_absolute():
        out = (cfg.repo_root / out).resolve()
    check_write(out, cfg.repo_root)                       # raises on DENY (Steam Data etc.)

    target_meta = parse(tgt)
    donor_meta = parse(don)
    spliced = splice_collision_bytes(donor_meta, target_meta)
    after = parse_bytes(spliced)                          # re-parse the spliced buffer for clamp offsets
    clamp_fixed = fix_clamp_in_bytes(spliced, after)

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists() and out == tgt:
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())
    out.write_bytes(spliced)

    return ok({
        "output": str(out),
        "bytes": len(spliced),
        "backup": str(backup) if backup else None,
        "collision_spliced": True,
        "clamp_mode_fixed": clamp_fixed,
        "validation": validate(out, donor_path=don),
    })


def parse_bytes(buf: bytes | bytearray) -> dict[str, Any]:
    """parse() on an in-memory buffer (for re-reading a just-spliced nif without a temp file)."""
    import tempfile, os
    fd, tmp = tempfile.mkstemp(suffix=".nif")
    try:
        os.write(fd, bytes(buf)); os.close(fd)
        return parse(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def fo4_validate_nif(cfg: Config, nif: str, donor_nif: str | None = None,
                     textures_root: str | None = None) -> dict[str, Any]:
    """Read-only Layer-0 gate for a flat-MISC nif: collision integrity (vs donor), texture clamp
    mode, vertex normals/tangents, diffuse texture path, mesh thickness. Returns ok({ok, issues, info}).

    textures_root: a Data-style root (the folder that CONTAINS a Textures/ dir — diffuse paths are
    "textures\\...") to confirm the diffuse .dds exists. For a modded item pass the mod folder (textures
    live there, not Steam Data); omit to skip the existence check (path is still checked non-empty)."""
    p = Path(nif)
    if not p.is_absolute():
        p = (cfg.repo_root / p).resolve()
    if not p.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"nif not found: {p}", {})
    don = None
    if donor_nif:
        don = Path(donor_nif)
        if not don.is_absolute():
            don = (cfg.repo_root / don).resolve()
    tex_root = None
    if textures_root:
        tex_root = Path(textures_root)
        if not tex_root.is_absolute():
            tex_root = (cfg.repo_root / tex_root).resolve()
    return ok(validate(p, donor_path=don, textures_root=tex_root))
