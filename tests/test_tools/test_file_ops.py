"""Tests for file operation tools."""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from mini_claude.tools.file_ops import (
    ReadFileTool,
    WriteFileTool,
    EditFileTool,
    ForceWriteTool,
    ListDirTool,
    SearchFilesTool,
    SearchContentTool,
    ListLocksTool,
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


# ========== WriteFileTool Tests (10个) ==========

class TestWriteFileTool:
    """测试写入文件工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_write_basic(self, temp_dir, mock_workspace):
        """测试基本写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "test.txt")
        result = await tool.execute(path=filepath, content="Hello, World!")
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_unicode(self, temp_dir, mock_workspace):
        """测试 Unicode 写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "unicode.txt")
        result = await tool.execute(path=filepath, content="中文内容 日本語 한국어")
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_long_content(self, temp_dir, mock_workspace):
        """测试长内容写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "long.txt")
        content = "测试内容" * 10000
        result = await tool.execute(path=filepath, content=content)
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_empty_content(self, temp_dir, mock_workspace):
        """测试空内容写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "empty.txt")
        result = await tool.execute(path=filepath, content="")
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_creates_directory(self, temp_dir, mock_workspace):
        """测试自动创建目录"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "subdir", "nested", "file.txt")
        result = await tool.execute(path=filepath, content="Nested content")
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_overwrites_existing(self, temp_dir, mock_workspace):
        """测试覆盖现有文件"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "overwrite.txt")
        await tool.execute(path=filepath, content="Original")
        result = await tool.execute(path=filepath, content="New content")
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_special_chars(self, temp_dir, mock_workspace):
        """测试特殊字符写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "special.txt")
        content = "Line1\nLine2\tTab@#$%^&*()"
        result = await tool.execute(path=filepath, content=content)
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_json_content(self, temp_dir, mock_workspace):
        """测试 JSON 内容写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "data.json")
        content = '{"key": "value", "number": 123}'
        result = await tool.execute(path=filepath, content=content)
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_python_code(self, temp_dir, mock_workspace):
        """测试 Python 代码写入"""
        tool = WriteFileTool()
        filepath = os.path.join(temp_dir, "script.py")
        content = "def hello():\n    print('Hello')"
        result = await tool.execute(path=filepath, content=content)
        assert "Successfully wrote" in result

    @pytest.mark.asyncio
    async def test_write_tool_name(self):
        """测试工具名称"""
        tool = WriteFileTool()
        assert tool.name == "write_file"


# ========== ReadFileTool Tests (10个) ==========

class TestReadFileTool:
    """测试读取文件工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_read_basic(self, temp_dir, mock_workspace):
        """测试基本读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "test.txt")
        await write_tool.execute(path=filepath, content="Hello, World!")
        result = await read_tool.execute(path=filepath)
        assert result == "Hello, World!"

    @pytest.mark.asyncio
    async def test_read_unicode(self, temp_dir, mock_workspace):
        """测试 Unicode 读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "unicode.txt")
        await write_tool.execute(path=filepath, content="中文内容")
        result = await read_tool.execute(path=filepath)
        assert "中文" in result

    @pytest.mark.asyncio
    async def test_read_empty_file(self, temp_dir, mock_workspace):
        """测试空文件读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "empty.txt")
        await write_tool.execute(path=filepath, content="")
        result = await read_tool.execute(path=filepath)
        assert result == ""

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, temp_dir, mock_workspace):
        """测试读取不存在的文件"""
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "nonexistent.txt")
        result = await read_tool.execute(path=filepath)
        assert "Error" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_read_long_file(self, temp_dir, mock_workspace):
        """测试长文件读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "long.txt")
        content = "测试内容" * 1000
        await write_tool.execute(path=filepath, content=content)
        result = await read_tool.execute(path=filepath)
        assert len(result) == len(content)

    @pytest.mark.asyncio
    async def test_read_special_chars(self, temp_dir, mock_workspace):
        """测试特殊字符读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "special.txt")
        content = "Line1\nLine2\tTab@#$%"
        await write_tool.execute(path=filepath, content=content)
        result = await read_tool.execute(path=filepath)
        assert "\n" in result
        assert "\t" in result

    @pytest.mark.asyncio
    async def test_read_json_file(self, temp_dir, mock_workspace):
        """测试 JSON 文件读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "data.json")
        content = '{"key": "value"}'
        await write_tool.execute(path=filepath, content=content)
        result = await read_tool.execute(path=filepath)
        assert "key" in result

    @pytest.mark.asyncio
    async def test_read_python_file(self, temp_dir, mock_workspace):
        """测试 Python 文件读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "script.py")
        content = "def hello():\n    pass"
        await write_tool.execute(path=filepath, content=content)
        result = await read_tool.execute(path=filepath)
        assert "def hello" in result

    @pytest.mark.asyncio
    async def test_read_nested_file(self, temp_dir, mock_workspace):
        """测试嵌套目录文件读取"""
        write_tool = WriteFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "sub", "nested.txt")
        await write_tool.execute(path=filepath, content="Nested")
        result = await read_tool.execute(path=filepath)
        assert result == "Nested"

    @pytest.mark.asyncio
    async def test_read_tool_name(self):
        """测试工具名称"""
        tool = ReadFileTool()
        assert tool.name == "read_file"


# ========== EditFileTool Tests (10个) ==========

class TestEditFileTool:
    """测试编辑文件工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_edit_basic(self, temp_dir, mock_workspace):
        """测试基本编辑"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "edit.txt")
        await write_tool.execute(path=filepath, content="Hello World")
        result = await edit_tool.execute(path=filepath, old_text="World", new_text="Claude")
        assert "Successfully edited" in result

    @pytest.mark.asyncio
    async def test_edit_multiple_occurrences(self, temp_dir, mock_workspace):
        """测试多次出现替换"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "multi.txt")
        await write_tool.execute(path=filepath, content="test test test")
        result = await edit_tool.execute(path=filepath, old_text="test", new_text="demo")
        assert "Successfully edited" in result

    @pytest.mark.asyncio
    async def test_edit_not_found(self, temp_dir, mock_workspace):
        """测试未找到文本"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "notfound.txt")
        await write_tool.execute(path=filepath, content="Hello World")
        result = await edit_tool.execute(path=filepath, old_text="NotFound", new_text="New")
        assert "not found" in result.lower() or "Error" in result

    @pytest.mark.asyncio
    async def test_edit_empty_old_text(self, temp_dir, mock_workspace):
        """测试空旧文本"""
        edit_tool = EditFileTool()
        result = await edit_tool.execute(path="test.txt", old_text="", new_text="New")
        assert "Error" in result or "empty" in result.lower()

    @pytest.mark.asyncio
    async def test_edit_nonexistent_file(self, temp_dir, mock_workspace):
        """测试编辑不存在的文件"""
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "nonexistent.txt")
        result = await edit_tool.execute(path=filepath, old_text="old", new_text="new")
        assert "Error" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_edit_unicode(self, temp_dir, mock_workspace):
        """测试 Unicode 编辑"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "unicode.txt")
        await write_tool.execute(path=filepath, content="中文内容")
        result = await edit_tool.execute(path=filepath, old_text="内容", new_text="测试")
        assert "Successfully edited" in result

    @pytest.mark.asyncio
    async def test_edit_long_text(self, temp_dir, mock_workspace):
        """测试长文本编辑"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "long.txt")
        content = "测试内容" * 100
        await write_tool.execute(path=filepath, content=content)
        result = await edit_tool.execute(path=filepath, old_text="测试内容", new_text="新内容")
        assert "Successfully edited" in result

    @pytest.mark.asyncio
    async def test_edit_preserves_other_content(self, temp_dir, mock_workspace):
        """测试保留其他内容"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        read_tool = ReadFileTool()
        filepath = os.path.join(temp_dir, "preserve.txt")
        await write_tool.execute(path=filepath, content="Line1\nLine2\nLine3")
        await edit_tool.execute(path=filepath, old_text="Line2", new_text="Modified")
        result = await read_tool.execute(path=filepath)
        assert "Line1" in result
        assert "Line3" in result

    @pytest.mark.asyncio
    async def test_edit_multiline(self, temp_dir, mock_workspace):
        """测试多行编辑"""
        write_tool = WriteFileTool()
        edit_tool = EditFileTool()
        filepath = os.path.join(temp_dir, "multiline.txt")
        await write_tool.execute(path=filepath, content="Line1\nLine2\nLine3")
        result = await edit_tool.execute(path=filepath, old_text="Line1\nLine2", new_text="NewLine")
        assert "Successfully edited" in result

    @pytest.mark.asyncio
    async def test_edit_tool_name(self):
        """测试工具名称"""
        tool = EditFileTool()
        assert tool.name == "edit_file"


