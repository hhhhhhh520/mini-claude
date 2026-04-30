"""Agent state definition - Refactored version."""

from typing import TypedDict, List, Optional, Dict, Any, Annotated
from langchain_core.messages import BaseMessage
from enum import Enum
from operator import add


class StopReason(Enum):
    """停止原因枚举 - 统一控制流判断"""
    CONTINUE = "continue"              # 继续执行
    TASK_COMPLETE = "task_complete"    # 任务完成
    MAX_ITERATIONS = "max_iterations"  # 达到迭代上限
    ERROR = "error"                    # 发生错误
    IDLE_LOOP = "idle_loop"            # 空转循环（无工具调用）
    USER_CANCEL = "user_cancel"        # 用户取消
    WAITING_CONFIRMATION = "waiting_confirmation"  # 等待用户确认（路径/命令等）


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
    )


def get_max_iterations(state: AgentState) -> int:
    """获取最大迭代次数（子代理使用更小的限制）"""
    from mini_claude.config.settings import settings
    if state.get("is_subagent", False):
        return settings.max_subagent_iterations
    return settings.max_iterations
