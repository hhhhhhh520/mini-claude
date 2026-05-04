"""Safety utilities for tool execution."""

import os
import re
import time
import threading
from typing import Tuple, Set, Dict, List, Any, Optional
from collections import defaultdict
from dataclasses import dataclass, field

from mini_claude.config.settings import settings


# Approved paths cache (persists during session)
_approved_paths: Set[str] = set()

# Paths pending confirmation (for async confirmation flow)
_pending_confirmations: dict = {}


# Dangerous command patterns
DANGEROUS_PATTERNS = [
    r"rm\s+-rf",
    r"rm\s+-r\s+-f",
    r"rm\s+-f\s+-r",
    r"rm\s+/",
    r"dd\s+if=",
    r"chmod\s+777",
    r"chmod\s+-R\s+777",      # 全系统权限开放
    r"chown\s+-R",            # 批量修改所有权
    r">\s*/dev/sd",
    r">\s*/dev/hd",
    r">\s*/etc/",             # 系统配置覆盖
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
    # 容器与云凭证
    "~/.docker/config.json",   # Docker 凭证
    "~/.kube/config",          # Kubernetes 凭证
    "~/.npmrc",                # npm 凭证
    "~/.pypirc",               # PyPI 凭证
    # Windows 敏感目录
    "~/AppData/Roaming/Microsoft/Credentials",
    "~/AppData/Local/Microsoft/Credentials",
]

# Shell chaining characters
SHELL_CHAIN_CHARS = [";", "&&", "||", "|", "`", "$("]


# Sensitive information patterns for input filtering
# Each pattern is a tuple of (regex_pattern, category, severity)
SENSITIVE_PATTERNS = [
    # API Key patterns - High severity
    (r'\bsk-[a-zA-Z0-9]{10,}', 'api_key', 'high'),  # OpenAI API key (at least 10 chars after sk-)
    (r'\bsk-proj-[a-zA-Z0-9]{10,}', 'api_key', 'high'),  # OpenAI project key
    (r'\bapi[_-]?key\s*=\s*["\']?[^\s"\']{4,}["\']?', 'api_key', 'high'),  # api_key=xxx or api-key=xxx
    (r'\bx-api-key\s*[:=]\s*["\']?[^\s"\']{4,}["\']?', 'api_key', 'high'),  # x-api-key: xxx
    (r'\bAKIA[A-Z0-9]{16}\b', 'api_key', 'high'),  # AWS access key

    # Password patterns - Medium/High severity
    (r'\bpassword\s*=\s*["\']?[^\s"\']{3,}["\']?', 'password', 'medium'),  # password=xxx
    (r'\bpasswd\s*=\s*["\']?[^\s"\']{3,}["\']?', 'password', 'medium'),  # passwd=xxx
    (r'\bpwd\s*=\s*["\']?[^\s"\']{3,}["\']?', 'password', 'medium'),  # pwd=xxx

    # Token patterns - High severity
    (r'\bbearer\s+[a-zA-Z0-9_\-\.]{4,}', 'token', 'high'),  # Bearer xxx
    (r'\btoken\s*=\s*["\']?[^\s"\']{4,}["\']?', 'token', 'high'),  # token=xxx
    (r'\bjwt\s+[a-zA-Z0-9_\-]{20,}', 'token', 'high'),  # jwt xxx (longer, real JWT format)
    (r'\bghp_[a-zA-Z0-9]{36}', 'token', 'high'),  # GitHub personal access token
    (r'\bgho_[a-zA-Z0-9]{36}', 'token', 'high'),  # GitHub OAuth token
    (r'\bghr_[a-zA-Z0-9]{36}', 'token', 'high'),  # GitHub refresh token
    (r'\bghu_[a-zA-Z0-9]{36}', 'token', 'high'),  # GitHub user-to-server token
    (r'\bghs_[a-zA-Z0-9]{36}', 'token', 'high'),  # GitHub server-to-server token

    # Connection strings with credentials - High severity
    (r'\bmysql://[^:]+:[^@]+@[^/\s]+', 'connection_string', 'high'),  # mysql://user:pass@host
    (r'\bpostgresql://[^:]+:[^@]+@[^/\s]+', 'connection_string', 'high'),  # postgresql://user:pass@host
    (r'\bmongodb(\+srv)?://[^:]+:[^@]+@[^/\s]+', 'connection_string', 'high'),  # mongodb://user:pass@host
    (r'\bredis://[^:]*:[^@]+@[^/\s]+', 'connection_string', 'high'),  # redis://:pass@host
    (r'\bpostgres://[^:]+:[^@]+@[^/\s]+', 'connection_string', 'high'),  # postgres://user:pass@host
]


