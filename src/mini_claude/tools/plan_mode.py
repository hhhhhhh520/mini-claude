"""exit_plan_mode 工具（收敛批次③C，对齐 Claude Code ExitPlanMode）。

plan 模式的收尾动作：模型整理好计划后调用本工具提交审批——
- 当前在 plan 模式：抛 PlanApprovalRequired → act 链转 WAITING_CONFIRMATION，
  用户回复 yes 后经 route_confirmation_key("plan") 切到 accept_edits，
  模型随即开始执行已批准的计划；回复 no 则模型留在 plan 模式修订计划
- 非 plan 模式：返回错误文本回流给 LLM 自纠

不是 MUTATING_TOOLS：plan 模式的只读闸不会拦它（这是唯一的出闸口）。
子代理白名单刻意不含它。
"""

from typing import Any, Dict

from .base import BaseTool, register_tool


class ExitPlanModeTool(BaseTool):
    @property
    def name(self) -> str:
        return "exit_plan_mode"

    @property
    def description(self) -> str:
        return (
            "Submit your finalized plan for user approval when in plan mode. "
            "The user will review it; on approval the session switches to "
            "execution. Do NOT call this unless you are in plan mode."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "plan": {
                    "type": "string",
                    "description": "The complete step-by-step plan for user review",
                }
            },
            "required": ["plan"],
        }

    async def execute(self, plan: str = "") -> str:
        if not plan.strip():
            return "Error: exit_plan_mode 需要 plan 参数（完整的分步计划）"

        from ..permissions.manager import PlanApprovalRequired, get_permission_manager
        from ..permissions.mode import PermissionMode

        manager = get_permission_manager()
        if manager.mode != PermissionMode.PLAN:
            return "Error: 当前不在 plan 模式，无需提交计划审批"

        raise PlanApprovalRequired(plan.strip())


register_tool(ExitPlanModeTool())
