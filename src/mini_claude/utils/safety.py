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
    r"rm\s+/",
    r"dd\s+if=",
    r"chmod\s+777",
    r">\s*/dev/sd",
    r">\s*/dev/hd",
    r"mkfs",
    r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb
    r"curl.*\|\s*bash",
    r"curl.*\|\s*sh",
    r"wget.*\|\s*bash",
    r"wget.*\|\s*sh",
    r"eval\s+",
    r"exec\s+",
    r"sudo\s+",
    r"su\s+",
    r"shutdown",
    r"reboot",
    r"init\s+[06]",
    r"systemctl\s+stop",
    r"systemctl\s+disable",
    r"service\s+\w+\s+stop",
    r"kill\s+-9\s+1",
    r"killall",
    # Windows specific
    r"format\s+",
    r"diskpart",
    r"bcdedit",
    r"reg\s+delete",
    r"reg\s+add",
    r"powershell.*-enc",
    r"powershell.*-e\s",
    r"cmd\s+/c\s+del",
    r"cmd\s+/c\s+format",
]

# Commands that require user confirmation even if not dangerous
CONFIRMATION_REQUIRED_PATTERNS = [
    r"git\s+push",
    r"git\s+reset\s+--hard",
    r"git\s+clean\s+-fd",
    r"npm\s+publish",
    r"pip\s+uninstall",
    r"conda\s+remove",
    r"docker\s+rm",
    r"docker\s+rmi",
    r"docker\s+system\s+prune",
]

# Protected paths that should never be accessed
PROTECTED_PATHS = [
    "/etc/passwd",
    "/etc/shadow",
    "/etc/ssh/",
    "~/.ssh",
    "~/.gnupg",
    "~/.aws",
    "~/.config/gcloud",
    "~/.bash_history",
    "~/.netrc",
    "~/.pgpass",
]

# Shell chaining characters
SHELL_CHAIN_CHARS = [";", "&&", "||", "|", "`", "$("]


def validate_command(command: str) -> Tuple[bool, str]:
    """Validate a shell command for safety.

    Returns:
        Tuple of (is_safe, reason)
    """
    command_stripped = command.strip()

    # Check for dangerous patterns first
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Dangerous command pattern detected: {pattern}"

    # Check for confirmation-required patterns
    for pattern in CONFIRMATION_REQUIRED_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return False, f"Command requires user confirmation: {pattern}"

    # Check for shell injection/chaining - STRICT: require confirmation for ALL chaining
    for chain_char in SHELL_CHAIN_CHARS:
        if chain_char in command:
            # Only allow simple pipe for read-only commands
            if chain_char == "|":
                # Check if it's a safe read-only pipe (e.g., cat file | grep pattern)
                pipe_parts = command.split("|")
                first_cmd = pipe_parts[0].strip().split()[0] if pipe_parts[0].strip() else ""
                read_only_cmds = ["cat", "head", "tail", "less", "more", "grep", "find", "ls", "echo", "sort", "uniq", "wc", "awk", "sed"]

                # Check all parts are read-only
                all_read_only = all(
                    any(part.strip().startswith(cmd) for cmd in read_only_cmds)
                    for part in pipe_parts if part.strip()
                )

                if all_read_only:
                    continue  # Allow read-only pipes

            return False, f"Shell command chaining detected ('{chain_char}') - requires confirmation"

    # Check for URL-encoded or escaped dangerous characters
    encoded_patterns = [
        (r"%3B", ";"),
        (r"%26%26", "&&"),
        (r"%7C", "|"),
        (r"\\x3b", ";"),
        (r"\\x26", "&"),
        (r"\\x7c", "|"),
    ]
    for encoded, decoded in encoded_patterns:
        if encoded in command.lower():
            return False, f"URL-encoded shell character detected ({encoded} = {decoded})"

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
    import urllib.parse

    workspace = workspace or settings.workspace_root
    workspace_abs = os.path.abspath(workspace)

    # 1. Check for URL-encoded path traversal
    try:
        decoded_path = urllib.parse.unquote(path)
        if decoded_path != path:
            # Path was URL-encoded, check the decoded version
            if ".." in decoded_path:
                return False, "URL-encoded path traversal detected"
    except Exception:
        pass

    # 2. Check for various path traversal patterns
    traversal_patterns = [
        "..",           # Basic traversal
        "../",          # Unix traversal
        "..\\",         # Windows traversal
        "%2e%2e",       # URL-encoded ..
        "%2e%2e%2f",    # URL-encoded ../
        "%2e%2e%5c",    # URL-encoded ..\
        "..%2f",        # Partial encoding
        "..%5c",        # Partial encoding Windows
    ]
    path_lower = path.lower()
    for pattern in traversal_patterns:
        if pattern in path_lower:
            return False, f"Path traversal pattern detected: {pattern}"

    # 3. Resolve the path (handles symlinks)
    try:
        # First get absolute path
        path_abs = os.path.abspath(path)

        # Then resolve symlinks using realpath
        path_real = os.path.realpath(path_abs)

        # Check if resolved path is different (symlink detected)
        if path_real != path_abs:
            # Verify the symlink target is still within workspace
            if not allow_outside and not path_real.startswith(workspace_abs):
                return False, f"Symlink points outside workspace: {path} -> {path_real}"
    except Exception as e:
        return False, f"Path resolution error: {e}"

    # 4. Check for Windows drive letter bypass (e.g., C:\, D:\)
    if os.name == 'nt' or '\\' in path:
        # Normalize path separators
        normalized = path.replace('\\', '/')
        # Check for absolute Windows paths
        if re.match(r'^[a-zA-Z]:', normalized):
            drive_path = os.path.abspath(path)
            if not allow_outside and not drive_path.startswith(workspace_abs):
                return False, f"Absolute Windows path outside workspace: {path}"

    # 5. Check for protected paths
    for protected in PROTECTED_PATHS:
        protected_expanded = os.path.expanduser(protected)
        protected_abs = os.path.abspath(protected_expanded)
        if path_real.startswith(protected_abs) or path_abs.startswith(protected_abs):
            return False, f"Access to protected path denied: {protected}"

    # 6. Check path is within workspace (skip if allow_outside)
    if not allow_outside and not path_real.startswith(workspace_abs):
        return False, f"Path outside workspace: {path}"

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

        # Note: Parent directory will be created automatically by write_file
        # So we don't need to check if it exists here
        return True, "OK"