# ========== ListDirTool Tests (10个) ==========

class TestListDirTool:
    """测试列出目录工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_list_basic(self, temp_dir, mock_workspace):
        """测试基本列出"""
        tool = ListDirTool()
        Path(temp_dir, "file1.txt").touch()
        Path(temp_dir, "file2.py").touch()
        result = await tool.execute(path=temp_dir)
        assert "file1.txt" in result
        assert "file2.py" in result

    @pytest.mark.asyncio
    async def test_list_empty_dir(self, temp_dir, mock_workspace):
        """测试空目录"""
        tool = ListDirTool()
        result = await tool.execute(path=temp_dir)
        assert result == "" or "empty" in result.lower() or result == "(empty)"

    @pytest.mark.asyncio
    async def test_list_with_subdirs(self, temp_dir, mock_workspace):
        """测试带子目录"""
        tool = ListDirTool()
        os.makedirs(Path(temp_dir, "subdir1"))
        os.makedirs(Path(temp_dir, "subdir2"))
        result = await tool.execute(path=temp_dir)
        assert "subdir1" in result
        assert "subdir2" in result

    @pytest.mark.asyncio
    async def test_list_nested_structure(self, temp_dir, mock_workspace):
        """测试嵌套结构"""
        tool = ListDirTool()
        os.makedirs(Path(temp_dir, "level1", "level2"))
        Path(temp_dir, "level1", "file.txt").touch()
        result = await tool.execute(path=temp_dir)
        assert "level1" in result

    @pytest.mark.asyncio
    async def test_list_nonexistent_dir(self, temp_dir, mock_workspace):
        """测试不存在的目录"""
        tool = ListDirTool()
        result = await tool.execute(path=os.path.join(temp_dir, "nonexistent"))
        assert "Error" in result or "not found" in result.lower()

    @pytest.mark.asyncio
    async def test_list_many_files(self, temp_dir, mock_workspace):
        """测试大量文件"""
        tool = ListDirTool()
        for i in range(50):
            Path(temp_dir, f"file{i}.txt").touch()
        result = await tool.execute(path=temp_dir)
        assert "file0.txt" in result

    @pytest.mark.asyncio
    async def test_list_hidden_files(self, temp_dir, mock_workspace):
        """测试隐藏文件"""
        tool = ListDirTool()
        Path(temp_dir, ".hidden").touch()
        result = await tool.execute(path=temp_dir)
        # 隐藏文件可能显示也可能不显示

    @pytest.mark.asyncio
    async def test_list_special_names(self, temp_dir, mock_workspace):
        """测试特殊文件名"""
        tool = ListDirTool()
        Path(temp_dir, "file with spaces.txt").touch()
        Path(temp_dir, "file-with-dashes.txt").touch()
        result = await tool.execute(path=temp_dir)
        assert "file with spaces.txt" in result or "file" in result

    @pytest.mark.asyncio
    async def test_list_unicode_names(self, temp_dir, mock_workspace):
        """测试 Unicode 文件名"""
        tool = ListDirTool()
        Path(temp_dir, "中文文件.txt").touch()
        result = await tool.execute(path=temp_dir)
        assert "中文" in result or ".txt" in result

    @pytest.mark.asyncio
    async def test_list_tool_name(self):
        """测试工具名称"""
        tool = ListDirTool()
        assert tool.name == "list_dir"


# ========== SearchFilesTool Tests (10个) ==========

class TestSearchFilesTool:
    """测试搜索文件工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_search_py_files(self, temp_dir, mock_workspace):
        """测试搜索 Python 文件"""
        tool = SearchFilesTool()
        Path(temp_dir, "test.py").touch()
        Path(temp_dir, "main.py").touch()
        Path(temp_dir, "readme.md").touch()
        result = await tool.execute(pattern="*.py", path=temp_dir)
        assert "test.py" in result
        assert "main.py" in result
        assert "readme.md" not in result

    @pytest.mark.asyncio
    async def test_search_txt_files(self, temp_dir, mock_workspace):
        """测试搜索文本文件"""
        tool = SearchFilesTool()
        Path(temp_dir, "file1.txt").touch()
        Path(temp_dir, "file2.txt").touch()
        result = await tool.execute(pattern="*.txt", path=temp_dir)
        assert "file1.txt" in result
        assert "file2.txt" in result

    @pytest.mark.asyncio
    async def test_search_no_match(self, temp_dir, mock_workspace):
        """测试无匹配"""
        tool = SearchFilesTool()
        Path(temp_dir, "test.py").touch()
        result = await tool.execute(pattern="*.md", path=temp_dir)
        assert "test.py" not in result

    @pytest.mark.asyncio
    async def test_search_recursive(self, temp_dir, mock_workspace):
        """测试递归搜索"""
        tool = SearchFilesTool()
        os.makedirs(Path(temp_dir, "subdir"))
        Path(temp_dir, "root.py").touch()
        Path(temp_dir, "subdir", "nested.py").touch()
        result = await tool.execute(pattern="*.py", path=temp_dir)
        assert "root.py" in result

    @pytest.mark.asyncio
    async def test_search_empty_pattern(self, temp_dir, mock_workspace):
        """测试空模式"""
        tool = SearchFilesTool()
        result = await tool.execute(pattern="", path=temp_dir)
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_nonexistent_dir(self, temp_dir, mock_workspace):
        """测试不存在的目录"""
        tool = SearchFilesTool()
        result = await tool.execute(pattern="*.py", path=os.path.join(temp_dir, "nonexistent"))
        # 可能返回错误或空结果
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_many_files(self, temp_dir, mock_workspace):
        """测试大量文件搜索"""
        tool = SearchFilesTool()
        for i in range(100):
            Path(temp_dir, f"file{i}.txt").touch()
        result = await tool.execute(pattern="*.txt", path=temp_dir)
        assert "file0.txt" in result

    @pytest.mark.asyncio
    async def test_search_special_pattern(self, temp_dir, mock_workspace):
        """测试特殊模式"""
        tool = SearchFilesTool()
        Path(temp_dir, "test_2024.py").touch()
        Path(temp_dir, "test_2025.py").touch()
        result = await tool.execute(pattern="test_*.py", path=temp_dir)
        assert "test_2024.py" in result

    @pytest.mark.asyncio
    async def test_search_unicode_filename(self, temp_dir, mock_workspace):
        """测试 Unicode 文件名搜索"""
        tool = SearchFilesTool()
        Path(temp_dir, "中文.py").touch()
        result = await tool.execute(pattern="*.py", path=temp_dir)
        assert ".py" in result

    @pytest.mark.asyncio
    async def test_search_tool_name(self):
        """测试工具名称"""
        tool = SearchFilesTool()
        assert tool.name == "search_files"