def check_sensitive_input(text: str) -> Dict[str, Any]:
    """Check input text for sensitive information patterns.

    Args:
        text: The input text to check for sensitive patterns.

    Returns:
        Dictionary with keys:
        - detected: bool - True if sensitive patterns were found
        - patterns: List[str] - List of pattern categories detected
        - severity: str - "high", "medium", "low", or "none"
        - matches: List[Dict] - Detailed match information (for logging)
    """
    if not text or not text.strip():
        return {
            "detected": False,
            "patterns": [],
            "severity": "none",
            "matches": []
        }

    detected_patterns: Set[str] = set()
    matches: List[Dict[str, Any]] = []
    max_severity = "none"

    severity_order = {"none": 0, "low": 1, "medium": 2, "high": 3}

    for pattern, category, severity in SENSITIVE_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            detected_patterns.add(category)
            matches.append({
                "category": category,
                "severity": severity,
                "match_start": match.start(),
                "match_end": match.end(),
            })
            if severity_order.get(severity, 0) > severity_order.get(max_severity, 0):
                max_severity = severity

    return {
        "detected": bool(detected_patterns),
        "patterns": sorted(list(detected_patterns)),
        "severity": max_severity if detected_patterns else "none",
        "matches": matches
    }


def validate_command(command: str) -> Tuple[bool, str]:
    """Validate a shell command for safety.

    Returns:
        Tuple of (is_safe, reason)
    """
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


def is_path_approved(path: str) -> bool:
    """Check if a path has been approved by user."""
    path_abs = os.path.abspath(path)
    # Check if path or any parent directory is approved
    for approved in _approved_paths:
        if path_abs.startswith(approved):
            return True
    return False


def approve_path(path: str) -> None:
    """Add a path to the approved list."""
    path_abs = os.path.abspath(path)
    _approved_paths.add(path_abs)


def clear_approved_paths() -> None:
    """Clear all approved paths."""
    _approved_paths.clear()


def get_approved_paths() -> Set[str]:
    """Get all approved paths."""
    return _approved_paths.copy()


class PathConfirmationRequired(Exception):
    """Exception raised when path requires user confirmation."""
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Path requires confirmation: {path} - {reason}")


