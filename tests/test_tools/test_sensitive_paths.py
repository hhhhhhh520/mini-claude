"""敏感路径守卫测试（2026-10-02 拍板：硬拒核心资产，放行模板变体）。

背景：路径沙箱只约束文件工具，run_command 命令通道可读沙箱外文件——
任务 B 实测中模型被拒后改道命令通道读到了沙箱外源码。拍板方案：密钥/凭据
类路径（.env*/.ssh/mcp-auth/id_rsa/*.pem/credentials）在命令检查层硬拒；
.env 的 example/sample/template/dist 模板变体放行（无密钥，合法读写）。

单点插在 validate_command（RunCommandTool 与 RunBackgroundTool 共用）。
"""

import pytest

from mini_claude.tools.bash import RunBackgroundTool, RunCommandTool
from mini_claude.utils.safety import validate_command


# ---------- 拒绝面：核心资产 ----------


@pytest.mark.parametrize(
    "command",
    [
        "type .env",
        "python -c \"print(open('.env').read())\"",
        "copy x.txt .env.local_backup",
        "dir C:\\Users\\me\\.ssh",
        "cat ~/.ssh/id_rsa",
        "type C:\\keys\\server.pem",
        "python -c \"import yaml; print(yaml.safe_load(open('.git-credentials')))\"",
        "dir C:\\Users\\me\\.mini-claude\\mcp-auth",
        "TYPE .ENV",
        "cat ~/.ssh/id_ed25519",
    ],
)
def test_sensitive_paths_denied(command):
    is_safe, reason = validate_command(command)
    assert not is_safe
    assert "敏感路径" in reason


@pytest.mark.asyncio
async def test_run_command_tool_reports_refusal():
    out = await RunCommandTool().execute("type .env")
    assert "Error" in out
    assert "敏感路径" in out


@pytest.mark.asyncio
async def test_run_background_tool_guarded():
    out = await RunBackgroundTool().execute("python -c \"open('.env')\"")
    assert "Error" in out
    assert "敏感路径" in out


# ---------- 放行面：模板变体与误伤防护 ----------


@pytest.mark.parametrize(
    "command",
    [
        # 只用白名单内命令（type/copy/dir 不在白名单，预存拒绝与本守卫无关）
        "cat .env.example",
        "echo environment",
        "python fizzbuzz.py",
        "git credential.helper",
    ],
)
def test_template_variants_and_benign_commands_allowed(command):
    is_safe, reason = validate_command(command)
    assert is_safe, f"误伤：{command} → {reason}"
