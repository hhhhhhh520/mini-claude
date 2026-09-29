"""工具结果尺寸上限（收敛批次②C：context 卫生）。

本体对每个工具设 maxResultSizeChars，超大输出整体截断——防止一次失控的
list_dir/cat 把 context 吃满。act（execute_single_tool）与 ask（run_single）
两条执行链统一走这里。

截断策略：保头去尾（错误信息与结构通常在头部），尾注标明原始长度——
LLM 需要"被截断"这个事实来自我修正（比如改用更窄的搜索条件）。
"""

from ..config.settings import settings

# 截断注记的固定开销预留
_NOTE_RESERVE = 120


def clip_tool_result(text: str, max_chars: int = None) -> str:
    """超限截断工具结果，尾部加截断注记。

    Args:
        text: 原始工具输出
        max_chars: 上限；None 时读 settings.tool_result_max_chars

    Returns:
        原文（未超限）或 截断文本 + 注记
    """
    if text is None:
        return ""
    if max_chars is None:
        max_chars = getattr(settings, "tool_result_max_chars", 24000)
    if len(text) <= max_chars:
        return text
    # 注记本身有长度：预留量取注记长度与上限一半的较小者，极小上限时
    # 保住前半内容（keep 至少不为 0）
    reserve = min(_NOTE_RESERVE, max(max_chars // 2, 0))
    keep = max(max_chars - reserve, 0)
    return (
        text[:keep]
        + f"\n\n[...输出已截断：原始 {len(text)} 字符，仅保留前 {keep} 字符。"
        + "如需其余部分，请缩小查询范围或分段获取...]"
    )
