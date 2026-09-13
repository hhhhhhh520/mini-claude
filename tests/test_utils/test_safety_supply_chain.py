"""ISSUE-019：命令白名单三条安装/任意脚本通道。

已复现实锤（只读探针）：
- `python evil.py` / `pip install requests` / `python -m pip install evil-pkg` 全部 PASS。
修法（与既有约定对齐，无交互确认通道，"确认"=拒+confirmation 文案）：
1. `python`/`python3` 带目录成分的 `.py` 位置参数 → 工作区校验，区外拒；
   纯文件名放行（旧行为保留，`test_validate_safe_python` 不动）。
2. `pip install` / `pip3 install` / `pip -r/-e` → confirmation（与 uninstall 对称）。
3. `python -m pip install/...` → 同样 confirmation（`pip` 不在模块黑名单里）。
无害用法（`-V`/`--version`/`list`/`show`/`freeze`/`-m pytest`）必须原样放行。
"""
import os

from mini_claude.utils import safety
from mini_claude.utils.safety import validate_command


class TestWorkspaceOutsideScriptsBlocked:
    def test_absolute_outside_blocked(self):
        ok, reason = validate_command("python C:/Windows/Temp/evil-019.py")
        assert ok is False, f"工作区外绝对路径脚本必须拦，实测放行：{reason}"

    def test_python3_absolute_outside_blocked(self):
        ok, reason = validate_command("python3 C:/Windows/Temp/evil-019.py")
        assert ok is False

    def test_workspace_inside_allowed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(safety.settings, "workspace_root", str(tmp_path))
        script = os.path.join(str(tmp_path), "ok-019.py")
        ok, reason = validate_command(f"python {script}")
        assert ok is True, f"工作区内脚本必须放行：{reason}"

    def test_bare_filename_preserved(self):
        """纯文件名是旧行为（test_validate_safe_python），保留。"""
        ok, _ = validate_command("python script.py")
        assert ok is True

    def test_traversal_still_blocked(self):
        ok, _ = validate_command("python ../evil-019.py")
        assert ok is False

    def test_version_flags_preserved(self):
        assert validate_command("python -V")[0] is True
        assert validate_command("python --version")[0] is True

    def test_m_module_preserved(self):
        """黑名单外的 -m 模块不受影响。"""
        assert validate_command("python -m pytest")[0] is True


class TestPipInstallChannels:
    def test_pip_install_requires_confirmation(self):
        ok, reason = validate_command("pip install requests")
        assert ok is False, "pip install 必须进确认，实测放行"
        assert "confirmation" in reason.lower()

    def test_pip3_install_requires_confirmation(self):
        ok, reason = validate_command("pip3 install evil-pkg")
        assert ok is False
        assert "confirmation" in reason.lower()

    def test_m_pip_install_blocked(self):
        ok, reason = validate_command("python -m pip install evil-pkg")
        assert ok is False, f"python -m pip install 是第三条通道，必须拦：{reason}"

    def test_m_pip_list_preserved(self):
        assert validate_command("python -m pip list")[0] is True

    def test_pip_readonly_preserved(self):
        """只读用法召回守卫。"""
        assert validate_command("pip list")[0] is True
        assert validate_command("pip show requests")[0] is True
        assert validate_command("pip freeze")[0] is True

    def test_pip_uninstall_still_confirmation(self):
        """既有行为守卫。"""
        ok, reason = validate_command("pip uninstall package")
        assert ok is False
