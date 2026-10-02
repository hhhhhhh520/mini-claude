"""确认键统一路由（P3）。

pending_confirmation_path 现在有四种形态：
- 普通路径                    → approve_path（原有逻辑）
- mcp:<server>:<tool>        → MCP 工具会话放行（P2）
- perm:<tool>:<arg>          → 权限 ask 会话放行（P3）
- plan                       → plan 模式审批通过（收敛批次③C）：切到
  accept_edits 模式，模型随即开始执行已批准的计划

REPL 的 'yes' 分支只调 route_confirmation_key()，前缀分发收敛在这一个函数。
"""


def route_confirmation_key(key: str) -> bool:
    """处理以约定前缀开头的确认键；返回 True 表示已处理（勿再走 approve_path）。"""
    if key.startswith("mcp:"):
        from ..mcp.manager import approve_confirmation_key

        return approve_confirmation_key(key)
    if key.startswith("perm:"):
        rest = key[len("perm:") :]
        if ":" in rest:
            tool, arg = rest.split(":", 1)
        else:
            tool, arg = rest, ""
        from ..permissions.manager import get_permission_manager

        get_permission_manager().approve_session(tool, arg)
        return True
    if key == "plan":
        from ..permissions.manager import get_permission_manager
        from ..permissions.mode import PermissionMode

        get_permission_manager().set_mode(PermissionMode.ACCEPT_EDITS)
        return True
    return False
