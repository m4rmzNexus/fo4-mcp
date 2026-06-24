"""bgsm_ops — clean-room BGSM material codec tests.

All fixtures are SYNTHETIC (built from the codec's own defaults() / encode()), never Bethesda
assets, so the suite stays copyright-clean. The byte-exact proof against the real vanilla Note.BGSM
and the deployed coupon .bgsm was run live in-session; here we lock the invariants the codec must
hold: decode<->encode identity across every version branch, lossless colors (the improvement over
MaterialLib's 8-bit quantization), exact string length prefixes, and the create/edit wrappers.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.bgsm_ops import (
    SIGNATURE, decode, encode, defaults, apply_fields, summarize,
    fo4_create_bgsm, fo4_inspect_bgsm,
)
from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


# ---- codec core ----
@pytest.mark.parametrize("v", [1, 2, 3, 6, 7, 8, 9, 10, 12, 13, 17, 20])
def test_defaults_roundtrip_every_version(v):
    blob = encode(defaults(v))
    again = decode(blob)
    assert again["Version"] == v
    assert encode(again) == blob               # decode->encode is a fixed point
    assert again["_trailing"] == b""           # defaults consume exactly the schema


def test_decode_rejects_bad_signature():
    with pytest.raises(Fo4McpError):
        decode(struct.pack("<I", 0xDEADBEEF) + bytes(300))


def test_signature_is_bgsm():
    assert decode(encode(defaults()))["_signature"] == SIGNATURE


def test_color_is_lossless():
    # the key fidelity win over MaterialLib: an arbitrary (non /255) color survives exactly
    d = defaults(20)
    d["SpecularColor"] = [0.123456, 0.654321, 0.314159]
    back = decode(encode(d))["SpecularColor"]
    assert all(abs(a - b) < 1e-6 for a, b in zip(back, [0.123456, 0.654321, 0.314159]))


def test_string_roundtrip_and_length_prefix():
    d = defaults(2)
    apply_fields(d, {"DiffuseTexture": "Mod/tex_d.dds"})
    assert d["DiffuseTexture"].endswith("\0")              # NUL appended internally
    blob = encode(d)
    # the diffuse is the first string after the fixed header; its u32 prefix = len(path)+1
    idx = blob.index(b"Mod/tex_d.dds")
    (n,) = struct.unpack_from("<I", blob, idx - 4)
    assert n == len("Mod/tex_d.dds") + 1
    assert decode(blob)["DiffuseTexture"] == "Mod/tex_d.dds\0"
    assert summarize(decode(blob))["DiffuseTexture"] == "Mod/tex_d.dds"   # NUL stripped for view


def test_blendmode_and_color_and_bool_coercion():
    d = defaults(20)
    apply_fields(d, {"AlphaBlendMode": "Additive", "EmittanceColor": 0x00FF80,
                     "TwoSided": True, "EmitEnabled": True})
    assert d["AlphaBlendMode"] == [1, 6, 0]                 # name -> raw triple
    assert d["EmittanceColor"][0] == 0.0 and abs(d["EmittanceColor"][1] - 1.0) < 1e-6  # 0xRRGGBB
    assert d["TwoSided"] == 1 and d["EmitEnabled"] == 1     # bool -> byte


def test_apply_fields_rejects_unknown():
    with pytest.raises(Fo4McpError):
        apply_fields(defaults(), {"NotAField": 1})


def test_emittance_color_only_present_when_enabled():
    off = encode(defaults(2))                               # EmitEnabled=0 -> no EmittanceColor
    d = defaults(2)
    apply_fields(d, {"EmitEnabled": True})
    on = encode(d)
    assert len(on) == len(off) + 12                        # +1 color (3 floats)


# ---- MCP wrappers ----
def test_create_from_defaults(tmp_path):
    out = "staging/m/test.bgsm"
    r = fo4_create_bgsm(_cfg(tmp_path), out, fields={"DiffuseTexture": "M/d.dds", "TwoSided": True},
                        version=20)["data"]
    assert r["mode"] == "create" and r["version"] == 20
    assert r["fields"]["DiffuseTexture"] == "M/d.dds"
    assert r["fields"]["TwoSided"] == 1
    assert (tmp_path / out).is_file()


def test_create_edit_mode_preserves_unspecified(tmp_path):
    cfg = _cfg(tmp_path)
    # make a template, then edit ONLY DiffuseTexture; everything else must be byte-preserved
    fo4_create_bgsm(cfg, "staging/tpl.bgsm", fields={"NormalTexture": "M/n.dds", "Smoothness": 0.25},
                    version=20)
    before = (tmp_path / "staging/tpl.bgsm").read_bytes()
    r = fo4_create_bgsm(cfg, "staging/tpl.bgsm", template="staging/tpl.bgsm",
                        fields={"DiffuseTexture": "M/d.dds"})["data"]
    assert r["mode"] == "edit" and r["changed"] == ["DiffuseTexture"]
    assert r["backup"] and (tmp_path / "staging/tpl.bgsm.bak").read_bytes() == before
    f = r["fields"]
    assert f["DiffuseTexture"] == "M/d.dds" and f["NormalTexture"] == "M/n.dds"
    assert abs(f["Smoothness"] - 0.25) < 1e-6


def test_inspect_reports_roundtrip(tmp_path):
    cfg = _cfg(tmp_path)
    fo4_create_bgsm(cfg, "staging/i.bgsm", fields={"DiffuseTexture": "M/d.dds"}, version=2)
    r = fo4_inspect_bgsm(cfg, "staging/i.bgsm")["data"]
    assert r["roundTripExact"] is True
    assert r["fields"]["DiffuseTexture"] == "M/d.dds"
    assert r["fields"]["Version"] == 2


def test_create_forbidden_output_raises(tmp_path):
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.bgsm"
    with pytest.raises(PathForbiddenError):
        fo4_create_bgsm(_cfg(tmp_path), forbidden, fields={"DiffuseTexture": "x.dds"})
