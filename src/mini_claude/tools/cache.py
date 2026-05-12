"""Tool result caching with TTL and LRU eviction."""

import hashlib
import json
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CacheEntry:
    """A single cache entry."""

    result: str
    created_at: float
    expires_at: float
    tool_name: str
    params_hash: str
    hit_count: int = 0
    file_mtime: Optional[float] = None  # For file-based tools
    file_path: Optional[str] = None  # Original file path


@dataclass
class CacheStats:
    """Cache statistics."""

    total_hits: int = 0
    total_misses: int = 0
    total_sets: int = 0
    total_evictions: int = 0
    total_invalidations: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.total_hits + self.total_misses
        if total == 0:
            return 0.0
        return self.total_hits / total


class ToolCache:
    """Tool result cache with TTL and LRU eviction.

    Features:
    - TTL (Time-To-Live) for automatic expiration
    - LRU (Least Recently Used) eviction when max size reached
    - File modification time tracking for file-based tools
    - Cache statistics (hit rate, size, etc.)
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_size: int = 100,
        cacheable_tools: Optional[List[str]] = None,
    ):
        """Initialize the cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds (default: 5 minutes)
            max_size: Maximum number of entries before LRU eviction
            cacheable_tools: List of tool names that can be cached
        """
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = CacheStats()

        # Default cacheable tools (read-only operations with stable results)
        self._cacheable_tools = cacheable_tools or [
            "read_file",
            "list_dir",
            "search_files",
            "search_content",
        ]

        # Tools that track file modification time
        self._file_based_tools = ["read_file", "list_dir", "search_files", "search_content"]

    def _generate_key(self, tool_name: str, params: Dict[str, Any]) -> str:
        """Generate a cache key from tool name and parameters.

        Args:
            tool_name: Name of the tool
            params: Tool parameters

        Returns:
            Cache key string
        """
        # Sort params for consistent hashing
        params_str = json.dumps(params, sort_keys=True, default=str)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
        return f"{tool_name}:{params_hash}"

    def _get_file_mtime(self, path: str) -> Optional[float]:
        """Get file modification time if path exists.

        Args:
            path: File path

        Returns:
            Modification time or None if file doesn't exist
        """
        try:
            if os.path.exists(path):
                return os.path.getmtime(path)
        except (OSError, IOError):
            pass
        return None

    def _extract_file_path(self, tool_name: str, params: Dict[str, Any]) -> Optional[str]:
        """Extract file path from tool parameters.

        Args:
            tool_name: Tool name
            params: Tool parameters

        Returns:
            File path or None
        """
        # Most file tools use 'path' parameter
        if "path" in params:
            return params["path"]
        # search_content uses 'path' for base directory
        if tool_name == "search_content" and "path" in params:
            return params["path"]
        return None

    def is_cacheable(self, tool_name: str) -> bool:
        """Check if a tool's results can be cached.

        Args:
            tool_name: Name of the tool

        Returns:
            True if the tool is cacheable
        """
        return tool_name in self._cacheable_tools

    def get(self, tool_name: str, params: Dict[str, Any]) -> Tuple[Optional[str], bool]:
        """Get a cached result if available and valid.

        Args:
            tool_name: Name of the tool
            params: Tool parameters

        Returns:
            Tuple of (result, hit) where result is the cached value or None,
            and hit is True if cache was hit
        """
        if not self.is_cacheable(tool_name):
            self._stats.total_misses += 1
            return None, False

        key = self._generate_key(tool_name, params)
        entry = self._cache.get(key)

        if entry is None:
            self._stats.total_misses += 1
            return None, False

        # Check TTL expiration
        current_time = time.time()
        if current_time > entry.expires_at:
            self._evict_entry(key)
            self._stats.total_misses += 1
            return None, False

        # Check file modification time for file-based tools
        if entry.file_path and entry.file_mtime is not None:
            current_mtime = self._get_file_mtime(entry.file_path)
            if current_mtime is not None and current_mtime > entry.file_mtime:
                # File was modified, invalidate cache
                self._evict_entry(key)
                self._stats.total_misses += 1
                return None, False

        # Cache hit - move to end for LRU
        self._cache.move_to_end(key)
        entry.hit_count += 1
        self._stats.total_hits += 1

        return entry.result, True

    def set(
        self,
        tool_name: str,
        params: Dict[str, Any],
        result: str,
    ) -> bool:
        """Set a cache entry.

        Args:
            tool_name: Name of the tool
            params: Tool parameters
            result: Tool result to cache

        Returns:
            True if the result was cached
        """
        # Only cache successful results (non-error results)
        if not self.is_cacheable(tool_name):
            return False

        # Don't cache error results
        if result.startswith("Error:") or result.startswith("Error "):
            return False

        key = self._generate_key(tool_name, params)
        current_time = time.time()

        # Extract file path and mtime for file-based tools
        file_path = self._extract_file_path(tool_name, params)
        file_mtime = None
        if file_path and tool_name in self._file_based_tools:
            file_mtime = self._get_file_mtime(file_path)

        entry = CacheEntry(
            result=result,
            created_at=current_time,
            expires_at=current_time + self._ttl_seconds,
            tool_name=tool_name,
            params_hash=key.split(":")[1],
            file_mtime=file_mtime,
            file_path=file_path,
        )

        # Remove existing entry if present (for move_to_end effect)
        if key in self._cache:
            del self._cache[key]

        # Evict oldest entries if at max size
        while len(self._cache) >= self._max_size:
            self._evict_oldest()

        self._cache[key] = entry
        self._stats.total_sets += 1

        return True

    def _evict_entry(self, key: str) -> None:
        """Evict a specific cache entry."""
        if key in self._cache:
            del self._cache[key]
            self._stats.total_evictions += 1

    def _evict_oldest(self) -> None:
        """Evict the oldest (first) cache entry (LRU)."""
        if self._cache:
            oldest_key = next(iter(self._cache))
            self._evict_entry(oldest_key)

    def invalidate(self, tool_name: Optional[str] = None) -> int:
        """Invalidate cache entries.

        Args:
            tool_name: If provided, only invalidate entries for this tool.
                       If None, invalidate all entries.

        Returns:
            Number of entries invalidated
        """
        if tool_name is None:
            count = len(self._cache)
            self._cache.clear()
            self._stats.total_invalidations += count
            return count

        keys_to_remove = [key for key in self._cache if key.startswith(f"{tool_name}:")]

        for key in keys_to_remove:
            del self._cache[key]

        self._stats.total_invalidations += len(keys_to_remove)
        return len(keys_to_remove)

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        return self.invalidate(None)

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl_seconds,
            "hits": self._stats.total_hits,
            "misses": self._stats.total_misses,
            "hit_rate": round(self._stats.hit_rate * 100, 2),
            "sets": self._stats.total_sets,
            "evictions": self._stats.total_evictions,
            "invalidations": self._stats.total_invalidations,
            "cacheable_tools": self._cacheable_tools,
        }

    def get_entries(self) -> List[Dict[str, Any]]:
        """Get all cache entries for display.

        Returns:
            List of cache entry details
        """
        entries = []
        current_time = time.time()

        for key, entry in self._cache.items():
            ttl_remaining = max(0, entry.expires_at - current_time)
            entries.append(
                {
                    "key": key,
                    "tool_name": entry.tool_name,
                    "created_at": entry.created_at,
                    "ttl_remaining": round(ttl_remaining, 1),
                    "hit_count": entry.hit_count,
                    "has_file_tracking": entry.file_mtime is not None,
                }
            )

        return entries

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items() if current_time > entry.expires_at
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.total_evictions += 1

        return len(expired_keys)


# Global cache instance (initialized lazily)
_cache_instance: Optional[ToolCache] = None


def get_tool_cache() -> ToolCache:
    """Get or create the global tool cache instance.

    This function provides backward compatibility with existing code.
    New code should prefer ApplicationContext.tool_cache.

    Returns:
        ToolCache instance
    """
    global _cache_instance

    if _cache_instance is None:
        # Try to use ApplicationContext first
        try:
            from mini_claude.context import get_context

            ctx = get_context()
            if ctx._tool_cache.is_initialized():
                _cache_instance = ctx.tool_cache
            else:
                from mini_claude.config.settings import settings

                _cache_instance = ToolCache(
                    ttl_seconds=settings.tool_cache_ttl_seconds,
                    max_size=settings.tool_cache_max_size,
                    cacheable_tools=settings.tool_cache_tools,
                )
                ctx.tool_cache = _cache_instance
        except ImportError:
            from mini_claude.config.settings import settings

            _cache_instance = ToolCache(
                ttl_seconds=settings.tool_cache_ttl_seconds,
                max_size=settings.tool_cache_max_size,
                cacheable_tools=settings.tool_cache_tools,
            )

    return _cache_instance


def reset_tool_cache() -> None:
    """Reset the global cache instance.

    Used for testing or when settings change.
    """
    global _cache_instance
    _cache_instance = None
    # Also reset in context
    try:
        from mini_claude.context import get_context

        ctx = get_context()
        ctx._tool_cache.reset()
    except ImportError:
        pass
