"""W9 silent-voice baker (fo4_bake_voice_assets) + W10 FaceGen export (fo4_build_facegen).

Validation/argv tests run always. The voice e2e bake drives the real LipGenerator+xWMAEncode
toolchain and is skipped if it (or the writer) is not present.
"""

from __future__ import annotations

import shutil
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError
from fo4_mcp.facegen import fo4_build_facegen
from fo4_mcp.manifest import parse_manifest
from fo4_mcp.seq import fo4_build_seq
from fo4_mcp.tools import _mutagen_cli_binary, fo4_create_record
from fo4_mcp.voice_bake import _fuze_pack, _duration_for, fo4_bake_voice_assets

_REPO = Path(__file__).resolve().parents[2]
_MANIFEST = parse_manifest(_REPO / "tools" / "MANIFEST.md")


def _cfg(repo_root: Path, fo4=None) -> Config:
    return Config(
        repo_root=repo_root, fo4_install_dir=fo4, fo4_user_docs=None,
        fo4_localappdata=None, mo2_instance_dir=None, tools_dir=repo_root / "tools",
        log_level="INFO", subprocess_timeout=120,
    )


# ---------------- pure-unit: FUZE packer + duration ----------------

def test_fuze_pack_header():
    fuz = _fuze_pack(b"LIPDATA", b"XWMAUDIO")
    assert fuz[:4] == b"FUZE"
    assert struct.unpack("<I", fuz[4:8])[0] == 1
    assert struct.unpack("<I", fuz[8:12])[0] == len(b"LIPDATA")
    assert fuz[12:19] == b"LIPDATA"
    assert fuz[19:] == b"XWMAUDIO"


def test_fuze_pack_empty_lip():
    fuz = _fuze_pack(b"", b"XWM")
    assert struct.unpack("<I", fuz[8:12])[0] == 0
    assert fuz[12:] == b"XWM"


def test_duration_clamped():
    assert _duration_for("") == 1.5                       # floor
    assert _duration_for("a " * 200) == 30.0              # ceiling
    assert 1.5 <= _duration_for("a normal length line") <= 30.0


# ---------------- W10 FaceGen argv (no CK launch) ----------------

def test_facegen_rejects_bad_suffix(tmp_path):
    with pytest.raises(Fo4McpError, match="must end"):
        fo4_build_facegen(_cfg(tmp_path, fo4=tmp_path), "MyMod.txt")


def test_facegen_missing_ck(tmp_path):
    # fo4_install_dir set but no CreationKit.exe -> ToolBinaryMissing
    with pytest.raises(Fo4McpError):
        fo4_build_facegen(_cfg(tmp_path, fo4=tmp_path), "MyMod.esp")


def test_facegen_rejects_bad_target(tmp_path):
    with pytest.raises(Fo4McpError, match="target must be"):
        fo4_build_facegen(_cfg(tmp_path, fo4=tmp_path), "MyMod.esp", target="PC")


def test_facegen_dry_run_argv():
    """With the real FO4 install, dry_run builds the exact -ExportFaceGenData argv + target.
    The mandatory <target> arg was verified by a live CK run (CK rejects the bare form)."""
    cfg = load_config()
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "CreationKit.exe").exists():
        pytest.skip("CreationKit.exe not present")
    data = fo4_build_facegen(cfg, "FO4MCP_Test.esp", dry_run=True)["data"]
    assert data["dry_run"] is True
    assert data["command"][1] == "-ExportFaceGenData:FO4MCP_Test.esp"
    assert data["command"][2] == "W32"            # mandatory platform target
    assert data["command"][0].lower().endswith("creationkit.exe")


# ---------------- W12 SEQ generation argv ----------------

def test_seq_rejects_bad_suffix(tmp_path):
    with pytest.raises(Fo4McpError, match="must end"):
        fo4_build_seq(_cfg(tmp_path, fo4=tmp_path), "MyMod.txt")


def test_seq_dry_run_argv():
    cfg = load_config()
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "CreationKit.exe").exists():
        pytest.skip("CreationKit.exe not present")
    data = fo4_build_seq(cfg, "FO4MCP_Test.esp", dry_run=True)["data"]
    assert data["dry_run"] is True
    assert data["command"][1] == "-GenerateSEQ:FO4MCP_Test.esp"


