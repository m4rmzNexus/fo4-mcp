"""Path safety boundary — Karar 4 enforcement.

Every write attempt from a tool must pass through `check_write()`. The
default policy is **deny**: writes are only allowed under the repo's
staging/research directories, or to diff-gated subdirs of fixtures/staging.

Reads are permissive — Steam game folder, Documents, LocalAppData are all
read-only data sources, so reading them is fine, but no tool should ever
write to them.

This module is pure (no I/O) so it's trivial to unit-test.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .errors import PathForbiddenError


class WriteDisposition(str, Enum):
    ALLOW = "allow"                 # write freely, no diff gate
    ALLOW_DIFF_GATED = "diff_gated" # write OK but caller must show diff first
    DENY = "deny"


@dataclass(frozen=True)
class PathRule:
    pattern: str          # path prefix relative to repo root, or absolute
    disposition: WriteDisposition
    reason: str


# Karar 4 tablosu — repo-relative patterns first, then absolute forbidden zones.
# Order matters: first match wins.
_REPO_RULES: tuple[PathRule, ...] = (
    PathRule("staging/",   WriteDisposition.ALLOW,            "generated outputs landing zone"),
    PathRule("research/",  WriteDisposition.ALLOW,            "research outputs landing zone"),
    PathRule("tools/",     WriteDisposition.ALLOW,            "tool downloads (gitignored)"),
    PathRule("fixtures/",  WriteDisposition.ALLOW_DIFF_GATED, "test ESPs / configs (commit-tracked)"),
    PathRule("docs/",      WriteDisposition.ALLOW_DIFF_GATED, "doc edits should be diff-reviewed"),
    PathRule("mcp-server/", WriteDisposition.ALLOW_DIFF_GATED, "code edits should be diff-reviewed"),
    PathRule("skills/",    WriteDisposition.ALLOW_DIFF_GATED, "skill pack edits"),
)

# Absolute forbidden — never write here regardless of repo membership.
_ABSOLUTE_FORBIDDEN: tuple[tuple[str, str], ...] = (
    ("steam/steamapps/common/fallout 4", "Steam game folder is READ-ONLY"),
    ("steamapps/common/fallout 4",       "Steam game folder is READ-ONLY"),
    ("documents/my games/fallout4",      "user docs are READ-ONLY data source"),
    ("appdata/local/fallout4",           "user appdata is READ-ONLY data source"),
)

# Allowed-outside-repo — narrow exceptions for Claude-managed metadata that
# lives in the user profile, not the repo. The PreToolUse hook routes Write/Edit
# through check_write(), so without these the harness can't write its own
# plan files or persistent memory.
#   * /.claude/plans/    — plan-mode plan files
#   * /.claude/projects/ — per-project transcripts + auto-memory dir
# Scoped to these subtrees ONLY — credentials and settings live at the
# ~/.claude/ root (not under plans/ or projects/) and stay DENY.
_OUTSIDE_REPO_ALLOWED: tuple[str, ...] = (
    "/.claude/plans/",
    "/.claude/projects/",
)


def _normalize(p: str | Path) -> str:
    """Lowercase + forward-slash normalize for case-insensitive comparison.

    Windows paths come in as backslash-separated; we treat them
    case-insensitively because NTFS does.
    """
    return str(p).replace("\\", "/").lower()


def check_write(target: str | Path, repo_root: str | Path) -> WriteDisposition:
    """Decide whether a write to `target` is allowed.

    Returns the disposition; raises `PathForbiddenError` for DENY.

    Caller is expected to honor `ALLOW_DIFF_GATED` by showing the user a
    diff before performing the write.
    """
    norm_target = _normalize(Path(target).resolve())
    norm_repo   = _normalize(Path(repo_root).resolve())

    # Absolute forbidden zones — fail closed.
    for needle, reason in _ABSOLUTE_FORBIDDEN:
        if needle in norm_target:
            raise PathForbiddenError(str(target), reason)

    # Inside repo? Match against rules.
    if norm_target.startswith(norm_repo + "/") or norm_target == norm_repo:
        rel = norm_target[len(norm_repo) + 1:] if norm_target != norm_repo else ""
        for rule in _REPO_RULES:
            if rel.startswith(_normalize(rule.pattern)):
                if rule.disposition == WriteDisposition.DENY:
                    raise PathForbiddenError(str(target), rule.reason)
                return rule.disposition
        # Inside repo but no rule matched -> require explicit diff gate.
        return WriteDisposition.ALLOW_DIFF_GATED

    # Narrow outside-repo allowlist (e.g. Claude plan files in the user profile).
    for needle in _OUTSIDE_REPO_ALLOWED:
        if needle in norm_target:
            return WriteDisposition.ALLOW

    # Outside repo and not in absolute forbidden -> deny by default.
    raise PathForbiddenError(
        str(target),
        "outside repo root; only Steam/Docs/AppData are readable, and they're read-only",
    )


def forbidden_reason(target: str | Path) -> str | None:
    """Return the forbidden-zone reason if `target` sits in an absolute-forbidden
    zone (Steam game folder, user Docs, AppData/Fallout4), else None.

    Unlike check_write(), this does NOT apply the outside-repo default-deny.
    It's for best-effort Bash/shell gating, where writing to temp dirs, the
    cwd, or other arbitrary paths is legitimate — we only want to catch a
    command clearly clobbering a read-only data source. Fail-open by design.
    """
    norm = _normalize(Path(target).resolve())
    for needle, reason in _ABSOLUTE_FORBIDDEN:
        if needle in norm:
            return reason
    return None


def is_inside(path: str | Path, parent: str | Path) -> bool:
    """Helper: is `path` underneath `parent`? Case-insensitive on Windows."""
    np = _normalize(Path(path).resolve())
    nq = _normalize(Path(parent).resolve())
    return np == nq or np.startswith(nq + "/")
