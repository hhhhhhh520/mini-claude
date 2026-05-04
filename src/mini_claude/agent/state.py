"""Agent state definition - Refactored version."""

from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage
from enum import Enum
from operator import add
from dataclasses import dataclass, field, asdict
from datetime import datetime


class StopReason(Enum):
    """停止原因枚举 - 统一控制流判断"""
    CONTINUE = "continue"              # 继续执行
    TASK_COMPLETE = "task_complete"    # 任务完成
    MAX_ITERATIONS = "max_iterations"  # 达到迭代上限
    ERROR = "error"                    # 发生错误
    IDLE_LOOP = "idle_loop"            # 空转循环（无工具调用）
    USER_CANCEL = "user_cancel"        # 用户取消
    WAITING_CONFIRMATION = "waiting_confirmation"  # 等待用户确认（路径/命令等）


@dataclass
class ExecutionState:
    """执行状态 - 用于断点续跑

    Attributes:
        current_node: 当前执行的节点名
        iteration_count: 迭代次数
        last_error: 最后一个错误信息
        pending_tools: 待执行的工具列表
        checkpoint_data: 检查点数据（LangGraph checkpoint config）
        created_at: 创建时间
        updated_at: 更新时间
    """
    current_node: str = ""
    iteration_count: int = 0
    last_error: Optional[str] = None
    pending_tools: List[str] = field(default_factory=list)
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于 JSON 序列化"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExecutionState":
        """从字典创建实例"""
        return cls(
            current_node=data.get("current_node", ""),
            iteration_count=data.get("iteration_count", 0),
            last_error=data.get("last_error"),
            pending_tools=data.get("pending_tools", []),
            checkpoint_data=data.get("checkpoint_data", {}),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
        )

    def is_valid(self) -> bool:
        """验证状态完整性

        Returns:
            True 如果状态有效可恢复
        """
        # 必须有当前节点或检查点数据
        has_node = bool(self.current_node)
        has_checkpoint = bool(self.checkpoint_data)
        # 迭代次数不能为负
        valid_iteration = self.iteration_count >= 0
        return (has_node or has_checkpoint) and valid_iteration

    def update_timestamp(self) -> "ExecutionState":
        """更新时间戳并返回自身"""
        self.updated_at = datetime.now().isoformat()
        return self


class AgentState(TypedDict):
    """精简后的状态定义 - 从18个字段精简到11个

    核心字段：
    - messages: 对话历史，使用 Annotated 自动累加
    - current_task: 当前任务描述
    - iteration: 当前迭代次数
    - stop_reason: 停止原因（替代 should_continue）

    子代理字段：
    - sub_agents: 子代理状态映射
    - sub_agent_results: 子代理结果
    - is_subagent: 是否为子代理模式
    - allowed_tools: 允许的工具列表

    错误处理字段：
    - errors: 错误列表
    - retry_count: 重试次数
    """

    # 核心字段（必须）
    messages: Annotated[List[BaseMessage], add]  # 对话历史，自动累加

    # 任务追踪
    current_task: str                           # 当前任务
    iteration: int                              # 当前迭代次数

    # 控制流 - 使用枚举替代布尔值
    stop_reason: StopReason                     # 停止原因
    thread_id: str                              # 会话ID

    # 子代理（可选）
    sub_agents: Dict[str, str]                  # agent_id -> status
    sub_agent_results: Dict[str, Any]           # agent_id -> result
    is_subagent: bool                           # 是否为子代理
    allowed_tools: Optional[List[str]]          # 允许的工具

    # 错误处理（可选）
    errors: List[str]                           # 错误列表
    retry_count: int                            # 重试次数

    # 用户确认（可选）
    pending_confirmation_path: Optional[str]    # 待确认的路径

    # 反思节点（可选）
    reflection_notes: List[str]                 # 反思笔记
    lessons_learned: List[str]                  # 经验教训
    improvement_suggestions: List[str]          # 改进建议


def create_initial_state(
    user_input: str,
    history: Optional[List[BaseMessage]] = None,
    thread_id: str = "default",
    is_subagent: bool = False,
    allowed_tools: Optional[List[str]] = None
) -> AgentState:
    """创建初始状态

    Args:
        user_input: 用户输入
        history: 历史消息（可选）
        thread_id: 会话ID
        is_subagent: 是否为子代理模式
        allowed_tools: 允许的工具列表

    Returns:
        初始化的 AgentState
    """
    from langchain_core.messages import HumanMessage

    # 构建消息列表
    messages = list(history) if history else []
    messages.append(HumanMessage(content=user_input))

    return AgentState(
        messages=messages,
        current_task=user_input,
        iteration=0,
        stop_reason=StopReason.CONTINUE,
        thread_id=thread_id,
        sub_agents={},
        sub_agent_results={},
        is_subagent=is_subagent,
        allowed_tools=allowed_tools,
        errors=[],
        retry_count=0,
        pending_confirmation_path=None,
        reflection_notes=[],
        lessons_learned=[],
        improvement_suggestions=[],
    )


def get_max_iterations(state: AgentState) -> int:
    """获取最大迭代次数（子代理使用更小的限制）"""
    from mini_claude.config.settings import settings
    if state.get("is_subagent", False):
        return settings.max_subagent_iterations
    return settings.max_iterations
