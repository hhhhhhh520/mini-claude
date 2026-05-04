"""Retry node: Prepare for re-execution."""

from langchain_core.messages import HumanMessage

from ._shared import logger


async def retry_node(state) -> dict:
    """重试节点

    职责：
    准备重新执行
    """
    logger.debug("retry_node: preparing for retry")

    return {
        "messages": [HumanMessage(content="请重新尝试执行任务。")],
    }