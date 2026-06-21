"""Config + environment detection.

Resolution order (first hit wins):
  1. Explicit .env value (FO4_INSTALL_DIR=...)
  2. OS env var with same name
  3. Heuristic auto-detect (Steam library scan, etc.)
  4. None (caller decides whether that's an error)

`Config` is a frozen dataclass; tools should accept it as a parameter so
they're trivial to test with synthetic configs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv optional — fall back to a minimal parser
    def load_dotenv(env_file=None, override: bool = False, **_) -> bool:  # type: ignore[no-redef]
        if env_file is None:
            return False
        path = Path(env_file)
        if not path.exists():
            return False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key:
                continue
            if override or key not in os.environ:
                os.environ[key] = val
        return True

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    repo_root: Path
    fo4_install_dir: Path | None
    fo4_user_docs: Path | None
    fo4_localappdata: Path | None
    mo2_instance_dir: Path | None
    tools_dir: Path
    log_level: str
    subprocess_timeout: int


# ---- Auto-detect helpers ------------------------------------------------------

_DEFAULT_STEAM_LIBRARIES = (
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Program Files\Steam\steamapps\common",
    r"D:\Steam\steamapps\common",
    r"D:\SteamLibrary\steamapps\common",
    r"E:\SteamLibrary\steamapps\common",
)


def _detect_fo4_install() -> Path | None:
    """Look for Fallout4.exe in the usual Steam library locations."""
    for lib in _DEFAULT_STEAM_LIBRARIES:
        candidate = Path(lib) / "Fallout 4"
        if (candidate / "Fallout4.exe").exists():
            return candidate
    return None


def _detect_user_docs() -> Path | None:
    candidate = Path(os.path.expandvars(r"%USERPROFILE%\Documents\My Games\Fallout4"))
    return candidate if candidate.exists() else None


def _detect_localappdata() -> Path | None:
    candidate = Path(os.path.expandvars(r"%LOCALAPPDATA%\Fallout4"))
    return candidate if candidate.exists() else None


def _looks_like_mo2_instance(path: Path) -> bool:
    """True if `path` is a *configured* MO2 instance.

    A configured instance always has `ModOrganizer.ini` at its root (this is
    written when the instance is created), or — defensively — a
    `profiles/` + `mods/` pair. A portable MO2 that's only been *extracted*
    (binary present, never launched) has `ModOrganizer.exe` and an empty
    `mods/` but no `.ini` and no `profiles/` yet, so it reads as NOT
    configured and detection falls through. Onboarding (the GUI first-launch)
    is what flips this to True.
    """
    if (path / "ModOrganizer.ini").exists():
        return True
    if (path / "profiles").is_dir() and (path / "mods").is_dir():
        return True
    return False


def _detect_portable_mo2(repo_root: Path) -> Path | None:
    """Repo-internal portable instance: <repo>/tools/mo2/portable."""
    portable = repo_root / "tools" / "mo2" / "portable"
    return portable if _looks_like_mo2_instance(portable) else None


def _detect_classic_mo2() -> Path | None:
    """Per-user instance under %LOCALAPPDATA%\\ModOrganizer\\Fallout4."""
    candidate = Path(os.path.expandvars(r"%LOCALAPPDATA%\ModOrganizer\Fallout4"))
    return candidate if candidate.exists() else None


def _detect_mo2_instance(repo_root: Path | None = None) -> Path | None:
    """MO2 instance for Fallout 4. None if no configured instance found.

    Precedence:
      1. repo-internal portable (tools/mo2/portable) if configured
      2. classic per-user instance (%LOCALAPPDATA%/ModOrganizer/Fallout4)

    Note: the `.env` MO2_INSTANCE_DIR override still wins over this in
    load_config(); this is the auto-detect fallback (secondary question #5).
    """
    if repo_root is not None:
        portable = _detect_portable_mo2(repo_root)
        if portable is not None:
            return portable
    return _detect_classic_mo2()


def _resolve_repo_root(start: Path) -> Path:
    """Walk upward from `start` until pyproject.toml found."""
    cur = start.resolve()
    for _ in range(8):  # don't walk forever
        if (cur / "pyproject.toml").exists():
            # mcp-server/pyproject.toml — repo root is its parent
            return cur.parent
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


# ---- Load --------------------------------------------------------------------

def load_config(env_file: Path | None = None) -> Config:
    """Build Config from .env + OS env + auto-detection."""
    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)
        log.debug("loaded .env from %s", env_file)

    def env(key: str) -> str | None:
        v = os.environ.get(key)
        if v:
            v = os.path.expandvars(v)
        return v or None

    def env_path(key: str) -> Path | None:
        v = env(key)
        return Path(v) if v else None

    repo_root = env_path("FO4_REPO_ROOT") or _resolve_repo_root(Path(__file__).resolve())

    return Config(
        repo_root          = repo_root,
        fo4_install_dir    = env_path("FO4_INSTALL_DIR")  or _detect_fo4_install(),
        fo4_user_docs      = env_path("FO4_USER_DOCS")    or _detect_user_docs(),
        fo4_localappdata   = env_path("FO4_LOCALAPPDATA") or _detect_localappdata(),
        mo2_instance_dir   = env_path("MO2_INSTANCE_DIR") or _detect_mo2_instance(repo_root),
        tools_dir          = env_path("FO4_TOOLS_DIR")    or (repo_root / "tools"),
        log_level          = (env("LOG_LEVEL") or "INFO").upper(),
        subprocess_timeout = int(env("SUBPROCESS_TIMEOUT") or "120"),
    )