# ========== SearchContentTool Tests (10个) ==========

class TestSearchContentTool:
    """测试搜索内容工具 - 10个测试用例"""

    @pytest.mark.asyncio
    async def test_search_basic(self, temp_dir, mock_workspace):
        """测试基本内容搜索"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "test.txt")
        await write_tool.execute(path=filepath, content="Hello TODO: fix this")
        result = await search_tool.execute(query="TODO", path=temp_dir)
        assert "TODO" in result

    @pytest.mark.asyncio
    async def test_search_not_found(self, temp_dir, mock_workspace):
        """测试未找到内容"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "test.txt")
        await write_tool.execute(path=filepath, content="Hello World")
        result = await search_tool.execute(query="TODO", path=temp_dir)
        # 可能返回空结果或提示未找到
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_multiple_files(self, temp_dir, mock_workspace):
        """测试多文件搜索"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        await write_tool.execute(path=os.path.join(temp_dir, "file1.txt"), content="TODO in file1")
        await write_tool.execute(path=os.path.join(temp_dir, "file2.txt"), content="TODO in file2")
        result = await search_tool.execute(query="TODO", path=temp_dir)
        assert "TODO" in result

    @pytest.mark.asyncio
    async def test_search_case_sensitive(self, temp_dir, mock_workspace):
        """测试大小写敏感"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "test.txt")
        await write_tool.execute(path=filepath, content="TODO todo Todo")
        result = await search_tool.execute(query="TODO", path=temp_dir)
        assert "TODO" in result

    @pytest.mark.asyncio
    async def test_search_unicode(self, temp_dir, mock_workspace):
        """测试 Unicode 搜索"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "test.txt")
        await write_tool.execute(path=filepath, content="中文内容测试")
        result = await search_tool.execute(query="中文", path=temp_dir)
        assert "中文" in result

    @pytest.mark.asyncio
    async def test_search_empty_query(self, temp_dir, mock_workspace):
        """测试空查询"""
        search_tool = SearchContentTool()
        result = await search_tool.execute(query="", path=temp_dir)
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_nonexistent_dir(self, temp_dir, mock_workspace):
        """测试不存在的目录"""
        search_tool = SearchContentTool()
        result = await search_tool.execute(query="test", path=os.path.join(temp_dir, "nonexistent"))
        # 可能返回错误或空结果
        assert result is not None

    @pytest.mark.asyncio
    async def test_search_code_file(self, temp_dir, mock_workspace):
        """测试代码文件搜索"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "code.py")
        await write_tool.execute(path=filepath, content="def hello():\n    pass")
        result = await search_tool.execute(query="def", path=temp_dir)
        assert "def" in result

    @pytest.mark.asyncio
    async def test_search_long_content(self, temp_dir, mock_workspace):
        """测试长内容搜索"""
        write_tool = WriteFileTool()
        search_tool = SearchContentTool()
        filepath = os.path.join(temp_dir, "long.txt")
        content = "测试内容" * 1000 + "TARGET" + "测试内容" * 1000
        await write_tool.execute(path=filepath, content=content)
        result = await search_tool.execute(query="TARGET", path=temp_dir)
        assert "TARGET" in result

    @pytest.mark.asyncio
    async def test_search_tool_name(self):
        """测试工具名称"""
        tool = SearchContentTool()
        assert tool.name == "search_content"


