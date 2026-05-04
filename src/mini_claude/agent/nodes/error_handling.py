"""Error handling node: Check retry count and generate fix suggestions."""

from langchain_core.messages import AIMessage, HumanMessage

from ._shared import (
    AgentState,
    StopReason,
    logger,
)
from ..suggestion import get_suggestion_engine


async def handle_error_node(state: AgentState) -> dict:
    """错误处理节点

    职责：
    1. 检查重试次数
    2. 生成修复建议
    3. 使用 SuggestionEngine 提供可操作建议
    """
    errors = state.get("errors", [])
    retry_count = state.get("retry_count", 0)

    logger.debug("handle_error_node: checking retry", retry_count=retry_count, error_count=len(errors))

    if retry_count >= 3:
        error_msg = errors[-1] if errors else "多次重试失败"
        # 生成建议
        suggestion_engine = get_suggestion_engine()
        suggestion = suggestion_engine.analyze_error(error_msg)
        return {
            "messages": [AIMessage(content=f"多次重试失败，错误：{error_msg}\n\n{suggestion_engine.format_suggestion(suggestion)}")],
            "stop_reason": StopReason.ERROR,
        }

    # 生成修复建议 - strip nested prefixes to avoid "上一步出错：上一步出错：..."
    error_msg = errors[-1] if errors else "未知错误"
    while error_msg.startswith("上一步出错："):
        error_msg = error_msg[len("上一步出错："):]

    # 使用 SuggestionEngine 分析错误
    suggestion_engine = get_suggestion_engine()
    suggestion = suggestion_engine.analyze_error(error_msg)
    suggestion_text = suggestion_engine.format_suggestion(suggestion)

    # 检测是否为 text_not_found 错误，添加特定提示
    if "text not found" in error_msg.lower() or "old_text" in error_msg.lower():
        text_not_found_hint = "\n\n💡 提示：文件内容可能已更改。请先使用 read_file 工具获取文件最新内容，然后使用正确的 old_text 参数重新编辑。"
        suggestion_text += text_not_found_hint

    return {
        "messages": [HumanMessage(content=f"上一步出错：{error_msg}\n\n{suggestion_text}\n\n请尝试修复或使用其他方法完成任务。")],
        "retry_count": retry_count + 1,
    }