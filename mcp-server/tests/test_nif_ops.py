"""nif_ops — flat-MISC nif validation gate + field decoders.

Tests drive the meta-based core (validate_meta) and the block decoders with hand-crafted byte blocks
(no Bethesda assets), exercising the three stacked PyNifly/flat-MISC render bugs the gate must catch:
collision corruption, texture clamp mode != 3, zero thickness. See memory fo4-flat-misc-render-3-causes.
"""
from __future__ import annotations

import struct

from fo4_mcp import nif_ops as N


# ---- hand-crafted blocks (the only fields each decoder reads) ----
def _lsp(clamp: int) -> bytearray:
    b = bytearray(0x40)
    struct.pack_into("<I", b, N.CLAMP_OFFSET, clamp & 0xFFFFFFFF)
    return b


def _tri(z_extent: float = 0.6, normal_tangent: bool = True, num_vert: int = 4) -> bytearray:
    vf = 0x1B if normal_tangent else 0x03            # VERTEX|UV(|NORMAL|TANGENT)
    vdesc = (vf << 44) | 0x05                         # low nibble 5 -> vertex size 20
    desc_end = 108                                    # numExtra=0 layout
    b = bytearray(desc_end + 10 + num_vert * 20 + 16)
    struct.pack_into("<I", b, 4, 0)                   # numExtra
    struct.pack_into("<Q", b, 100, vdesc)
    struct.pack_into("<H", b, desc_end + 4, num_vert)
    vdata = desc_end + 10
    for k in range(num_vert):
        z = 0.0 if k < num_vert // 2 else z_extent
        struct.pack_into("<e", b, vdata + k * 20 + 4, z)   # pos.z is the 3rd half
    return b


def _texset(diffuse: str) -> bytearray:
    s = diffuse.encode("latin1")
    return bytearray(struct.pack("<I", 1) + struct.pack("<I", len(s)) + s)


def _meta(entries: list[tuple[str, bytearray]]) -> dict:
    blocks = [bytearray(b) for _, b in entries]
    return {"types": [t for t, _ in entries], "blocks": blocks,
            "sizes": [len(b) for b in blocks], "nblocks": len(blocks)}


def _good_meta(clamp=3, z=0.6, nt=True, phys=1572):
    return _meta([
        ("bhkPhysicsSystem", bytearray(phys)),
        ("BSTriShape", _tri(z, nt)),
        ("BSLightingShaderProperty", _lsp(clamp)),
        ("BSShaderTextureSet", _texset("textures\\PrewarCoupons\\coupon_cram.dds")),
    ])


_DONOR = _meta([("bhkPhysicsSystem", bytearray(1572))])


# ---- decoders ----
def test_clamp_mode_reads_offset():
    assert N.clamp_mode(_meta([("BSLightingShaderProperty", _lsp(3))])) == 3
    assert N.clamp_mode(_meta([("BSLightingShaderProperty", _lsp(0xFFFFFFFF))])) == 0xFFFFFFFF


def test_vertex_flags_detect_normal_tangent():
    assert N.vertex_flags(_meta([("BSTriShape", _tri(normal_tangent=True))]))["NORMAL"]
    assert N.vertex_flags(_meta([("BSTriShape", _tri(normal_tangent=True))]))["TANGENT"]
    assert not N.vertex_flags(_meta([("BSTriShape", _tri(normal_tangent=False))])).get("NORMAL")


def test_mesh_z_extent():
    assert abs(N.mesh_z_extent(_meta([("BSTriShape", _tri(z_extent=0.6))])) - 0.6) < 0.01
    assert N.mesh_z_extent(_meta([("BSTriShape", _tri(z_extent=0.0))])) == 0.0


def test_texture_set_reads_diffuse():
    assert N.texture_set(_meta([("BSShaderTextureSet", _texset("textures\\x.dds"))])) == ["textures\\x.dds"]


# ---- validate gate ----
def test_validate_good_passes():
    r = N.validate_meta(_good_meta(), _DONOR)
    assert r["ok"], r["issues"]
    assert r["info"]["textureClampMode"] == 3


def test_validate_flags_bad_clamp():
    r = N.validate_meta(_good_meta(clamp=0xFFFFFFFF), _DONOR)
    assert not r["ok"]
    assert any("clamp" in i.lower() for i in r["issues"])


def test_validate_flags_corrupted_collision():
    r = N.validate_meta(_good_meta(phys=1684), _DONOR)   # PyNifly-regenerated size
    assert not r["ok"]
    assert any("collision" in i.lower() for i in r["issues"])


def test_validate_flags_zero_thickness():
    r = N.validate_meta(_good_meta(z=0.0), _DONOR)
    assert not r["ok"]
    assert any("thickness" in i.lower() or "flat" in i.lower() for i in r["issues"])


def test_validate_flags_missing_normals():
    r = N.validate_meta(_good_meta(nt=False), _DONOR)
    assert not r["ok"]
    assert any("NORMAL" in i or "TANGENT" in i for i in r["issues"])


# ---- DDS color-space gate (B3) ----
def _dds(dxgi: int) -> bytes:
    b = bytearray(148)
    b[0:4] = b"DDS "
    b[0x54:0x58] = b"DX10"                 # ddspf.dwFourCC
    struct.pack_into("<I", b, 128, dxgi)   # DXT10 header dxgiFormat
    return bytes(b)


def test_dds_format_reads_dxgi(tmp_path):
    f = tmp_path / "x.dds"
    f.write_bytes(_dds(99))
    assert N.dds_format(f) == ("DX10", 99)
    f.write_bytes(b"notadds" + bytes(200))
    assert N.dds_format(f) == (None, None)


def test_validate_warns_linear_diffuse(tmp_path):
    d = tmp_path / "textures" / "PrewarCoupons"
    d.mkdir(parents=True)
    (d / "coupon_cram.dds").write_bytes(_dds(98))        # BC7 linear — wrong for a color map
    r = N.validate_meta(_good_meta(), _DONOR, textures_root=tmp_path)
    assert r["ok"], r["issues"]                          # warning, NOT blocking
    assert any("linear" in w.lower() or "srgb" in w.lower() for w in r["warnings"])
    assert r["info"]["diffuseDxgi"] == 98


def test_validate_no_warn_srgb_diffuse(tmp_path):
    d = tmp_path / "textures" / "PrewarCoupons"
    d.mkdir(parents=True)
    (d / "coupon_cram.dds").write_bytes(_dds(99))        # BC7 sRGB — correct
    r = N.validate_meta(_good_meta(), _DONOR, textures_root=tmp_path)
    assert not r["warnings"]
    assert r["info"]["diffuseDxgi"] == 99


def test_set_dds_diffuse_srgb_flips_and_is_idempotent(tmp_path):
    f = tmp_path / "diffuse.dds"
    f.write_bytes(_dds(98))                               # linear
    assert N.set_dds_diffuse_srgb(f) is True              # 98 -> 99
    assert N.dds_format(f) == ("DX10", 99)
    assert N.set_dds_diffuse_srgb(f) is False             # already sRGB -> no-op
    # lossless: only the 4-byte tag changed
    a = bytearray(_dds(98)); struct.pack_into("<I", a, 128, 99)
    assert f.read_bytes() == bytes(a)
