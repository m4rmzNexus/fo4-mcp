"""Structured error envelope for fo4-mcp tool responses.

Every tool returns either a success dict or raises an Fo4McpError subclass.
The server layer catches these and serializes them into a uniform error
envelope so agents can branch on `error.code` without parsing prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    # path / safety
    PATH_FORBIDDEN = "path_forbidden"
    PATH_NOT_FOUND = "path_not_found"
    PATH_OUTSIDE_REPO = "path_outside_repo"

    # tool wiring
    TOOL_NOT_INSTALLED = "tool_not_installed"
    TOOL_BINARY_MISSING = "tool_binary_missing"
    TOOL_VERSION_INCOMPATIBLE = "tool_version_incompatible"

    # subprocess
    SUBPROCESS_FAILED = "subprocess_failed"
    SUBPROCESS_TIMEOUT = "subprocess_timeout"
    SUBPROCESS_OUTPUT_UNPARSEABLE = "subprocess_output_unparseable"

    # env
    ENV_FO4_NOT_DETECTED = "env_fo4_not_detected"
    ENV_MO2_DETECTION_AMBIGUOUS = "env_mo2_detection_ambiguous"

    # input
    INVALID_ARGUMENT = "invalid_argument"

    # not yet implemented
    NOT_IMPLEMENTED = "not_implemented"


@dataclass
class Fo4McpError(Exception):
    """Base error. Subclasses set a specific code."""

    code: ErrorCode
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"[{self.code.value}] {self.message}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code.value,
                "message": self.message,
                "details": self.details,
            },
        }


class PathForbiddenError(Fo4McpError):
    def __init__(self, path: str, reason: str) -> None:
        super().__init__(ErrorCode.PATH_FORBIDDEN, f"write blocked: {path} ({reason})", {"path": path, "reason": reason})


class ToolBinaryMissingError(Fo4McpError):
    def __init__(self, tool_name: str, expected_path: str | None = None) -> None:
        super().__init__(
            ErrorCode.TOOL_BINARY_MISSING,
            f"tool '{tool_name}' binary not found",
            {"tool": tool_name, "expected_path": expected_path},
        )


class SubprocessFailedError(Fo4McpError):
    def __init__(self, cmd: list[str], exit_code: int, stderr: str) -> None:
        super().__init__(
            ErrorCode.SUBPROCESS_FAILED,
            f"subprocess exited {exit_code}: {cmd[0]}",
            {"cmd": cmd, "exit_code": exit_code, "stderr_tail": stderr[-2000:]},
        )


class NotImplementedYetError(Fo4McpError):
    def __init__(self, tool_name: str, why: str = "MVP placeholder") -> None:
        super().__init__(
            ErrorCode.NOT_IMPLEMENTED,
            f"{tool_name} is not implemented yet ({why})",
            {"tool": tool_name},
        )


def ok(data: dict[str, Any]) -> dict[str, Any]:
    """Wrap a success response in the standard envelope."""
    return {"ok": True, "data": data}
