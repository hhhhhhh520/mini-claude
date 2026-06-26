"""Check completion node: Use LLM to determine if task is complete."""

from langchain_core.messages import HumanMessage, AIMessage

from ._shared import (
    AgentState,
    StopReason,
    logger,
)


async def check_completion_node(state: AgentState) -> dict:
    """检查任务完成度节点

    职责：
    使用 LLM 判断任务是否真正完成

    注意：只在检测到可能完成时调用，避免额外 LLM 开销
    """
    current_task = state["current_task"]
    messages = state["messages"]

    # 快速检查：如果最近有工具结果但没有 AI 的文本回复，直接返回 INCOMPLETE
    # 这避免了 LLM 在还没告诉用户结果时就判断完成
    recent_messages = messages[-5:]
    has_tool_result = any(
        isinstance(m, HumanMessage) and hasattr(m, "name") and m.name for m in recent_messages
    )
    has_ai_text_reply = any(
        isinstance(m, AIMessage) and m.content and len(m.content.strip()) > 5  # 有实质性回复
        for m in recent_messages
    )

    if has_tool_result and not has_ai_text_reply:
        logger.debug("check_completion_node: has tool result but no AI reply, returning INCOMPLETE")
        return {"stop_reason": StopReason.CONTINUE}

    # 构建检查提示 - 更明确的判断标准
    recent_messages = messages[-10:]
    messages_text = "\n".join(
        [
            f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content[:300]}..."
            for m in recent_messages
            if m.content
        ]
    )

    completion_prompt = f"""判断以下任务是否已完成。

原始任务：{current_task}

最近的对话和工具结果：
{messages_text}

判断标准：
1. 如果任务要求"运行"或"执行"文件，必须看到实际运行结果（不仅仅是读取文件）
2. 如果任务要求"创建"或"生成"文件，必须看到文件创建成功的确认
3. 如果任务要求"修改"或"编辑"文件，必须看到修改成功的确认
4. 如果任务是"查看文件夹内容"或"列出目录"，必须明确告知用户文件夹内容（包括是否为空）
5. 如果任务是对话类问题（如"介绍"、"解释"），有回答就算完成

重要：
- 如果任务是查看文件夹，必须报告文件夹是否为空，不能只说"执行成功"
- 空文件夹也是有效结果，但必须明确告知用户"这是一个空文件夹"

请回答以下之一：
- COMPLETE: 任务已完成（满足上述标准，且结果已明确告知用户）
- INCOMPLETE: 任务未完成（还需要继续执行或需要向用户报告结果）

只回答 COMPLETE 或 INCOMPLETE，不要解释。"""

    try:
        from ._shared import llm_provider

        response = await llm_provider.chat(
            messages=[{"role": "user", "content": completion_prompt}],
            temperature=0,
        )
        answer = response.choices[0].message.content.strip().upper()

        logger.debug("check_completion_node: LLM answer", answer=answer)

        # 注意：必须先检查 INCOMPLETE，因为 "COMPLETE" in "INCOMPLETE" 为 True
        if answer == "INCOMPLETE" or answer.startswith("INCOMPLETE"):
            return {"stop_reason": StopReason.CONTINUE}
        elif answer == "COMPLETE" or answer.startswith("COMPLETE"):
            return {"stop_reason": StopReason.TASK_COMPLETE}
        else:
            return {"stop_reason": StopReason.CONTINUE}

    except (ConnectionError, TimeoutError) as e:
        logger.debug("check_completion_node LLM connection error", error=str(e))
        return {"stop_reason": StopReason.CONTINUE}
    except Exception as e:
        logger.debug("check_completion_node unexpected error", error=type(e).__name__)
        # 出错时默认继续
        return {"stop_reason": StopReason.CONTINUE}
