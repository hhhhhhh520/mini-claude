"""Safety utilities for tool execution."""

import os
import re
from typing import Tuple
from pathlib import Path

from mini_claude.config.settings import settings


# Dangerous command patterns
DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"rm\s+-r\s+-f",
    r"rm\s+-f\s+-r",
    r"dd\s+if=",
    r"chmod\s+777",
    r">\s*/dev/sd",
    r">\s*/dev/hd",
    r"mkfs",
    r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb
    r"curl.*\|\s*bash",
    r"wget.*\|\s*bash",
    r"eval\s+",
    r"exec\s+",
]

# Protected paths that should never be accessed
PROTECTED_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "~/.config/gcloud",
]


def validate_command(command: str) -> Tuple[bool, str]:
    """Validate a shell command for safety.

    Returns:
        Tuple of (is_safe, reason)
    """
    # Check for dangerous patterns
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Dangerous command pattern detected: {pattern}"

    # Check for shell injection attempts
    if any(char in command for char in [";", "&&", "||", "|"]):
        # Allow some common safe combinations
        safe_prefixes = ["ls", "cat", "echo", "pwd", "which"]
        first_cmd = command.split(";")[0].split("&&")[0].split("||")[0].split("|")[0].strip()

        if not any(first_cmd.startswith(prefix) for prefix in safe_prefixes):
            return False, "Shell command chaining detected - requires confirmation"

    return True, "OK"


def validate_path(path: str, workspace: str = None, allow_outside: bool = False) -> Tuple[bool, str]:
    """Validate a file path is within workspace.

    Args:
        path: The path to validate
        workspace: The workspace root directory
        allow_outside: If True, allow paths outside workspace (for read operations)

    Returns:
        Tuple of (is_valid, reason)
    """
    workspace = workspace or settings.workspace_root
    workspace_abs = os.path.abspath(workspace)
    path_abs = os.path.abspath(path)

    # Check for protected paths
    for protected in PROTECTED_PATHS:
        protected_expanded = os.path.expanduser(protected)
        if path_abs.startswith(protected_expanded):
            return False, f"Access to protected path denied: {protected}"

    # Check path is within workspace (skip if allow_outside)
    if not allow_outside and not path_abs.startswith(workspace_abs):
        return False, f"Path outside workspace: {path}"

    # Check for path traversal
    if ".." in path:
        return False, "Path traversal detected"

    return True, "OK"


def is_binary_file(path: str) -> bool:
    """Check if a file is binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except Exception:
        return True


def get_file_size(path: str) -> int:
    """Get file size in bytes."""
    try:
        return os.path.getsize(path)
    except Exception:
        return 0


def truncate_content(content: str, max_length: int = 10000) -> str:
    """Truncate content if too long."""
    if len(content) > max_length:
        return content[:max_length] + f"\n\n... [truncated, {len(content) - max_length} more chars]"
    return content


class SafetyChecker:
    """Safety checker for tool operations."""

    def __init__(self, workspace: str = None):
        self.workspace = workspace or settings.workspace_root

    def check_command(self, command: str) -> Tuple[bool, str]:
        """Check if a command is safe to execute."""
        return validate_command(command)

    def check_path(self, path: str, allow_outside: bool = False) -> Tuple[bool, str]:
        """Check if a path is safe to access."""
        return validate_path(path, self.workspace, allow_outside)

    def check_file_read(self, path: str) -> Tuple[bool, str]:
        """Check if a file can be safely read."""
        # Allow reading files outside workspace for read operations
        is_valid, reason = self.check_path(path, allow_outside=True)
        if not is_valid:
            return is_valid, reason

        if not os.path.exists(path):
            return False, f"File not found: {path}"

        if is_binary_file(path):
            return False, f"Cannot read binary file: {path}"

        size = get_file_size(path)
        if size > 1_000_000:  # 1MB limit
            return False, f"File too large ({size} bytes): {path}"

        return True, "OK"

    def check_file_write(self, path: str) -> Tuple[bool, str]:
        """Check if a file can be safely written."""
        is_valid, reason = self.check_path(path)
        if not is_valid:
            return is_valid, reason

        # Check parent directory exists
        parent = os.path.dirname(path)
        if parent and not os.path.exists(parent):
            return False, f"Parent directory does not exist: {parent}"

        return True, "OK"
