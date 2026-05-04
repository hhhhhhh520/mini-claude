"""Retry node: Prepare for re-execution."""

from langchain_core.messages import HumanMessage

from ._shared import logger


async def retry_node(state) -> dict:
    """重试节点

    职责：
    准备重新执行
    """
    logger.debug("retry_node: preparing for retry")

    errors = state.get("errors", [])
    error_msg = errors[-1] if errors else ""

    # 检测是否为 text_not_found 错误，添加特定提示
    if "text not found" in error_msg.lower() or "old_text" in error_msg.lower():
        hint = "\n\n💡 提示：请先使用 read_file 工具读取文件最新内容，确认 old_text 参数正确后再尝试 edit_file。"
        return {
            "messages": [HumanMessage(content=f"请重新尝试执行任务。{hint}")],
        }

    return {
        "messages": [HumanMessage(content="请重新尝试执行任务。")],
    }