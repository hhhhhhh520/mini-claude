"""File operation tools with file locking for parallel agent support."""

import os
import glob as glob_module
from typing import Dict, Any, List, Optional

from .base import BaseTool, register_tool
from ..utils.safety import SafetyChecker, truncate_content
from ..utils.file_lock import file_lock_manager


# Current agent ID (set by agent context)
_current_agent_id: str = "main"


def set_current_agent(agent_id: str) -> None:
    """Set the current agent ID for lock ownership."""
    global _current_agent_id
    _current_agent_id = agent_id


def get_current_agent() -> str:
    """Get the current agent ID."""
    return _current_agent_id


class ReadFileTool(BaseTool):
    """Read file contents."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "[PREFERRED] Read the contents of a file. Use this tool instead of shell commands like 'cat'. Supports optional line range."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Starting line number (optional)",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Ending line number (optional)",
                },
            },
            "required": ["path"],
        }

    async def execute(self, path: str, start_line: int = None, end_line: int = None) -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_file_read(path)
        if not is_valid:
            return f"Error: {reason}"

        # Acquire read lock
        agent_id = get_current_agent()
        success, lock_msg = await file_lock_manager.acquire_lock(path, agent_id, "read")
        if not success:
            return f"Error: {lock_msg}"

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if start_line is not None:
                lines = lines[start_line - 1:]
            if end_line is not None:
                lines = lines[:end_line - (start_line or 1) + 1]

            content = "".join(lines)
            return truncate_content(content)

        except Exception as e:
            return f"Error reading file: {e}"
        finally:
            await file_lock_manager.release_lock(path, agent_id)


class WriteFileTool(BaseTool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "[PREFERRED] Create or overwrite a file with content. Use this tool instead of shell commands like 'echo > file' or 'cat > file'. Automatically creates parent directories."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_file_write(path)
        if not is_valid:
            return f"Error: {reason}"

        # Acquire write lock
        agent_id = get_current_agent()
        success, lock_msg = await file_lock_manager.acquire_lock(path, agent_id, "write")
        if not success:
            return f"Error: {lock_msg}"

        # Check for conflicts (file modified since lock acquired)
        has_conflict, conflict_details = await file_lock_manager.check_conflict(path, agent_id)
        if has_conflict:
            await file_lock_manager.release_lock(path, agent_id)
            return f"Error: Conflict detected - {conflict_details}\nUse 'force_write' to overwrite."

        try:
            # Create parent directories if needed
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            # Update version tracking
            await file_lock_manager.update_version(path, agent_id)

            return f"Successfully wrote {len(content)} characters to {path}"

        except Exception as e:
            return f"Error writing file: {e}"
        finally:
            await file_lock_manager.release_lock(path, agent_id)


class EditFileTool(BaseTool):
    """Edit a file by replacing text."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "[PREFERRED] Edit a file by replacing specific text. Use this tool instead of sed or other shell commands. Finds old_text and replaces with new_text."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit",
                },
                "old_text": {
                    "type": "string",
                    "description": "Text to find and replace",
                },
                "new_text": {
                    "type": "string",
                    "description": "Text to replace with",
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    async def execute(self, path: str, old_text: str, new_text: str) -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_file_read(path)
        if not is_valid:
            return f"Error: {reason}"

        # Acquire write lock
        agent_id = get_current_agent()
        success, lock_msg = await file_lock_manager.acquire_lock(path, agent_id, "write")
        if not success:
            return f"Error: {lock_msg}"

        # Check for conflicts
        has_conflict, conflict_details = await file_lock_manager.check_conflict(path, agent_id)
        if has_conflict:
            await file_lock_manager.release_lock(path, agent_id)
            return f"Error: Conflict detected - {conflict_details}\nUse 'force_edit' to force apply."

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return f"Error: Text not found in file"

            new_content = content.replace(old_text, new_text, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Update version tracking
            await file_lock_manager.update_version(path, agent_id)

            return f"Successfully edited {path}"

        except Exception as e:
            return f"Error editing file: {e}"
        finally:
            await file_lock_manager.release_lock(path, agent_id)


class ListDirTool(BaseTool):
    """List directory contents."""

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "[PREFERRED] List contents of a directory. Use this tool instead of shell commands like 'ls' or 'dir'."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the directory (default: current directory)",
                },
            },
            "required": [],
        }

    async def execute(self, path: str = ".") -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_path(path)
        if not is_valid:
            return f"Error: {reason}"

        try:
            entries = []
            for entry in sorted(os.listdir(path)):
                full_path = os.path.join(path, entry)
                if os.path.isdir(full_path):
                    entries.append(f"[DIR] {entry}/")
                else:
                    size = os.path.getsize(full_path)
                    entries.append(f"[FILE] {entry} ({size} bytes)")

            return "\n".join(entries) or "Empty directory"

        except Exception as e:
            return f"Error listing directory: {e}"


