"""Tests for file operation tools."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from mini_claude.tools.file_ops import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ListDirTool,
    SearchFilesTool,
    SearchContentTool,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def mock_workspace(temp_dir):
    """Mock the workspace root to the temp directory."""
    with patch('mini_claude.utils.safety.settings.workspace_root', temp_dir):
        yield temp_dir


@pytest.mark.asyncio
async def test_write_and_read_file(temp_dir, mock_workspace):
    """Test writing and reading a file."""
    write_tool = WriteFileTool()
    read_tool = ReadFileTool()

    filepath = os.path.join(temp_dir, "test.txt")
    content = "Hello, World!"

    # Write file
    result = await write_tool.execute(path=filepath, content=content)
    assert "Successfully wrote" in result

    # Read file
    result = await read_tool.execute(path=filepath)
    assert result == content


@pytest.mark.asyncio
async def test_edit_file(temp_dir, mock_workspace):
    """Test editing a file."""
    write_tool = WriteFileTool()
    edit_tool = EditFileTool()

    filepath = os.path.join(temp_dir, "edit_test.txt")
    await write_tool.execute(path=filepath, content="Hello World")

    result = await edit_tool.execute(
        path=filepath,
        old_text="World",
        new_text="Claude"
    )
    assert "Successfully edited" in result


@pytest.mark.asyncio
async def test_list_dir(temp_dir, mock_workspace):
    """Test listing directory contents."""
    tool = ListDirTool()

    # Create some files
    Path(temp_dir, "file1.txt").touch()
    Path(temp_dir, "file2.py").touch()
    os.makedirs(Path(temp_dir, "subdir"))

    result = await tool.execute(path=temp_dir)
    assert "file1.txt" in result
    assert "file2.py" in result
    assert "subdir" in result


@pytest.mark.asyncio
async def test_search_files(temp_dir, mock_workspace):
    """Test searching for files."""
    tool = SearchFilesTool()

    # Create some files
    Path(temp_dir, "test.py").touch()
    Path(temp_dir, "main.py").touch()
    Path(temp_dir, "readme.md").touch()

    result = await tool.execute(pattern="*.py", path=temp_dir)
    assert "test.py" in result
    assert "main.py" in result
    assert "readme.md" not in result


@pytest.mark.asyncio
async def test_search_content(temp_dir, mock_workspace):
    """Test searching content in files."""
    write_tool = WriteFileTool()
    search_tool = SearchContentTool()

    # Create files with content
    await write_tool.execute(
        path=os.path.join(temp_dir, "file1.txt"),
        content="This has TODO: implement feature"
    )
    await write_tool.execute(
        path=os.path.join(temp_dir, "file2.txt"),
        content="No todos here"
    )

    result = await search_tool.execute(query="TODO", path=temp_dir)
    assert "file1.txt" in result
    assert "TODO" in result