# ---------------- W9 voice baker ----------------

@pytest.fixture
def real_env():
    return load_config(), _MANIFEST


@pytest.fixture
def staging_out():
    d = _REPO / "staging" / "w9-bake-test"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _toolchain_present(cfg) -> bool:
    lg = cfg.repo_root / "tools" / "ckpe" / "Tools" / "LipGen" / "LipGenerator"
    return (lg / "LipGenerator.exe").exists() and (lg / "xWMAEncode.exe").exists() \
        and (lg / "FonixData.cdf").exists()


def _voice_spec():
    return {"records": [
        {"type": "npc", "editorId": "BakeSpeaker", "name": "Speaker",
         "voice": "013AD2:Fallout4.esm"},
        {"type": "quest", "editorId": "BakeQuest", "name": "BQ", "questType": "SideQuests",
         "topics": [
            {"editorId": "BakeGreet", "name": "Greet", "subtype": "Custom0",
             "responses": [
                {"speaker": "000800:VoiceBake.esp",
                 "lines": [{"text": "Hello there, friend.", "responseNumber": 1},
                           {"text": "Stay safe.", "responseNumber": 2}]}
             ]}
         ]},
    ]}


def test_voice_bake_rejects_out_of_repo(real_env, staging_out, tmp_path):
    """out_root outside the repo is refused by the safe-write boundary."""
    cfg, manifest = real_env
    if _mutagen_cli_binary(cfg, manifest) is None:
        pytest.skip("mutagen-cli not built")
    out = staging_out / "VoiceBake.esp"
    fo4_create_record(cfg, manifest, _voice_spec(), str(out))
    with pytest.raises(Fo4McpError):
        fo4_bake_voice_assets(cfg, manifest, str(out),
                              out_root=str(tmp_path / "outside"), dry_run=True)


def test_voice_bake_dry_run_plans_lines(real_env, staging_out):
    cfg, manifest = real_env
    if _mutagen_cli_binary(cfg, manifest) is None:
        pytest.skip("mutagen-cli not built")
    out = staging_out / "VoiceBake.esp"
    fo4_create_record(cfg, manifest, _voice_spec(), str(out))
    data = fo4_bake_voice_assets(cfg, manifest, str(out),
                                 out_root=str(staging_out), dry_run=True)["data"]
    assert data["line_count"] == 2
    assert data["dry_run"] is True
    assert data["baked_count"] == 0
    # each planned line carries its canonical .fuz dest
    assert all("/Sound/Voice/VoiceBake.esp/" in p["dest"].replace("\\", "/")
               for p in data["planned"])


def test_voice_bake_e2e_makes_valid_fuz(real_env, staging_out):
    """Real bake: LipGenerator + xWMAEncode + FUZE pack -> a valid .fuz per line on disk."""
    cfg, manifest = real_env
    if _mutagen_cli_binary(cfg, manifest) is None:
        pytest.skip("mutagen-cli not built")
    if not _toolchain_present(cfg):
        pytest.skip("LipGen/xWMAEncode toolchain not present")
    if cfg.fo4_install_dir is None or not (cfg.fo4_install_dir / "Data" / "Fallout4.esm").is_file():
        pytest.skip("FO4 install needed to resolve the voice-type folder")
    out = staging_out / "VoiceBake.esp"
    fo4_create_record(cfg, manifest, _voice_spec(), str(out))
    data = fo4_bake_voice_assets(cfg, manifest, str(out),
                                 out_root=str(staging_out), dry_run=False)["data"]
    assert data["baked_count"] == 2
    assert data["skipped"] == []
    fuzzes = list(staging_out.rglob("*.fuz"))
    assert len(fuzzes) == 2
    raw = fuzzes[0].read_bytes()
    assert raw[:4] == b"FUZE"
    assert struct.unpack("<I", raw[4:8])[0] == 1
    assert struct.unpack("<I", raw[8:12])[0] > 0           # a real .lip got embedded
