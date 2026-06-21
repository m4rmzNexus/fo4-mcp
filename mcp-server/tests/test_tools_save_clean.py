"""fo4_clean_save_changeforms tests — pure-Python FO4 .fos WRITE path.

Mirrors test_tools_save_inspect.py: a synthetic minimal-but-valid .fos builder,
a no-op roundtrip oracle (zero removals => byte-identical), a changeforms
removal case, gating tests, and a REAL-save no-op roundtrip (skips if none).

The synthetic builder constructs a complete uncompressed body — header,
formVersion, gameVersion, plugin info, a correct 100-byte FLT, two GlobalData
blocks in table1, a few ChangeForms across two plugin indices, table3, formID
array, worldspace array, UNKNOWN3 — so the walker must reach EOF exactly and
the writer must reproduce it byte-for-byte.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import ErrorCode, Fo4McpError, PathForbiddenError
from fo4_mcp.save_inspect import FO4_MAGIC, fo4_inspect_save
from fo4_mcp.save_clean import (
    _SaveBody,
    _resolve_papyrus_shim,
    fo4_clean_save_changeforms,
    fo4_clean_save_papyrus,
    reserialize_save,
)


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _ws(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def _global_data(type_code: int, payload: bytes) -> bytes:
    """A GlobalData block: u32 type + u32 size + payload."""
    return struct.pack("<II", type_code, len(payload)) + payload


def _changeform(refid_data: int, *, type_code: int = 0, flags: int = 0,
                version: int = 1, body: bytes = b"\x00") -> bytes:
    """A ChangeForm with INT8 length width (type byte top bits = 0).

    RefID is the 3-byte big-endian DATA. length1 = len(body), length2 = 0
    (uncompressed). type_code occupies the low 6 bits.
    """
    refid = struct.pack(">I", refid_data)[1:]  # 3 bytes, big-endian
    type_field = type_code & 0x3F  # top 2 bits = 0 => INT8 length width
    return (
        refid
        + struct.pack("<I", flags)
        + struct.pack("<B", type_field)
        + struct.pack("<B", version)
        + struct.pack("<B", len(body))   # length1 (u8)
        + struct.pack("<B", 0)           # length2 (u8)
        + body
    )


# RefID DATA encodings (type bits at >>22 & 3):
#   DEFAULT (1) => full plugin index 0
#   FORMIDX (0) => formIDs[(val-1)] -> high byte = plugin index
def _refid_default(val: int) -> int:
    return (1 << 22) | (val & 0x3FFFFF)


def _refid_formidx(form_index_1based: int) -> int:
    return (0 << 22) | (form_index_1based & 0x3FFFFF)


def _build_fos(
    *,
    form_version: int = 74,
    game_version: str = "1.10.163.0",
    plugins: list[str] | None = None,
    light_plugins: list[str] | None = None,
    change_forms: list[bytes] | None = None,
    form_ids: list[int] | None = None,
    worldspace: list[int] | None = None,
    unknown3: bytes = b"\xAB\xCD",
) -> bytes:
    """Construct a faithful minimal uncompressed FO4 .fos with a full body."""
    if plugins is None:
        plugins = ["Fallout4.esm", "ModA.esp", "ModB.esp"]
    if light_plugins is None:
        light_plugins = []
    if change_forms is None:
        change_forms = []
    if form_ids is None:
        form_ids = []
    if worldspace is None:
        worldspace = [0x01]

    # --- header block (counted by headerSize) ---
    hb = b""
    hb += struct.pack("<I", 11)            # version
    hb += struct.pack("<I", 7)             # save_number
    hb += _ws("TestSole")                  # player_name
    hb += struct.pack("<I", 12)            # player_level
    hb += _ws("Sanctuary")                 # player_location
    hb += _ws("Day 3")                     # game_date
    hb += _ws("HumanRace")                 # race
    hb += struct.pack("<H", 0)             # sex
    hb += struct.pack("<f", 100.0)         # cur_exp
    hb += struct.pack("<f", 250.0)         # lvlup_exp
    hb += struct.pack("<Q", 132000000000000000)  # filetime
    hb += struct.pack("<I", 1)             # shot_w
    hb += struct.pack("<I", 1)             # shot_h

    header = FO4_MAGIC + struct.pack("<I", len(hb)) + hb
    header += b"\x00" * (1 * 1 * 4)        # screenshot RGBA

    body_start = len(header)

    # --- body pieces (sizes feed the FLT) ---
    fv = struct.pack("<B", form_version)
    gv = _ws(game_version)

    plugin_block = struct.pack("<B", len(plugins))
    for n in plugins:
        plugin_block += _ws(n)
    if form_version >= 68:
        plugin_block += struct.pack("<H", len(light_plugins))
        for n in light_plugins:
            plugin_block += _ws(n)
    plugin_info = struct.pack("<I", len(plugin_block)) + plugin_block

    table1 = _global_data(3, b"\x01\x02\x03\x04") + _global_data(5, b"globaldata")
    table1_count = 2
    table2 = b""
    table2_count = 0
    table3 = _global_data(1002, b"anim-block-bytes")  # NOT 1001; opaque
    table3_count = 1

    cf_bytes = b"".join(change_forms)

    fid_array = struct.pack("<I", len(form_ids)) + b"".join(
        struct.pack("<I", f) for f in form_ids
    )
    ws_array = struct.pack("<I", len(worldspace)) + b"".join(
        struct.pack("<I", w) for w in worldspace
    )

    # --- FLT (absolute offsets) ---
    t1_off = body_start + len(fv) + len(gv) + len(plugin_info) + 100
    t2_off = t1_off + len(table1)
    cf_off = t2_off + len(table2)
    t3_off = cf_off + len(cf_bytes)
    fid_count_off = t3_off + len(table3)
    unk3_off = fid_count_off + len(fid_array) + len(ws_array)

    flt = struct.pack(
        "<10I",
        fid_count_off, unk3_off, t1_off, t2_off, cf_off, t3_off,
        table1_count, table2_count, table3_count, len(change_forms),
    ) + b"\x00" * 60  # 15 unused u32

    return (
        header + fv + gv + plugin_info + flt
        + table1 + table2 + cf_bytes + table3
        + fid_array + ws_array + unknown3
    )


# ---- Test 1: synthetic no-op roundtrip = byte-identical ----------------------

def test_walker_reaches_eof_and_noop_roundtrip_byte_identical():
    # ModA.esp = full index 1; ModB.esp = full index 2.
    # form_ids: index0 -> 0x02000ABC (ModB, idx 2), index1 -> 0x01000DEF (ModA, idx 1)
    form_ids = [0x02000ABC, 0x01000DEF]
    cfs = [
        _changeform(_refid_default(0x100), body=b"\xDE\xAD"),       # full idx 0 (Fallout4.esm)
        _changeform(_refid_formidx(1), type_code=1, body=b"\xBE"),  # -> ModB (idx 2)
        _changeform(_refid_formidx(2), type_code=8, body=b"\xEF\x01\x02"),  # -> ModA (idx 1)
    ]
    blob = _build_fos(change_forms=cfs, form_ids=form_ids)

    body = _SaveBody(blob)              # walker must reach EOF (raises otherwise)
    assert body.change_form_count == 3
    assert reserialize_save(blob) == blob


def test_inspect_still_reads_synthetic():
    blob = _build_fos()
    h = fo4_inspect_save(_cfg(Path("C:/Modding")), _write_tmp(blob))["data"]
    assert h["plugins"] == ["Fallout4.esm", "ModA.esp", "ModB.esp"]


_TMP_HOLDER: list[Path] = []


def _write_tmp(blob: bytes) -> str:
    import tempfile
    fd = tempfile.NamedTemporaryFile(suffix=".fos", delete=False)
    fd.write(blob)
    fd.close()
    p = Path(fd.name)
    _TMP_HOLDER.append(p)
    return str(p)


# ---- Test 2: changeforms removal ---------------------------------------------

def test_removal_drops_one_plugins_changeforms(tmp_path):
    form_ids = [0x02000ABC, 0x01000DEF]  # idx0->ModB(2), idx1->ModA(1)
    cfs = [
        _changeform(_refid_default(0x100), body=b"\xDE\xAD"),       # Fallout4.esm (idx 0)
        _changeform(_refid_formidx(1), type_code=1, body=b"\xBE"),  # ModB (idx 2)
        _changeform(_refid_formidx(2), type_code=8, body=b"\xEF\x01\x02"),  # ModA (idx 1)
        _changeform(_refid_formidx(2), type_code=0, body=b"\x09"),  # ModA (idx 1) again
    ]
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos(change_forms=cfs, form_ids=form_ids))
    out = tmp_path / "staging" / "Save.cleaned.fos"

    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(src), str(out), plugins=["ModA.esp"], confirm=True
    )
    assert res["ok"] is True
    data = res["data"]
    assert data["removed_count"] == 2          # the two ModA changeforms
    assert data["kept_changeform_count"] == 2
    assert data["removed_plugins"] == ["ModA.esp"]
    assert data["bak_path"] is None

    cleaned = out.read_bytes()

    # Re-parses cleanly (walker reaches EOF) with the new changeFormCount.
    re_body = _SaveBody(cleaned)
    assert re_body.change_form_count == 2

    # FLT changeFormCount + offsets recomputed: the cleaned file is smaller by
    # exactly the two removed ChangeForm spans.
    removed_bytes = len(cfs[2]) + len(cfs[3])
    assert len(cleaned) == len(src.read_bytes()) - removed_bytes

    # fo4_inspect_save still reads header/plugins.
    insp = fo4_inspect_save(_cfg(tmp_path), str(out))["data"]
    assert insp["plugins"] == ["Fallout4.esm", "ModA.esp", "ModB.esp"]
    assert insp["player_name"] == "TestSole"


def test_removal_makes_bak_when_output_exists(tmp_path):
    form_ids = [0x01000DEF]
    cfs = [_changeform(_refid_formidx(1), body=b"\x01")]
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos(change_forms=cfs, form_ids=form_ids))
    out = tmp_path / "staging" / "out.fos"
    out.parent.mkdir(parents=True)
    out.write_bytes(b"OLD-CONTENT")

    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(src), str(out), plugins=["ModA.esp"], confirm=True
    )
    assert res["data"]["bak_path"] is not None
    assert Path(res["data"]["bak_path"]).read_bytes() == b"OLD-CONTENT"


# ---- Test 3: gating ----------------------------------------------------------

def test_refuse_without_confirm(tmp_path):
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    out = tmp_path / "staging" / "out.fos"
    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(src), str(out), plugins=["ModA.esp"], confirm=False
    )
    assert res["refused"] is True
    assert "confirm" in res["reason"].lower()
    assert not out.exists()


def test_refuse_empty_plugins(tmp_path):
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    out = tmp_path / "staging" / "out.fos"
    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(src), str(out), plugins=[], confirm=True
    )
    assert res["refused"] is True
    assert "non-empty" in res["reason"] or "auto-pick" in res["reason"]
    assert not out.exists()


def test_forbidden_output_path_raises(tmp_path):
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    forbidden = Path("C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/x.fos")
    with pytest.raises(PathForbiddenError):
        fo4_clean_save_changeforms(
            _cfg(tmp_path), str(src), str(forbidden), plugins=["ModA.esp"], confirm=True
        )


def test_named_plugin_absent_refuses_with_present_list(tmp_path):
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    out = tmp_path / "staging" / "out.fos"
    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(src), str(out), plugins=["NotHere.esp"], confirm=True
    )
    assert res["refused"] is True
    assert "NotHere.esp" in res["reason"]
    assert "Fallout4.esm" in res["present_full_plugins"]
    assert not out.exists()


def test_confirm_gate_checked_before_existence(tmp_path):
    # No-confirm refusal should not require the save to exist (gates first).
    out = tmp_path / "staging" / "out.fos"
    res = fo4_clean_save_changeforms(
        _cfg(tmp_path), str(tmp_path / "missing.fos"), str(out),
        plugins=["ModA.esp"], confirm=False,
    )
    assert res["refused"] is True


# ---- Test 4: REAL-save no-op roundtrip (correctness oracle; skip if none) ----

def _find_real_save() -> Path | None:
    candidates = [
        Path.home() / "Documents" / "My Games" / "Fallout4" / "Saves",
        Path("C:/Modding/staging/save-archive"),
    ]
    for root in candidates:
        if root.is_dir():
            for fos in sorted(root.rglob("*.fos")):
                return fos
    return None


def test_real_save_noop_roundtrip_byte_identical():
    sample = _find_real_save()
    if sample is None:
        pytest.skip("no real .fos save found under Documents/My Games/Fallout4/Saves")
    data = sample.read_bytes()  # READ-ONLY
    body = _SaveBody(data)      # walker must reach EOF exactly on real data
    out = body.serialize()
    assert len(out) == len(data), "output length must equal input length"
    assert out == data, "no-op re-serialize of a real save must be byte-identical"


# ---- #16-B: Papyrus-VM cleaner (ReSaver shim) — gating + integration ----------

def test_papyrus_refuse_bad_mode(tmp_path):
    res = fo4_clean_save_papyrus(
        _cfg(tmp_path), str(tmp_path / "x.fos"), str(tmp_path / "staging" / "o.fos"),
        mode="garbage", confirm=True,
    )
    assert res["refused"] is True and "mode" in res["reason"]


def test_papyrus_unattached_requires_risk_ack(tmp_path):
    res = fo4_clean_save_papyrus(
        _cfg(tmp_path), str(tmp_path / "x.fos"), str(tmp_path / "staging" / "o.fos"),
        mode="unattached", confirm=True, accept_unattached_risk=False,
    )
    assert res["refused"] is True and "engine-NORMAL" in res["reason"]


def test_papyrus_refuse_without_confirm(tmp_path):
    res = fo4_clean_save_papyrus(
        _cfg(tmp_path), str(tmp_path / "x.fos"), str(tmp_path / "staging" / "o.fos"),
        mode="undefined", confirm=False,
    )
    assert res["refused"] is True and "confirm" in res["reason"].lower()


def test_papyrus_forbidden_output_raises(tmp_path):
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    forbidden = Path("C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/x.fos")
    with pytest.raises(PathForbiddenError):
        fo4_clean_save_papyrus(
            _cfg(tmp_path), str(src), str(forbidden), mode="undefined", confirm=True
        )


def test_papyrus_toolchain_absent_refuses(tmp_path):
    # Gates pass (mode/confirm/check_write/src), then the shim resolve fails
    # because tmp tools/ has no JDK + CleanShim.jar -> clean refusal, no raise.
    src = tmp_path / "Save.fos"
    src.write_bytes(_build_fos())
    out = tmp_path / "staging" / "o.fos"
    res = fo4_clean_save_papyrus(
        _cfg(tmp_path), str(src), str(out), mode="undefined", confirm=True
    )
    assert res["refused"] is True and "toolchain not built" in res["reason"]
    assert not out.exists()


def test_papyrus_undefined_on_real_save():
    """Integration: run the real ReSaver shim on a real save (skips if either
    the shim toolchain or a real save is unavailable)."""
    cfg = load_config()
    if _resolve_papyrus_shim(cfg) is None:
        pytest.skip("ReSaver shim toolchain not built (JDK + CleanShim.jar)")
    sample = _find_real_save()
    if sample is None:
        pytest.skip("no real .fos save found")
    out_dir = cfg.repo_root / "staging" / "save-clean-test"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = fo4_clean_save_papyrus(
        cfg, str(sample), str(out_dir / "pytest_undef.fos"),
        mode="undefined", confirm=True,
    )["data"]
    assert res["backend"] == "resaver-shim"
    assert res["reread_ok"] is True
    assert isinstance(res["removed_count"], int)
    assert res["before"]["broken"] is False and res["after"]["broken"] is False
