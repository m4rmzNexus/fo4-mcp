"""fo4_read_esl_flag / fo4_set_esl_flag tests — pure TES4 header rewrite, no tool."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.esl_flag import (
    _read_tes4_flags,
    _set_light_flag_bytes,
    fo4_read_esl_flag,
    fo4_set_esl_flag,
)

_REPO = Path(__file__).resolve().parents[2]
_FIXTURE_ESP = _REPO / "fixtures" / "armor-swap-test" / "seed" / "test_armor.esp"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=None, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


def _tes4(flags: int, body: bytes = b"") -> bytes:
    # type 'TES4' | dataSize u32 | flags u32 | formID u32 | versionControl u32 |
    # formVersion u16 | unknown u16 | body
    return (
        _MAGIC
        + struct.pack("<I", len(body))   # dataSize
        + struct.pack("<I", flags)
        + struct.pack("<I", 0)           # formID (always 0 for TES4)
        + struct.pack("<I", 0)           # versionControl
        + struct.pack("<H", 131)         # formVersion (AE)
        + struct.pack("<H", 0)           # unknown
        + body
    )


_MAGIC = b"TES4"


# ---------------- pure helpers ----------------

def test_read_tes4_flags_values():
    assert _read_tes4_flags(_tes4(0x000)) == 0x000
    assert _read_tes4_flags(_tes4(0x081)) == 0x081   # esm + localized
    assert _read_tes4_flags(_tes4(0x281)) == 0x281   # esm + localized + light


def test_read_tes4_flags_rejects_non_tes4():
    with pytest.raises(ValueError):
        _read_tes4_flags(b"NOPE" + b"\x00" * 12)


def test_set_light_flag_enable_disable_roundtrip():
    body = b"HEDR\x0c\x00arbitrary body bytes here"
    base = _tes4(0x081, body)

    patched, old, new = _set_light_flag_bytes(base, True)
    assert old is False and new is True
    assert _read_tes4_flags(patched) == 0x281
    # body untouched, length unchanged
    assert patched[24:] == base[24:]
    assert len(patched) == len(base)

    # clearing it again returns to the original flags + body
    restored, old2, new2 = _set_light_flag_bytes(patched, False)
    assert old2 is True and new2 is False
    assert _read_tes4_flags(restored) == 0x081
    assert restored == base


# ---------------- read tool ----------------

def test_read_esl_flag_on_fixture_header(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "light.esp"
    src.write_bytes(_tes4(0x281, b"HEDR body"))
    data = fo4_read_esl_flag(cfg, str(src))["data"]
    assert data["light_flagged"] is True
    assert data["is_esm"] is True
    assert data["is_localized"] is True
    assert data["flags_hex"] == "0x00000281"


def test_read_esl_flag_plain_esp(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "plain.esp"
    src.write_bytes(_tes4(0x000))
    data = fo4_read_esl_flag(cfg, str(src))["data"]
    assert data["light_flagged"] is False
    assert data["is_esm"] is False


def test_read_esl_flag_missing_file_raises(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(Fo4McpError):
        fo4_read_esl_flag(cfg, str(tmp_path / "nope.esp"))


def test_read_esl_flag_non_tes4_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "notesp.bin"
    src.write_bytes(b"PK\x03\x04nope nope nope")
    with pytest.raises(Fo4McpError):
        fo4_read_esl_flag(cfg, str(src))


# ---------------- writer ----------------

def test_set_esl_flag_writes_flagged_copy(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    data = fo4_set_esl_flag(cfg, str(src), "staging/flagged.esp", enable=True)["data"]
    assert data["old_light"] is False and data["new_light"] is True
    written = (tmp_path / "staging" / "flagged.esp").read_bytes()
    assert _read_tes4_flags(written) & 0x200


def test_set_esl_flag_forbidden_output_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000))
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/x.esp"
    with pytest.raises(PathForbiddenError):
        fo4_set_esl_flag(cfg, str(src), forbidden, enable=True)


def test_set_esl_flag_backs_up_existing(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x000, b"HEDR body"))
    (tmp_path / "staging").mkdir()
    dst = tmp_path / "staging" / "out.esp"
    dst.write_bytes(_tes4(0x281, b"old"))  # pre-existing
    data = fo4_set_esl_flag(cfg, str(src), "staging/out.esp", enable=True)["data"]
    assert data["bak_path"] is not None
    assert Path(data["bak_path"]).exists()


def test_set_esl_flag_non_tes4_input_raises(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "notesp.bin"
    src.write_bytes(b"PK\x03\x04nope")
    with pytest.raises(Fo4McpError):
        fo4_set_esl_flag(cfg, str(src), "staging/x.esp", enable=True)


def test_set_esl_flag_disable(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "in.esp"
    src.write_bytes(_tes4(0x281, b"HEDR body"))
    data = fo4_set_esl_flag(cfg, str(src), "staging/cleared.esp", enable=False)["data"]
    assert data["old_light"] is True and data["new_light"] is False
    written = (tmp_path / "staging" / "cleared.esp").read_bytes()
    assert not (_read_tes4_flags(written) & 0x200)


# ---------------- integration: real fixture ESP ----------------

def test_real_fixture_roundtrip(tmp_path):
    if not _FIXTURE_ESP.exists():
        pytest.skip("test_armor.esp fixture not present")
    cfg = _cfg(tmp_path)
    original = _FIXTURE_ESP.read_bytes()
    src_size = struct.unpack_from("<I", original, 4)[0]  # dataSize before

    data = fo4_set_esl_flag(cfg, str(_FIXTURE_ESP), "staging/test_armor.esp", enable=True)["data"]
    assert data["new_light"] is True

    written = (tmp_path / "staging" / "test_armor.esp").read_bytes()
    # re-read the staged copy and confirm the flag stuck
    reread = fo4_read_esl_flag(cfg, str(tmp_path / "staging" / "test_armor.esp"))["data"]
    assert reread["light_flagged"] is True
    # dataSize and total header-determined length unchanged
    assert struct.unpack_from("<I", written, 4)[0] == src_size
    assert len(written) == len(original)
    assert written[24:] == original[24:]