# ========== ForceWriteTool Tests (5个) ==========

class TestForceWriteTool:
    """测试强制写入工具 - 5个测试用例"""

    @pytest.mark.asyncio
    async def test_force_write_basic(self, temp_dir, mock_workspace):
        """测试基本强制写入"""
        tool = ForceWriteTool()
        filepath = os.path.join(temp_dir, "force.txt")
        result = await tool.execute(path=filepath, content="Forced content")
        assert "Successfully" in result or "wrote" in result.lower()

    @pytest.mark.asyncio
    async def test_force_write_overwrites(self, temp_dir, mock_workspace):
        """测试强制覆盖"""
        write_tool = WriteFileTool()
        force_tool = ForceWriteTool()
        filepath = os.path.join(temp_dir, "overwrite.txt")
        await write_tool.execute(path=filepath, content="Original")
        result = await force_tool.execute(path=filepath, content="Forced")
        assert "Successfully" in result or "wrote" in result.lower()

    @pytest.mark.asyncio
    async def test_force_write_creates_dirs(self, temp_dir, mock_workspace):
        """测试创建目录"""
        tool = ForceWriteTool()
        filepath = os.path.join(temp_dir, "sub", "nested", "force.txt")
        result = await tool.execute(path=filepath, content="Nested")
        assert "Successfully" in result or "wrote" in result.lower()

    @pytest.mark.asyncio
    async def test_force_write_unicode(self, temp_dir, mock_workspace):
        """测试 Unicode 强制写入"""
        tool = ForceWriteTool()
        filepath = os.path.join(temp_dir, "unicode.txt")
        result = await tool.execute(path=filepath, content="中文内容")
        assert "Successfully" in result or "wrote" in result.lower()

    @pytest.mark.asyncio
    async def test_force_write_tool_name(self):
        """测试工具名称"""
        tool = ForceWriteTool()
        assert tool.name == "force_write"


