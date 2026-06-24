"""Canonical pure-Python BGSM material codec — the arbitrary-material authoring half of the
Blender->FO4 asset pipeline (asset-pipeline-completion-roadmap Faz B1).

Clean-room reimplementation of the BGSM v1-20 binary layout. The exact field order and every
version-gate were transcribed from ousnius/Material-Editor (MIT) MaterialLib — BaseMaterialFile.cs
+ BGSM.cs (reference source kept under tools/material-editor/ref-src/). A single ordered _SCHEMA
drives BOTH decode and encode, so decode->encode is byte-identical (proven against vanilla
Note.BGSM + the deployed coupon .bgsm).

Two fidelity improvements over MaterialLib itself:
  * Colors are preserved as raw 3-float triples, NOT round-tripped through an 8-bit uint32 (which
    MaterialLib does, quantizing). Round-trip is therefore lossless for ANY input.
  * Strings are stored with their exact bytes (incl. the trailing NUL), so the u32 length prefix is
    reproduced verbatim regardless of the source's NUL convention.

MCP wrappers (fo4_create_bgsm / fo4_inspect_bgsm) live at the bottom.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

from .config import Config
from .errors import Fo4McpError, ErrorCode, ok
from .safety import check_write

SIGNATURE = 0x4D534742  # "BGSM" little-endian (ReadUInt32)

# ---- field kinds ----
U8, U32, F, B, S, C, BLEND = "u8", "u32", "f32", "bool", "str", "color", "blend"


def _lt(n):
    return lambda d: d["Version"] < n


def _gt(n):
    return lambda d: d["Version"] > n


def _ge(n):
    return lambda d: d["Version"] >= n


def _terrain(d):
    return d["Version"] >= 3 and bool(d.get("Terrain"))


# Ordered serialization schema = the format spec. (name, kind, condition|None). A field is present
# in a file iff its condition(decoded-so-far) is truthy. Mutually-exclusive branches reuse a key
# (e.g. GlowTexture in both the v>2 and v<=2 texture blocks) — only one condition ever fires.
_SCHEMA: list[tuple[str, str, Any]] = [
    # ---- BaseMaterialFile ----
    ("_signature", U32, None),
    ("Version", U32, None),
    ("TileFlags", U32, None),                       # bit1=TileV, bit2=TileU
    ("UOffset", F, None), ("VOffset", F, None), ("UScale", F, None), ("VScale", F, None),
    ("Alpha", F, None),
    ("AlphaBlendMode", BLEND, None),                # raw (u8, u32, u32) triple
    ("AlphaTestRef", U8, None),
    ("AlphaTest", B, None),
    ("ZBufferWrite", B, None), ("ZBufferTest", B, None),
    ("ScreenSpaceReflections", B, None), ("WetnessControlScreenSpaceReflections", B, None),
    ("Decal", B, None), ("TwoSided", B, None), ("DecalNoFade", B, None), ("NonOccluder", B, None),
    ("Refraction", B, None), ("RefractionFalloff", B, None), ("RefractionPower", F, None),
    ("EnvironmentMapping", B, _lt(10)), ("EnvironmentMappingMaskScale", F, _lt(10)),
    ("DepthBias", B, _ge(10)),
    ("GrayscaleToPaletteColor", B, None),
    ("MaskWrites", U8, _ge(6)),
    # ---- BGSM textures ----
    ("DiffuseTexture", S, None), ("NormalTexture", S, None),
    ("SmoothSpecTexture", S, None), ("GreyscaleTexture", S, None),
    ("GlowTexture", S, _gt(2)), ("WrinklesTexture", S, _gt(2)), ("SpecularTexture", S, _gt(2)),
    ("LightingTexture", S, _gt(2)), ("FlowTexture", S, _gt(2)),
    ("DistanceFieldAlphaTexture", S, _ge(17)),
    ("EnvmapTexture", S, lambda d: d["Version"] <= 2),
    ("GlowTexture", S, lambda d: d["Version"] <= 2),
    ("InnerLayerTexture", S, lambda d: d["Version"] <= 2),
    ("WrinklesTexture", S, lambda d: d["Version"] <= 2),
    ("DisplacementTexture", S, lambda d: d["Version"] <= 2),
    # ---- BGSM body ----
    ("EnableEditorAlphaRef", B, None),
    ("Translucency", B, _ge(8)), ("TranslucencyThickObject", B, _ge(8)),
    ("TranslucencyMixAlbedoWithSubsurfaceColor", B, _ge(8)),
    ("TranslucencySubsurfaceColor", C, _ge(8)),
    ("TranslucencyTransmissiveScale", F, _ge(8)), ("TranslucencyTurbulence", F, _ge(8)),
    ("RimLighting", B, _lt(8)), ("RimPower", F, _lt(8)), ("BackLightPower", F, _lt(8)),
    ("SubsurfaceLighting", B, _lt(8)), ("SubsurfaceLightingRolloff", F, _lt(8)),
    ("SpecularEnabled", B, None), ("SpecularColor", C, None),
    ("SpecularMult", F, None), ("Smoothness", F, None),
    ("FresnelPower", F, None),
    ("WetnessControlSpecScale", F, None), ("WetnessControlSpecPowerScale", F, None),
    ("WetnessControlSpecMinvar", F, None),
    ("WetnessControlEnvMapScale", F, _lt(10)),
    ("WetnessControlFresnelPower", F, None), ("WetnessControlMetalness", F, None),
    ("PBR", B, _gt(2)),
    ("CustomPorosity", B, _ge(9)), ("PorosityValue", F, _ge(9)),
    ("RootMaterialPath", S, None),
    ("AnisoLighting", B, None), ("EmitEnabled", B, None),
    ("EmittanceColor", C, lambda d: bool(d.get("EmitEnabled"))),
    ("EmittanceMult", F, None), ("ModelSpaceNormals", B, None), ("ExternalEmittance", B, None),
    ("LumEmittance", F, _ge(12)),
    ("UseAdaptativeEmissive", B, _ge(13)),
    ("AdaptativeEmissive_ExposureOffset", F, _ge(13)),
    ("AdaptativeEmissive_FinalExposureMin", F, _ge(13)),
    ("AdaptativeEmissive_FinalExposureMax", F, _ge(13)),
    ("BackLighting", B, _lt(8)),
    ("ReceiveShadows", B, None), ("HideSecret", B, None), ("CastShadows", B, None),
    ("DissolveFade", B, None), ("AssumeShadowmask", B, None),
    ("Glowmap", B, None),
    ("EnvironmentMappingWindow", B, _lt(7)), ("EnvironmentMappingEye", B, _lt(7)),
    ("Hair", B, None), ("HairTintColor", C, None),
    ("Tree", B, None), ("Facegen", B, None), ("SkinTint", B, None), ("Tessellate", B, None),
    ("DisplacementTextureBias", F, _lt(3)), ("DisplacementTextureScale", F, _lt(3)),
    ("TessellationPnScale", F, _lt(3)), ("TessellationBaseFactor", F, _lt(3)),
    ("TessellationFadeDistance", F, _lt(3)),
    ("GrayscaleToPaletteScale", F, None),
    ("SkewSpecularAlpha", B, _ge(1)),
    ("Terrain", B, _ge(3)),
    ("UnkInt1", U32, lambda d: d["Version"] == 3 and bool(d.get("Terrain"))),
    ("TerrainThresholdFalloff", F, _terrain),
    ("TerrainTilingDistance", F, _terrain), ("TerrainRotationAngle", F, _terrain),
]

_NAMES = {n for n, _, _ in _SCHEMA if not n.startswith("_")}
_KIND = {n: k for n, k, _ in _SCHEMA}
_STR_FIELDS = {n for n, k, _ in _SCHEMA if k == S}
_COLOR_FIELDS = {n for n, k, _ in _SCHEMA if k == C}
_BOOL_FIELDS = {n for n, k, _ in _SCHEMA if k == B}


# ---------------------------------------------------------------- codec
def _read(kind: str, b: bytes, p: int):
    if kind == U32:
        return struct.unpack_from("<I", b, p)[0], p + 4
    if kind == U8 or kind == B:
        return b[p], p + 1
    if kind == F:
        return struct.unpack_from("<f", b, p)[0], p + 4
    if kind == C:
        return list(struct.unpack_from("<3f", b, p)), p + 12
    if kind == BLEND:
        a = b[p]
        b1, b2 = struct.unpack_from("<II", b, p + 1)
        return [a, b1, b2], p + 9
    if kind == S:
        n = struct.unpack_from("<I", b, p)[0]
        return b[p + 4:p + 4 + n].decode("latin1"), p + 4 + n   # raw incl. trailing NUL
    raise ValueError(kind)


def _write(kind: str, v: Any) -> bytes:
    if kind == U32:
        return struct.pack("<I", int(v) & 0xFFFFFFFF)
    if kind == U8 or kind == B:
        return bytes([int(v) & 0xFF])
    if kind == F:
        return struct.pack("<f", float(v))
    if kind == C:
        return struct.pack("<3f", *(float(x) for x in v))
    if kind == BLEND:
        return bytes([int(v[0]) & 0xFF]) + struct.pack("<II", int(v[1]) & 0xFFFFFFFF, int(v[2]) & 0xFFFFFFFF)
    if kind == S:
        data = str(v).encode("latin1")
        return struct.pack("<I", len(data)) + data
    raise ValueError(kind)


def decode(data: bytes) -> dict[str, Any]:
    """Parse a BGSM blob into an ordered field dict. Raises on a bad signature. Any bytes left
    after the schema (none for well-formed files) are kept under '_trailing' for exact re-encode."""
    d: dict[str, Any] = {}
    p = 0
    for name, kind, cond in _SCHEMA:
        if cond is not None and not cond(d):
            continue
        v, p = _read(kind, data, p)
        d[name] = v
        if name == "_signature" and v != SIGNATURE:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                              f"not a BGSM (signature 0x{v:08X} != 0x{SIGNATURE:08X})", {})
    d["_trailing"] = data[p:]
    return d


def encode(d: dict[str, Any]) -> bytes:
    """Serialize a field dict back to bytes following the same schema/conditions."""
    out = bytearray()
    for name, kind, cond in _SCHEMA:
        if cond is not None and not cond(d):
            continue
        out += _write(kind, d[name])
    out += d.get("_trailing", b"")
    return bytes(out)


# ---------------------------------------------------------------- defaults (MaterialLib SetDefaults)
def defaults(version: int = 2) -> dict[str, Any]:
    """A fresh BGSM with Material-Editor's default field values (every key present, all versions)."""
    g = 128 / 255.0
    d: dict[str, Any] = {
        "_signature": SIGNATURE, "Version": version, "TileFlags": 3,
        "UOffset": 0.0, "VOffset": 0.0, "UScale": 1.0, "VScale": 1.0,
        "Alpha": 1.0, "AlphaBlendMode": [0, 6, 7], "AlphaTestRef": 128, "AlphaTest": 0,
        "ZBufferWrite": 1, "ZBufferTest": 1,
        "ScreenSpaceReflections": 0, "WetnessControlScreenSpaceReflections": 0,
        "Decal": 0, "TwoSided": 0, "DecalNoFade": 0, "NonOccluder": 0,
        "Refraction": 0, "RefractionFalloff": 0, "RefractionPower": 0.0,
        "EnvironmentMapping": 0, "EnvironmentMappingMaskScale": 1.0, "DepthBias": 0,
        "GrayscaleToPaletteColor": 0, "MaskWrites": 63,
        "DiffuseTexture": "\0", "NormalTexture": "\0", "SmoothSpecTexture": "\0", "GreyscaleTexture": "\0",
        "GlowTexture": "\0", "WrinklesTexture": "\0", "SpecularTexture": "\0", "LightingTexture": "\0",
        "FlowTexture": "\0", "DistanceFieldAlphaTexture": "\0",
        "EnvmapTexture": "\0", "InnerLayerTexture": "\0", "DisplacementTexture": "\0",
        "EnableEditorAlphaRef": 0,
        "Translucency": 0, "TranslucencyThickObject": 0, "TranslucencyMixAlbedoWithSubsurfaceColor": 0,
        "TranslucencySubsurfaceColor": [1.0, 1.0, 1.0],
        "TranslucencyTransmissiveScale": 0.0, "TranslucencyTurbulence": 0.0,
        "RimLighting": 0, "RimPower": 2.0, "BackLightPower": 0.0,
        "SubsurfaceLighting": 0, "SubsurfaceLightingRolloff": 0.3,
        "SpecularEnabled": 0, "SpecularColor": [1.0, 1.0, 1.0], "SpecularMult": 1.0, "Smoothness": 1.0,
        "FresnelPower": 5.0, "WetnessControlSpecScale": -1.0, "WetnessControlSpecPowerScale": -1.0,
        "WetnessControlSpecMinvar": -1.0, "WetnessControlEnvMapScale": -1.0,
        "WetnessControlFresnelPower": -1.0, "WetnessControlMetalness": -1.0,
        "PBR": 0, "CustomPorosity": 0, "PorosityValue": 0.0,
        "RootMaterialPath": "\0",
        "AnisoLighting": 0, "EmitEnabled": 0, "EmittanceColor": [1.0, 1.0, 1.0], "EmittanceMult": 1.0,
        "ModelSpaceNormals": 0, "ExternalEmittance": 0, "LumEmittance": 0.0,
        "UseAdaptativeEmissive": 0, "AdaptativeEmissive_ExposureOffset": 0.0,
        "AdaptativeEmissive_FinalExposureMin": 0.0, "AdaptativeEmissive_FinalExposureMax": 0.0,
        "BackLighting": 0,
        "ReceiveShadows": 0, "HideSecret": 0, "CastShadows": 0, "DissolveFade": 0, "AssumeShadowmask": 0,
        "Glowmap": 0, "EnvironmentMappingWindow": 0, "EnvironmentMappingEye": 0,
        "Hair": 0, "HairTintColor": [g, g, g],
        "Tree": 0, "Facegen": 0, "SkinTint": 0, "Tessellate": 0,
        "DisplacementTextureBias": -0.5, "DisplacementTextureScale": 10.0,
        "TessellationPnScale": 1.0, "TessellationBaseFactor": 1.0, "TessellationFadeDistance": 0.0,
        "GrayscaleToPaletteScale": 1.0, "SkewSpecularAlpha": 0,
        "Terrain": 0, "UnkInt1": 0,
        "TerrainThresholdFalloff": 0.0, "TerrainTilingDistance": 0.0, "TerrainRotationAngle": 0.0,
        "_trailing": b"",
    }
    return d


