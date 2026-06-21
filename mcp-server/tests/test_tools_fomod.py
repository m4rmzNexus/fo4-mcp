"""fo4_generate_fomod tests — pure XML codegen, no subprocess."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp.config import Config
from fo4_mcp.errors import Fo4McpError, PathForbiddenError
from fo4_mcp.tools import fo4_generate_fomod


def _cfg(repo_root: Path) -> Config:
    return Config(
        repo_root=repo_root,
        fo4_install_dir=None,
        fo4_user_docs=None,
        fo4_localappdata=None,
        mo2_instance_dir=None,
        tools_dir=repo_root / "tools",
        log_level="INFO",
        subprocess_timeout=120,
    )


def _spec():
    return {
        "name": "Test Armor Mod",
        "author": "m4rmz",
        "version": "1.0",
        "description": "fixture",
        "required_files": [{"source": "Data", "destination": "", "type": "folder"}],
        "install_steps": [
            {
                "name": "Main",
                "groups": [
                    {
                        "name": "Texture Variant",
                        "type": "SelectExactlyOne",
                        "plugins": [
                            {
                                "name": "Red",
                                "description": "Red textures",
                                "type": "Recommended",
                                "files": [{"source": "red", "destination": "Textures"}],
                            },
                            {
                                "name": "Blue",
                                "description": "Blue textures",
                                "type": "Optional",
                                "files": [{"source": "blue", "destination": "Textures"}],
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_generates_valid_xml(tmp_path):
    cfg = _cfg(tmp_path)
    res = fo4_generate_fomod(cfg, _spec(), "staging/fomod-test")["data"]
    assert res["ok"] and res["module_name"] == "Test Armor Mod"
    assert res["install_step_count"] == 1 and res["required_file_count"] == 1
    assert not res["warnings"]

    fomod = tmp_path / "staging" / "fomod-test" / "fomod"
    info = ET.parse(fomod / "info.xml").getroot()
    assert info.tag == "fomod"
    assert info.findtext("Name") == "Test Armor Mod"
    assert info.findtext("Author") == "m4rmz"

    mc = ET.parse(fomod / "ModuleConfig.xml").getroot()
    assert mc.findtext("moduleName") == "Test Armor Mod"
    # required folder present
    rif = mc.find("requiredInstallFiles")
    assert rif is not None and rif.find("folder").get("source") == "Data"
    # one step, one group SelectExactlyOne, two plugins
    grp = mc.find("installSteps/installStep/optionalFileGroups/group")
    assert grp.get("type") == "SelectExactlyOne"
    plugins = grp.findall("plugins/plugin")
    assert [p.get("name") for p in plugins] == ["Red", "Blue"]
    assert plugins[0].find("typeDescriptor/type").get("name") == "Recommended"
    assert plugins[0].find("files/file").get("destination") == "Textures"


def test_missing_name_raises(tmp_path):
    cfg = _cfg(tmp_path)
    with pytest.raises(Fo4McpError) as exc:
        fo4_generate_fomod(cfg, {"author": "x"}, "staging/out")
    assert "name is required" in str(exc.value)


def test_forbidden_output_raises(tmp_path):
    cfg = _cfg(tmp_path)
    forbidden = "C:/Program Files (x86)/Steam/steamapps/common/Fallout 4/Data/fomod"
    with pytest.raises(PathForbiddenError):
        fo4_generate_fomod(cfg, {"name": "X"}, forbidden)


def test_nonstandard_types_warn_not_fail(tmp_path):
    cfg = _cfg(tmp_path)
    spec = {
        "name": "Y",
        "install_steps": [
            {"name": "S", "groups": [
                {"name": "G", "type": "SelectWeird", "plugins": [
                    {"name": "P", "description": "d", "type": "Bogus"}
                ]}
            ]}
        ],
    }
    res = fo4_generate_fomod(cfg, spec, "staging/warn-test")["data"]
    assert res["ok"]
    assert any("SelectWeird" in w for w in res["warnings"])
    assert any("Bogus" in w for w in res["warnings"])


def test_minimal_spec_name_only(tmp_path):
    cfg = _cfg(tmp_path)
    res = fo4_generate_fomod(cfg, {"name": "Bare"}, "staging/bare")["data"]
    assert res["ok"] and res["install_step_count"] == 0 and res["required_file_count"] == 0
    fomod = tmp_path / "staging" / "bare" / "fomod"
    assert (fomod / "info.xml").exists() and (fomod / "ModuleConfig.xml").exists()
