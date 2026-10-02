"""系统提示词环境信息块（<env>）测试。

背景（2026-10-02 真机实测）：qwen3.8-flash 在 ask 模式猜 `/workspace`、用 cmd 里
不存在的 ls/pwd，10 轮预算全部烧在环境适应上，任务失败；同任务补 2 行环境说明后
一次通过。系统提示词必须自带环境事实：工作区根（沙箱）、OS、shell 习惯差异。

- env 块进 get_system_prompt（REPL 图路径与 ask 模式同源生效）
- 工作区根用 settings.workspace_root 实值；/add-dir 的额外根同步出现
- shell 提示按 os.name 分叉（Windows: cmd 无 ls/pwd；POSIX: sh 工具可用）
"""

import os

import pytest

from mini_claude.config.settings import ModelProvider
from mini_claude.llm.prompts import build_env_block, get_system_prompt


def test_env_block_contains_workspace_root():
    from mini_claude.utils.safety import get_workspace_roots

    env = build_env_block()
    # 沙箱规范根（resolve 归一化后的形态）必须出现在 env 块里
    assert get_workspace_roots()[0] in env
    assert "working_directory" in env


def test_env_block_contains_platform_and_shell():
    env = build_env_block()
    assert "platform:" in env
    assert "shell:" in env
    assert os.name.lower() in env.lower() or "Windows" in env or "Linux" in env


def test_env_block_windows_shell_hints():
    if os.name != "nt":
        pytest.skip("Windows shell 提示用例")
    env = build_env_block()
    assert "cmd" in env
    assert "dir" in env
    assert "没有 ls" in env, "必须明确警告 cmd 没有 ls/pwd"


def test_env_block_posix_shell_hints():
    if os.name == "nt":
        pytest.skip("POSIX shell 提示用例")
    env = build_env_block()
    assert "sh" in env


def test_env_block_sandbox_semantics():
    """环境块必须说明沙箱语义：相对路径基于工作区根，沙箱外默认受限。"""
    env = build_env_block()
    assert "沙箱" in env


def test_system_prompt_includes_env_block():
    """get_system_prompt 是 REPL 与 ask 的共同源头——env 必须在其中。"""
    from mini_claude.utils.safety import get_workspace_roots

    prompt = get_system_prompt(ModelProvider.CLAUDE)
    assert "working_directory" in prompt
    assert get_workspace_roots()[0] in prompt


def test_additional_roots_appear_in_env_block():
    from mini_claude.utils import safety

    extra = os.path.abspath(os.path.join(os.getcwd(), "tmp-extra-root-for-test"))
    os.makedirs(extra, exist_ok=True)
    ok, reason = safety.add_workspace_root(extra)
    assert ok, reason
    try:
        env = build_env_block()
        assert extra in env, "/add-dir 的额外根必须出现在环境块里"
    finally:
        safety.reset_workspace_roots()


def test_ask_mode_gets_system_prompt_via_build_system_messages():
    """ask 模式改走 build_system_messages 后，第一条系统消息必须带环境块。"""
    from mini_claude.agent.nodes._shared import build_system_messages

    msgs = build_system_messages()
    assert msgs and msgs[0]["role"] == "system"
    assert "working_directory" in msgs[0]["content"]