_BLEND_NAMES = {  # AlphaBlendModeType -> raw (a, b, c)
    "unknown": [0, 6, 7], "none": [0, 0, 0], "standard": [1, 6, 7],
    "additive": [1, 6, 0], "multiplicative": [1, 4, 1],
}


def _coerce(name: str, value: Any) -> Any:
    """Map a friendly field value to the codec's internal representation."""
    if name in _STR_FIELDS:
        s = str(value)
        return s if s.endswith("\0") else s + "\0"          # texture path -> path + NUL
    if name in _BOOL_FIELDS:
        return 1 if value in (True, 1, "1", "true", "True") else 0
    if name in _COLOR_FIELDS:
        if isinstance(value, int):                            # 0xRRGGBB
            return [((value >> 16) & 0xFF) / 255.0, ((value >> 8) & 0xFF) / 255.0, (value & 0xFF) / 255.0]
        return [float(x) for x in value]                      # [r, g, b]
    if name == "AlphaBlendMode" and isinstance(value, str):
        m = _BLEND_NAMES.get(value.lower())
        if m is None:
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"unknown AlphaBlendMode '{value}'", {})
        return list(m)
    return value


def apply_fields(d: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Validate + apply user field overrides (rejecting unknown names) onto a field dict."""
    bad = [k for k in fields if k not in _NAMES]
    if bad:
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT,
                          f"unknown BGSM field(s): {', '.join(sorted(bad))}", {"known": sorted(_NAMES)})
    for k, v in fields.items():
        d[k] = _coerce(k, v)
    return d


def summarize(d: dict[str, Any]) -> dict[str, Any]:
    """A JSON-safe, human-readable view: textures NUL-stripped, _trailing reported by length."""
    out: dict[str, Any] = {}
    for name, _, _ in _SCHEMA:
        if name not in d or name.startswith("_"):
            continue
        v = d[name]
        out[name] = v.rstrip("\0") if name in _STR_FIELDS else v
    out["_signature"] = f"0x{d['_signature']:08X}"
    out["_trailingBytes"] = len(d.get("_trailing", b""))
    return out


def load(path: str | Path) -> dict[str, Any]:
    return decode(Path(path).read_bytes())


# ---------------------------------------------------------------- MCP wrappers
def _resolve(cfg: Config, p: str) -> Path:
    q = Path(p)
    return q if q.is_absolute() else (cfg.repo_root / q).resolve()


def fo4_inspect_bgsm(cfg: Config, bgsm: str) -> dict[str, Any]:
    """Read-only: decode a .bgsm and return its full field set (textures, flags, colors, version).
    Also reports whether the codec round-trips it byte-identical (a fidelity self-check)."""
    p = _resolve(cfg, bgsm)
    if not p.is_file():
        raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"bgsm not found: {p}", {})
    raw = p.read_bytes()
    d = decode(raw)
    return ok({"path": str(p), "bytes": len(raw),
               "roundTripExact": encode(d) == raw, "fields": summarize(d)})


def fo4_create_bgsm(cfg: Config, output: str, fields: dict[str, Any] | None = None,
                    template: str | None = None, version: int = 2) -> dict[str, Any]:
    """Author a BGSM material file. Two modes:
      * template given  -> decode it and apply `fields` (edit; every unspecified byte preserved
        exactly — the safe path, e.g. take Note.BGSM, swap DiffuseTexture + clear AlphaTest).
      * no template     -> build from Material-Editor defaults at `version`, apply `fields`.
    `fields` keys are BGSM property names (DiffuseTexture, NormalTexture, AlphaTest, TwoSided,
    SpecularColor=[r,g,b] or 0xRRGGBB, AlphaBlendMode="None"/"Standard"/..., EmitEnabled, ...).
    Output is gated to staging/fixtures (Steam Data is refused); .bak on in-place overwrite. Always
    verifies the written bytes re-decode (and, for edits, that the diff is exactly the requested
    fields)."""
    out = _resolve(cfg, output)
    check_write(out, cfg.repo_root)                          # raises on DENY (Steam Data etc.)

    if template:
        tpl = _resolve(cfg, template)
        if not tpl.is_file():
            raise Fo4McpError(ErrorCode.INVALID_ARGUMENT, f"template bgsm not found: {tpl}", {})
        d = decode(tpl.read_bytes())
    else:
        d = defaults(version)

    changed = sorted(fields) if fields else []
    if fields:
        apply_fields(d, fields)

    blob = encode(d)
    if decode(blob)["DiffuseTexture"] != d["DiffuseTexture"]:   # cheap sanity; full re-decode below
        raise Fo4McpError(ErrorCode.INTERNAL, "BGSM re-decode mismatch", {})

    out.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if out.exists():
        backup = out.with_suffix(out.suffix + ".bak")
        backup.write_bytes(out.read_bytes())
    out.write_bytes(blob)

    return ok({"output": str(out), "bytes": len(blob), "backup": str(backup) if backup else None,
               "mode": "edit" if template else "create", "version": d["Version"],
               "changed": changed, "fields": summarize(decode(blob))})