def validate_path(path: str, workspace: str = None, allow_outside: bool = False, require_confirmation: bool = True) -> Tuple[bool, str]:
    """Validate a file path is within workspace.

    Args:
        path: The path to validate
        workspace: The workspace root directory
        allow_outside: If True, allow paths outside workspace (for read operations)
        require_confirmation: If True, raise exception for paths needing confirmation

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
                # Check if already approved
                if is_path_approved(drive_path):
                    return True, "OK"
                # Raise confirmation exception if enabled
                if require_confirmation:
                    raise PathConfirmationRequired(
                        drive_path,
                        f"Path is outside workspace ({workspace})"
                    )
                return False, f"Absolute Windows path outside workspace: {path}"

    # 5. Check for protected paths
    for protected in PROTECTED_PATHS:
        protected_expanded = os.path.expanduser(protected)
        protected_abs = os.path.abspath(protected_expanded)
        if path_real.startswith(protected_abs) or path_abs.startswith(protected_abs):
            return False, f"Access to protected path denied: {protected}"

    # 6. Check path is within workspace (skip if allow_outside)
    if not allow_outside and not path_real.startswith(workspace_abs):
        # Check if already approved
        if is_path_approved(path_real):
            return True, "OK"
        # Raise confirmation exception if enabled
        if require_confirmation:
            raise PathConfirmationRequired(
                path_real,
                f"Path is outside workspace ({workspace})"
            )
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

    def check_path(self, path: str, allow_outside: bool = False, require_confirmation: bool = True) -> Tuple[bool, str]:
        """Check if a path is safe to access."""
        return validate_path(path, self.workspace, allow_outside, require_confirmation)

    def check_file_read(self, path: str, require_confirmation: bool = True) -> Tuple[bool, str]:
        """Check if a file can be safely read."""
        # Allow reading files outside workspace for read operations
        is_valid, reason = self.check_path(path, allow_outside=True, require_confirmation=require_confirmation)
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

    def check_file_write(self, path: str, require_confirmation: bool = True) -> Tuple[bool, str]:
        """Check if a file can be safely written."""
        is_valid, reason = self.check_path(path, require_confirmation=require_confirmation)
        if not is_valid:
            return is_valid, reason

        # Note: Parent directory will be created automatically by write_file
        # So we don't need to check if it exists here
        return True, "OK"

    def check_sensitive(self, text: str) -> Dict[str, Any]:
        """Check input text for sensitive information patterns.

        Args:
            text: The input text to check.

        Returns:
            Dictionary with detected, patterns, severity, and matches keys.
        """
        return check_sensitive_input(text)


# =============================================================================
# RATE LIMITING
# =============================================================================

@dataclass
class RateLimitEntry:
    """Entry for rate limit tracking."""
    count: int = 0
    window_start: float = 0.0
    timestamps: List[float] = field(default_factory=list)  # For sliding window
    tokens: float = 0.0  # For token bucket
    last_update: float = 0.0


class RateLimiter:
    """Rate limiter with multiple strategies.

    Supports three strategies:
    - fixed_window: Simple counting within fixed time windows (per minute)
    - sliding_window: More accurate counting using sliding time window
    - token_bucket: Allows burst traffic up to burst_size

    All strategies use in-memory storage with thread-safe operations.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        strategy: str = "sliding_window",
        burst_size: int = 10,
        enabled: bool = True,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute
            strategy: Rate limiting strategy (fixed_window, sliding_window, token_bucket)
            burst_size: Maximum burst size for token_bucket strategy
            enabled: Whether rate limiting is enabled
        """
        self.requests_per_minute = requests_per_minute
        self.strategy = strategy
        self.burst_size = burst_size
        self.enabled = enabled

        # Thread-safe storage
        self._lock = threading.RLock()
        self._entries: Dict[str, RateLimitEntry] = defaultdict(RateLimitEntry)

        # Token bucket: tokens refill rate (tokens per second)
        self._refill_rate = requests_per_minute / 60.0

    def check_limit(self, identifier: str) -> bool:
        """Check if the identifier is within rate limits.

        Args:
            identifier: Unique identifier (e.g., user_id, ip_address, session_id)

        Returns:
            True if within limits (request allowed), False if exceeded (request denied)
        """
        if not self.enabled:
            return True

        with self._lock:
            current_time = time.time()

            if self.strategy == "fixed_window":
                return self._check_fixed_window(identifier, current_time)
            elif self.strategy == "sliding_window":
                return self._check_sliding_window(identifier, current_time)
            elif self.strategy == "token_bucket":
                return self._check_token_bucket(identifier, current_time)
            else:
                # Unknown strategy, default to allowing
                return True

    def _check_fixed_window(self, identifier: str, current_time: float) -> bool:
        """Fixed window rate limiting.

        Divides time into fixed windows (1 minute each).
        Simple but can allow 2x rate at window boundaries.
        """
        entry = self._entries[identifier]
        window_start = int(current_time / 60) * 60  # Start of current minute

        if entry.window_start != window_start:
            # New window, reset count
            entry.count = 0
            entry.window_start = window_start

        if entry.count >= self.requests_per_minute:
            return False

        entry.count += 1
        entry.last_update = current_time
        return True

    def _check_sliding_window(self, identifier: str, current_time: float) -> bool:
        """Sliding window rate limiting.

        More accurate than fixed window by tracking individual timestamps.
        Counts requests in the last 60 seconds.
        """
        entry = self._entries[identifier]

        # Remove timestamps older than 60 seconds
        cutoff = current_time - 60.0
        entry.timestamps = [ts for ts in entry.timestamps if ts > cutoff]

        if len(entry.timestamps) >= self.requests_per_minute:
            return False

        entry.timestamps.append(current_time)
        entry.last_update = current_time
        return True

    def _check_token_bucket(self, identifier: str, current_time: float) -> bool:
        """Token bucket rate limiting.

        Allows burst traffic up to burst_size.
        Tokens refill at rate of requests_per_minute / 60 per second.
        """
        entry = self._entries[identifier]

        # Initialize bucket if needed
        if entry.last_update == 0.0:
            entry.tokens = float(self.burst_size)
            entry.last_update = current_time

        # Refill tokens based on time elapsed
        elapsed = current_time - entry.last_update
        entry.tokens = min(
            self.burst_size,
            entry.tokens + elapsed * self._refill_rate
        )

        if entry.tokens < 1.0:
            return False

        entry.tokens -= 1.0
        entry.last_update = current_time
        return True

    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for the identifier.

        Args:
            identifier: Unique identifier

        Returns:
            Number of remaining requests in current window/bucket
        """
        if not self.enabled:
            return self.requests_per_minute  # Unlimited when disabled

        with self._lock:
            current_time = time.time()
            entry = self._entries.get(identifier)

            if entry is None:
                if self.strategy == "token_bucket":
                    return self.burst_size
                return self.requests_per_minute

            if self.strategy == "fixed_window":
                window_start = int(current_time / 60) * 60
                if entry.window_start != window_start:
                    return self.requests_per_minute
                return max(0, self.requests_per_minute - entry.count)

            elif self.strategy == "sliding_window":
                cutoff = current_time - 60.0
                active_count = len([ts for ts in entry.timestamps if ts > cutoff])
                return max(0, self.requests_per_minute - active_count)

            elif self.strategy == "token_bucket":
                # Refill and get current tokens
                elapsed = current_time - entry.last_update
                tokens = min(
                    self.burst_size,
                    entry.tokens + elapsed * self._refill_rate
                )
                return int(tokens)

            return self.requests_per_minute

    def reset(self, identifier: str) -> None:
        """Reset rate limit for the identifier.

        Args:
            identifier: Unique identifier to reset
        """
        with self._lock:
            if identifier in self._entries:
                del self._entries[identifier]

    def reset_all(self) -> None:
        """Reset all rate limit entries."""
        with self._lock:
            self._entries.clear()

    def get_retry_after(self, identifier: str) -> float:
        """Get seconds until the identifier can make another request.

        Args:
            identifier: Unique identifier

        Returns:
            Seconds to wait (0 if not rate limited)
        """
        if not self.enabled:
            return 0.0

        with self._lock:
            current_time = time.time()
            entry = self._entries.get(identifier)

            if entry is None:
                return 0.0

            if self.strategy == "fixed_window":
                # Time until next window
                window_end = (int(current_time / 60) + 1) * 60
                return window_end - current_time

            elif self.strategy == "sliding_window":
                if not entry.timestamps:
                    return 0.0
                # Time until oldest request expires
                oldest = min(entry.timestamps)
                return max(0.0, 60.0 - (current_time - oldest))

            elif self.strategy == "token_bucket":
                if entry.tokens >= 1.0:
                    return 0.0
                # Time until one token is refilled
                return (1.0 - entry.tokens) / self._refill_rate

            return 0.0

    def get_stats(self, identifier: str) -> Dict[str, Any]:
        """Get statistics for the identifier.

        Args:
            identifier: Unique identifier

        Returns:
            Dictionary with rate limit statistics
        """
        return {
            "identifier": identifier,
            "strategy": self.strategy,
            "enabled": self.enabled,
            "limit": self.requests_per_minute,
            "remaining": self.get_remaining(identifier),
            "retry_after": self.get_retry_after(identifier),
        }


# Global rate limiter instance (lazy initialization)
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.rate_limiter.
    """
    global _rate_limiter
    if _rate_limiter is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context
            ctx = get_context()
            if ctx._rate_limiter.is_initialized():
                _rate_limiter = ctx.rate_limiter
            else:
                _rate_limiter = RateLimiter(
                    requests_per_minute=settings.rate_limit_requests_per_minute,
                    strategy=settings.rate_limit_strategy,
                    burst_size=settings.rate_limit_burst_size,
                    enabled=settings.rate_limit_enabled,
                )
                ctx.rate_limiter = _rate_limiter
        except ImportError:
            _rate_limiter = RateLimiter(
                requests_per_minute=settings.rate_limit_requests_per_minute,
                strategy=settings.rate_limit_strategy,
                burst_size=settings.rate_limit_burst_size,
                enabled=settings.rate_limit_enabled,
            )
    return _rate_limiter


def reset_rate_limiter() -> None:
    """Reset the global rate limiter (for testing)."""
    global _rate_limiter
    _rate_limiter = None
    # Also reset in context
    try:
        from mini_claude.context import get_context
        ctx = get_context()
        ctx._rate_limiter.reset()
    except ImportError:
        pass