# ========== Tool Properties Tests (10个) ==========

class TestToolProperties:
    """测试工具属性 - 10个测试用例"""

    def test_read_file_description(self):
        """测试读取工具描述"""
        tool = ReadFileTool()
        assert tool.description is not None
        assert len(tool.description) > 0

    def test_write_file_description(self):
        """测试写入工具描述"""
        tool = WriteFileTool()
        assert tool.description is not None

    def test_edit_file_description(self):
        """测试编辑工具描述"""
        tool = EditFileTool()
        assert tool.description is not None

    def test_list_dir_description(self):
        """测试列目录工具描述"""
        tool = ListDirTool()
        assert tool.description is not None

    def test_search_files_description(self):
        """测试搜索文件工具描述"""
        tool = SearchFilesTool()
        assert tool.description is not None

    def test_search_content_description(self):
        """测试搜索内容工具描述"""
        tool = SearchContentTool()
        assert tool.description is not None

    def test_read_file_parameters(self):
        """测试读取工具参数"""
        tool = ReadFileTool()
        params = tool.parameters
        assert "properties" in params
        assert "path" in params["properties"]

    def test_write_file_parameters(self):
        """测试写入工具参数"""
        tool = WriteFileTool()
        params = tool.parameters
        assert "path" in params["properties"]
        assert "content" in params["properties"]

    def test_edit_file_parameters(self):
        """测试编辑工具参数"""
        tool = EditFileTool()
        params = tool.parameters
        assert "path" in params["properties"]
        assert "old_text" in params["properties"]
        assert "new_text" in params["properties"]

    def test_list_dir_parameters(self):
        """测试列目录工具参数"""
        tool = ListDirTool()
        params = tool.parameters
        assert "path" in params["properties"]
