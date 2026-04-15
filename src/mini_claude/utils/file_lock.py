"""File locking and conflict detection for parallel agent execution."""

import os
import hashlib
import asyncio
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class LockState(Enum):
    """State of a file lock."""
    UNLOCKED = "unlocked"
    LOCKED = "locked"
    CONFLICT = "conflict"


@dataclass
class FileLock:
    """Represents a lock on a file."""
    path: str
    agent_id: str
    locked_at: datetime = field(default_factory=datetime.now)
    original_hash: Optional[str] = None
    lock_type: str = "write"  # "write" or "read"


@dataclass
class FileVersion:
    """Tracks file version for optimistic locking."""
    path: str
    hash: str
    modified_at: datetime = field(default_factory=datetime.now)
    modified_by: Optional[str] = None


class FileLockManager:
    """Manages file locks and conflict detection for parallel agents."""

    def __init__(self):
        self._locks: Dict[str, FileLock] = {}
        self._versions: Dict[str, FileVersion] = {}
        self._lock = asyncio.Lock()

    def _normalize_path(self, path: str) -> str:
        """Normalize file path for consistent key."""
        return os.path.abspath(path).replace("\\", "/")

    def _compute_hash(self, path: str) -> Optional[str]:
        """Compute MD5 hash of file content."""
        try:
            with open(path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except FileNotFoundError:
            return None
        except Exception:
            return None

    async def acquire_lock(
        self,
        path: str,
        agent_id: str,
        lock_type: str = "write"
    ) -> Tuple[bool, str]:
        """Acquire a lock on a file.

        Returns:
            Tuple of (success, message)
        """
        async with self._lock:
            norm_path = self._normalize_path(path)

            # Check if file is already locked
            if norm_path in self._locks:
                existing = self._locks[norm_path]

                # Read locks can share with other read locks
                if lock_type == "read" and existing.lock_type == "read":
                    return True, f"Shared read lock granted"

                # Write lock conflicts with any existing lock
                if existing.agent_id != agent_id:
                    return False, (
                        f"File locked by agent '{existing.agent_id}' "
                        f"(locked at {existing.locked_at.strftime('%H:%M:%S')})"
                    )

            # Compute hash for conflict detection
            file_hash = self._compute_hash(path)

            # Create lock
            self._locks[norm_path] = FileLock(
                path=norm_path,
                agent_id=agent_id,
                original_hash=file_hash,
                lock_type=lock_type
            )

            # Track version
            if file_hash:
                self._versions[norm_path] = FileVersion(
                    path=norm_path,
                    hash=file_hash,
                    modified_by=agent_id
                )

            return True, f"Lock acquired for {path}"

    async def release_lock(self, path: str, agent_id: str) -> Tuple[bool, str]:
        """Release a lock on a file."""
        async with self._lock:
            norm_path = self._normalize_path(path)

            if norm_path not in self._locks:
                return True, "No lock to release"

            existing = self._locks[norm_path]
            if existing.agent_id != agent_id:
                return False, f"Lock owned by agent '{existing.agent_id}'"

            del self._locks[norm_path]
            return True, "Lock released"

    async def check_conflict(self, path: str, agent_id: str) -> Tuple[bool, Optional[str]]:
        """Check if file has been modified since lock was acquired.

        Returns:
            Tuple of (has_conflict, conflict_details)
        """
        async with self._lock:
            norm_path = self._normalize_path(path)

            if norm_path not in self._locks:
                return False, None

            lock = self._locks[norm_path]

            # Only check for write locks
            if lock.lock_type != "write":
                return False, None

            # If file didn't exist when locked, no conflict
            if lock.original_hash is None:
                # Check if file exists now
                if os.path.exists(path):
                    return True, "File was created by another agent"
                return False, None

            # Compare current hash with original
            current_hash = self._compute_hash(path)

            if current_hash != lock.original_hash:
                return True, (
                    f"File was modified by another agent. "
                    f"Original hash: {lock.original_hash[:8]}..., "
                    f"Current hash: {current_hash[:8] if current_hash else 'N/A'}..."
                )

            return False, None

    async def update_version(self, path: str, agent_id: str) -> None:
        """Update file version after successful write."""
        async with self._lock:
            norm_path = self._normalize_path(path)
            file_hash = self._compute_hash(path)

            if file_hash:
                self._versions[norm_path] = FileVersion(
                    path=norm_path,
                    hash=file_hash,
                    modified_by=agent_id
                )

    def get_lock_info(self, path: str) -> Optional[Dict]:
        """Get lock information for a file."""
        norm_path = self._normalize_path(path)

        if norm_path in self._locks:
            lock = self._locks[norm_path]
            return {
                "agent_id": lock.agent_id,
                "locked_at": lock.locked_at.isoformat(),
                "lock_type": lock.lock_type,
            }
        return None

    def get_all_locks(self) -> Dict[str, Dict]:
        """Get all current locks."""
        return {
            path: {
                "agent_id": lock.agent_id,
                "locked_at": lock.locked_at.isoformat(),
                "lock_type": lock.lock_type,
            }
            for path, lock in self._locks.items()
        }

    async def release_all_for_agent(self, agent_id: str) -> int:
        """Release all locks held by an agent. Returns count of released locks."""
        async with self._lock:
            to_release = [
                path for path, lock in self._locks.items()
                if lock.agent_id == agent_id
            ]
            for path in to_release:
                del self._locks[path]
            return len(to_release)


# Global file lock manager
file_lock_manager = FileLockManager()