class SearchFilesTool(BaseTool):
    """Search for files by pattern."""

    @property
    def name(self) -> str:
        return "search_files"

    @property
    def description(self) -> str:
        return "[PREFERRED] Search for files matching a glob pattern. Use this instead of shell 'find' command. Example: '**/*.py' finds all Python files."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to search for (e.g., '**/*.py')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from",
                },
            },
            "required": ["pattern"],
        }

    async def execute(self, pattern: str, path: str = ".") -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_path(path)
        if not is_valid:
            return f"Error: {reason}"

        try:
            matches = glob_module.glob(pattern, recursive=True, root_dir=path)
            if not matches:
                return f"No files found matching: {pattern}"

            return "\n".join(sorted(matches))

        except Exception as e:
            return f"Error searching files: {e}"


class SearchContentTool(BaseTool):
    """Search for content in files."""

    @property
    def name(self) -> str:
        return "search_content"

    @property
    def description(self) -> str:
        return "Search for text content in files"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search for",
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern for files to search (e.g., '*.py')",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from",
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, pattern: str = "*", path: str = ".") -> str:
        import re
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_path(path)
        if not is_valid:
            return f"Error: {reason}"

        try:
            results = []
            files = glob_module.glob(pattern, recursive=True, root_dir=path)

            for file_path in files:
                full_path = os.path.join(path, file_path)
                if os.path.isdir(full_path):
                    continue

                is_valid, _ = checker.check_file_read(full_path)
                if not is_valid:
                    continue

                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            if query.lower() in line.lower():
                                results.append(f"{file_path}:{i}: {line.strip()}")
                                if len(results) > 50:  # Limit results
                                    return "\n".join(results) + "\n... [truncated]"
                except Exception:
                    continue

            return "\n".join(results) or f"No matches found for: {query}"

        except Exception as e:
            return f"Error searching content: {e}"


# Register all file tools
register_tool(ReadFileTool())
register_tool(WriteFileTool())
register_tool(EditFileTool())
register_tool(ListDirTool())
register_tool(SearchFilesTool())
register_tool(SearchContentTool())


class ListLocksTool(BaseTool):
    """List all active file locks."""

    @property
    def name(self) -> str:
        return "list_locks"

    @property
    def description(self) -> str:
        return "List all active file locks in the workspace"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        locks = file_lock_manager.get_all_locks()

        if not locks:
            return "No active file locks"

        lines = ["Active file locks:"]
        for path, info in locks.items():
            lines.append(f"  {path}")
            lines.append(f"    Agent: {info['agent_id']}")
            lines.append(f"    Type: {info['lock_type']}")
            lines.append(f"    Since: {info['locked_at']}")

        return "\n".join(lines)


class ForceWriteTool(BaseTool):
    """Force write to a file, ignoring conflicts."""

    @property
    def name(self) -> str:
        return "force_write"

    @property
    def description(self) -> str:
        return "Force write to a file, overwriting any changes (use with caution)"

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file",
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, path: str, content: str) -> str:
        from mini_claude.config.settings import settings

        # Resolve relative path to workspace
        if not os.path.isabs(path):
            path = os.path.join(settings.workspace_root, path)

        checker = SafetyChecker()
        is_valid, reason = checker.check_file_write(path)
        if not is_valid:
            return f"Error: {reason}"

        agent_id = get_current_agent()

        # Force acquire lock (release any existing lock)
        if file_lock_manager.get_lock_info(path):
            await file_lock_manager.release_lock(path, agent_id)

        await file_lock_manager.acquire_lock(path, agent_id, "write")

        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            await file_lock_manager.update_version(path, agent_id)

            return f"Force wrote {len(content)} characters to {path}"

        except Exception as e:
            return f"Error force writing file: {e}"
        finally:
            await file_lock_manager.release_lock(path, agent_id)


# Register lock management tools
register_tool(ListLocksTool())
register_tool(ForceWriteTool())


# Import for type checking
from ..utils.safety import SafetyChecker
