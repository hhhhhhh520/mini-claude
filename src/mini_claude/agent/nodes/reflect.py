"""Reflect node: Analyze execution results and summarize lessons."""

import json
from typing import Dict, List

from langchain_core.messages import AIMessage, HumanMessage

from ._shared import (
    AgentState,
    trace_agent_node,
    logger,
)


async def reflect_node(state: AgentState) -> dict:
    """Reflect 节点：分析执行结果，总结经验

    仅在复杂任务时激活（由 TaskComplexityAnalyzer 判断）

    职责：
    1. 分析任务复杂度，决定是否需要反思
    2. 对复杂任务生成反思内容：
       - 成功经验：哪些工具调用成功，为什么成功
       - 失败教训：哪些尝试失败，如何避免
       - 改进建议：下次执行类似任务的建议

    Returns:
        部分状态更新: reflection_notes, lessons_learned, improvement_suggestions
    """
    from ..complexity import TaskComplexityAnalyzer, ComplexityLevel

    with trace_agent_node("reflect", state["iteration"]) as span:
        current_task = state["current_task"]
        messages = state["messages"]
        iteration = state["iteration"]

        logger.debug("reflect_node: starting", iteration=iteration)

        if span:
            span.set_attribute("iteration", iteration)

        # 1. 分析任务复杂度
        analyzer = TaskComplexityAnalyzer()

        # 从消息中提取上下文信息
        file_count = 0
        for msg in messages:
            if hasattr(msg, 'name') and msg.name == 'write_file':
                file_count += 1

        context = {
            "file_count": file_count,
        }

        complexity = analyzer.analyze(current_task, context)
        logger.debug(
            "reflect_node: complexity analysis",
            complexity_level=complexity.level.value,
            score=complexity.score,
        )

        if span:
            span.set_attribute("complexity_level", complexity.level.value)
            span.set_attribute("complexity_score", complexity.score)

        # 2. 只对复杂任务进行反思
        if complexity.level != ComplexityLevel.COMPLEX:
            logger.debug("reflect_node: task not complex enough, skipping reflection")
            if span:
                span.set_attribute("reflected", False)
            return {}  # 不修改状态

        if span:
            span.set_attribute("reflected", True)

        # 3. 提取工具调用历史
        tool_calls: List[Dict] = []
        tool_results: List[Dict] = []

        for msg in messages:
            # AI 消息中的工具调用
            if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    # ToolCall 对象有 name, args, id 属性
                    if hasattr(tc, 'name'):
                        tool_calls.append({
                            "name": tc.name,
                            "args": tc.args if hasattr(tc, 'args') else {},
                        })
                    elif isinstance(tc, dict):
                        tool_calls.append({
                            "name": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        })
            # Human 消息中的工具结果
            if isinstance(msg, HumanMessage) and hasattr(msg, 'name') and msg.name:
                content = msg.content or ""
                is_success = "error" not in content.lower() and "失败" not in content
                tool_results.append({
                    "name": msg.name,
                    "success": is_success,
                    "content_preview": content[:200] if len(content) > 200 else content,
                })

        # 4. 使用 LLM 生成反思内容
        reflection_prompt = f"""分析以下任务执行过程，总结经验和教训。

任务描述：{current_task}

复杂度分析：
- 等级：{complexity.level.value}
- 得分：{complexity.score}
- 因素：{', '.join(complexity.factors)}

工具调用历史：
{json.dumps(tool_calls, ensure_ascii=False, indent=2) if tool_calls else '无工具调用'}

工具执行结果：
{json.dumps(tool_results, ensure_ascii=False, indent=2) if tool_results else '无工具结果'}

请分析并回答以下三个部分：

1. 成功经验（successes）：
   - 哪些工具调用成功
   - 为什么成功
   - 可以复用的模式

2. 失败教训（failures）：
   - 哪些尝试失败
   - 失败原因分析
   - 如何避免类似失败

3. 改进建议（improvements）：
   - 下次执行类似任务的建议
   - 可以优化的地方
   - 需要注意的风险点

请用 JSON 格式回答：
{{
    "successes": ["经验1", "经验2"],
    "failures": ["教训1", "教训2"],
    "improvements": ["建议1", "建议2"]
}}"""

        try:
            from ._shared import llm_provider
            response = await llm_provider.chat(
                messages=[{"role": "user", "content": reflection_prompt}],
                temperature=0.3,
            )
            content = response.choices[0].message.content or ""

            # 解析 JSON 响应
            # 尝试提取 JSON 块
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                reflection_data = json.loads(json_match.group())
            else:
                reflection_data = json.loads(content)

            successes = reflection_data.get("successes", [])
            failures = reflection_data.get("failures", [])
            improvements = reflection_data.get("improvements", [])

            logger.debug(
                "reflect_node: reflection generated",
                success_count=len(successes),
                failure_count=len(failures),
                improvement_count=len(improvements),
            )

            if span:
                span.set_attribute("success_count", len(successes))
                span.set_attribute("failure_count", len(failures))
                span.set_attribute("improvement_count", len(improvements))

            # 5. 返回状态更新
            return {
                "reflection_notes": successes,
                "lessons_learned": failures,
                "improvement_suggestions": improvements,
            }

        except json.JSONDecodeError as e:
            logger.warning("reflect_node: JSON parse error", error=str(e))
            if span:
                span.set_attribute("error", str(e))
            # 解析失败，返回空更新
            return {}
        except (ConnectionError, TimeoutError) as e:
            logger.warning("reflect_node: LLM connection error", error=str(e))
            if span:
                span.set_attribute("error", str(e))
            return {}
        except Exception as e:
            logger.warning("reflect_node: unexpected error", error=str(e), exc_info=True)
            if span:
                span.set_attribute("error", str(e))
            return {}
