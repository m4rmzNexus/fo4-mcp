"""Config detection unit tests — MO2 portable detection (secondary Q5).

Hermetic: portable detection is driven off a tmp_path repo root, so these
never touch the real machine's MO2 install. The classic-fallback path is
exercised only via _detect_classic_mo2 monkeypatching.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fo4_mcp import config as cfgmod
from fo4_mcp.config import (
    _detect_mo2_instance,
    _detect_portable_mo2,
    _looks_like_mo2_instance,
    load_config,
)


def _make_portable(root: Path, *, ini: bool = False, profiles: bool = False, mods: bool = False) -> Path:
    portable = root / "tools" / "mo2" / "portable"
    portable.mkdir(parents=True, exist_ok=True)
    (portable / "ModOrganizer.exe").write_text("stub", encoding="utf-8")
    if ini:
        (portable / "ModOrganizer.ini").write_text("[General]\n", encoding="utf-8")
    if profiles:
        (portable / "profiles" / "default-ae").mkdir(parents=True, exist_ok=True)
    if mods:
        (portable / "mods").mkdir(parents=True, exist_ok=True)
    return portable


def test_portable_onboarded_with_ini_detected(tmp_path: Path):
    portable = _make_portable(tmp_path, ini=True)
    assert _detect_portable_mo2(tmp_path) == portable
    assert _looks_like_mo2_instance(portable)


def test_portable_onboarded_with_profiles_and_mods_detected(tmp_path: Path):
    portable = _make_portable(tmp_path, profiles=True, mods=True)
    assert _detect_portable_mo2(tmp_path) == portable


def test_portable_extracted_not_onboarded_returns_none(tmp_path: Path):
    """Binary extracted (+ empty mods/) but never launched -> not a configured
    instance -> None. This is the current real-world state pre-Phase B'."""
    _make_portable(tmp_path, mods=True)  # mods only, no ini, no profiles
    assert _detect_portable_mo2(tmp_path) is None


def test_portable_absent_returns_none(tmp_path: Path):
    assert _detect_portable_mo2(tmp_path) is None


def test_detect_prefers_portable_over_classic(tmp_path: Path, monkeypatch):
    _make_portable(tmp_path, ini=True)
    # Classic should never be consulted when portable is configured.
    monkeypatch.setattr(cfgmod, "_detect_classic_mo2", lambda: Path("C:/should/not/be/used"))
    assert _detect_mo2_instance(tmp_path) == tmp_path / "tools" / "mo2" / "portable"


def test_detect_falls_back_to_classic(tmp_path: Path, monkeypatch):
    sentinel = tmp_path / "classic-instance"
    monkeypatch.setattr(cfgmod, "_detect_classic_mo2", lambda: sentinel)
    # No portable configured -> classic fallback.
    assert _detect_mo2_instance(tmp_path) == sentinel


def test_detect_none_when_nothing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cfgmod, "_detect_classic_mo2", lambda: None)
    assert _detect_mo2_instance(tmp_path) is None


def test_env_override_wins(tmp_path: Path, monkeypatch):
    """MO2_INSTANCE_DIR override beats auto-detection.

    Uses monkeypatch.setenv (auto-restored at teardown) + a non-existent
    env_file so load_dotenv is skipped and nothing leaks into os.environ for
    later tests (an early version of this test poisoned FO4_REPO_ROOT and
    broke the real-binary Caprica compile test downstream)."""
    override = tmp_path / "explicit-mo2"
    override.mkdir()
    monkeypatch.setenv("FO4_REPO_ROOT", tmp_path.as_posix())
    monkeypatch.setenv("MO2_INSTANCE_DIR", override.as_posix())
    cfg = load_config(env_file=tmp_path / "does-not-exist.env")
    assert cfg.mo2_instance_dir == override
    assert cfg.repo_root == tmp_path
