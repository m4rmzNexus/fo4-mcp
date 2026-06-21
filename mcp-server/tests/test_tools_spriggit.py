"""fo4_spriggit_export / fo4_spriggit_import tests.

Two layers:
  * boundary/gate tests — pure, no Spriggit binary needed (use a stub manifest)
  * integration tests — run the real Spriggit.CLI.exe against the committed
    fixture under fixtures/armor-swap-test/seed/; skipped if the binary, the
    fixture, or a net9 dotnet is unavailable (fresh checkout / no tools).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config, load_config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.manifest import ToolEntry, parse_manifest
from fo4_mcp.tools import fo4_spriggit_export, fo4_spriggit_import

_REPO = Path(__file__).resolve().parents[2]
_SPRIGGIT = _REPO / "tools" / "spriggit" / "Spriggit.CLI.exe"
_FIXTURE_YAML = _REPO / "fixtures" / "armor-swap-test" / "seed" / "yaml"
_FIXTURE_ESP = _REPO / "fixtures" / "armor-swap-test" / "seed" / "test_armor.esp"


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root,
        fo4_install_dir=None,
        fo4_user_docs=None,
        fo4_localappdata=None,
        mo2_instance_dir=None,
        tools_dir=repo_root / "tools",
        log_level="INFO",
        subprocess_timeout=300,
    )


class _ManifestStub:
    """Manifest that resolves 'spriggit' to a (possibly fake) path."""

    def __init__(self, binary_path: str, resolved: bool = True):
        self._entry = ToolEntry(
            name="Spriggit", version="0.40.1", source="", asset="",
            binary_path=binary_path, license="GPL-3.0",
        )
        self._resolved = resolved

    def get(self, name):
        if name.lower() == "spriggit":
            e = self._entry
            # force is_resolved via binary_path validity flag
            return e if self._resolved else ToolEntry(
                name="Spriggit", version="", source="", asset="",
                binary_path="TBD", license="",
            )
        return None


# ---------------- boundary / gate tests (no Spriggit needed) ----------------

def test_export_rejects_forbidden_output(tmp_path):
    cfg = _cfg(tmp_path)
    plugin = tmp_path / "in.esp"
    plugin.write_bytes(b"TES4stub")
    mani = _ManifestStub(str(_SPRIGGIT if _SPRIGGIT.exists() else tmp_path / "fake.exe"))
    forbidden = Path("C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/out")
    with pytest.raises(PathForbiddenError):
        fo4_spriggit_export(cfg, mani, str(plugin), str(forbidden))


def test_export_missing_plugin_raises(tmp_path):
    cfg = _cfg(tmp_path)
    (tmp_path / "staging").mkdir()
    mani = _ManifestStub(str(tmp_path / "fake.exe"))
    with pytest.raises(Fo4McpError):
        fo4_spriggit_export(cfg, mani, str(tmp_path / "nope.esp"), "staging/out")


def test_import_rejects_non_spriggit_source(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "notyaml"
    src.mkdir()
    (tmp_path / "staging").mkdir()
    mani = _ManifestStub(str(tmp_path / "fake.exe"))
    with pytest.raises(Fo4McpError) as exc:
        fo4_spriggit_import(cfg, mani, str(src), "staging/out.esp")
    assert "spriggit-meta.json" in str(exc.value)


def test_import_rejects_forbidden_output(tmp_path):
    cfg = _cfg(tmp_path)
    src = tmp_path / "yaml"
    src.mkdir()
    (src / "spriggit-meta.json").write_text("{}", encoding="utf-8")
    mani = _ManifestStub(str(tmp_path / "fake.exe"))
    forbidden = Path("C:/Users/x/Documents/My Games/Fallout4/out.esp")
    with pytest.raises(PathForbiddenError):
        fo4_spriggit_import(cfg, mani, str(src), str(forbidden))


# ---------------- integration tests (real Spriggit) ----------------

def _skip_if_no_spriggit():
    if not _SPRIGGIT.exists():
        pytest.skip(f"Spriggit not extracted at {_SPRIGGIT}")
    if not _FIXTURE_YAML.exists():
        pytest.skip(f"fixture YAML missing at {_FIXTURE_YAML}")
    if shutil.which("dotnet") is None and not (Path.home() / ".dotnet" / "dotnet.exe").exists():
        pytest.skip("dotnet not found (Spriggit needs .NET 9)")


@pytest.fixture
def real_env():
    cfg = load_config()
    manifest = parse_manifest(_REPO / "tools" / "MANIFEST.md")
    return cfg, manifest


def test_export_roundtrip_real(tmp_path, real_env):
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    # 1) import the committed YAML fixture to a temp esp (staging gate)
    staging = cfg.repo_root / "staging" / "spriggit-test"
    if staging.exists():
        shutil.rmtree(staging)
    esp = staging / "test_armor.esp"
    imp = fo4_spriggit_import(cfg, manifest, str(_FIXTURE_YAML), str(esp))["data"]
    assert imp["ok"] and imp["wrote"] and esp.exists()

    # 2) export it back to YAML
    out = staging / "yaml-out"
    exp = fo4_spriggit_export(cfg, manifest, str(esp), str(out))
    assert exp["data"]["ok"]
    assert exp["data"]["file_count"] >= 3  # RecordData + meta + 1 record
    assert any("RecordData.yaml" in f for f in exp["data"]["files_created"])
    shutil.rmtree(staging, ignore_errors=True)


def test_import_diff_gate_blocks_overwrite(tmp_path, real_env):
    _skip_if_no_spriggit()
    cfg, manifest = real_env
    staging = cfg.repo_root / "staging" / "spriggit-diffgate"
    if staging.exists():
        shutil.rmtree(staging)
    esp = staging / "test_armor.esp"
    # first import creates it
    first = fo4_spriggit_import(cfg, manifest, str(_FIXTURE_YAML), str(esp))["data"]
    assert first["wrote"] is True
    # second import without confirm must NOT overwrite
    second = fo4_spriggit_import(cfg, manifest, str(_FIXTURE_YAML), str(esp))["data"]
    assert second["diff_required"] is True
    assert second["wrote"] is False
    assert "existing_sha256" in second
    # confirm_overwrite writes + leaves a backup
    third = fo4_spriggit_import(
        cfg, manifest, str(_FIXTURE_YAML), str(esp), confirm_overwrite=True
    )["data"]
    assert third["wrote"] is True
    assert third["backup_path"] is not None
    assert Path(third["backup_path"]).exists()
    shutil.rmtree(staging, ignore_errors=True)
