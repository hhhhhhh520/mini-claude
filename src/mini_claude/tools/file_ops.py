"""File operation tools."""

import os
import glob as glob_module
from typing import Dict, Any, List, Optional
from pathlib import Path

from .base import BaseTool, register_tool
from ..utils.safety import SafetyChecker, truncate_content


class ReadFileTool(BaseTool):
    """Read file contents."""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file"

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


class WriteFileTool(BaseTool):
    """Write content to a file."""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file, creating it if it doesn't exist"

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

        try:
            # Create parent directories if needed
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return f"Successfully wrote {len(content)} characters to {path}"

        except Exception as e:
            return f"Error writing file: {e}"


class EditFileTool(BaseTool):
    """Edit a file by replacing text."""

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing old text with new text"

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

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()

            if old_text not in content:
                return f"Error: Text not found in file"

            new_content = content.replace(old_text, new_text, 1)

            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)

            return f"Successfully edited {path}"

        except Exception as e:
            return f"Error editing file: {e}"


class ListDirTool(BaseTool):
    """List directory contents."""

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List contents of a directory"

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
        return "Search for files matching a glob pattern"

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


# Import for type checking
from ..utils.safety import SafetyChecker
