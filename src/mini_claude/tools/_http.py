"""共享 httpx.AsyncClient（进程级惰性单例）。

为什么共享而不是每调用新建：AsyncClient 构造会**同步**加载 SSL 证书库
（Windows 实测 ~0.22s），发生在事件循环上就是 0.2s 级的全局冻结——
多 Agent 并行下每个 web 工具调用都冻所有协程一次，比同步 requests 更隐蔽。
共享实例把成本摊到进程首次调用，顺带获得连接复用（对标 Claude Code 的
长连接 web 工具行为）。

关闭纪律：repl 与 ask 的 finally 清理链必须 await close_shared_client()
（同 checkpoint 连接、后台进程的收口位置）。
"""

from typing import Optional

import httpx

_client: Optional[httpx.AsyncClient] = None


def get_shared_client() -> httpx.AsyncClient:
    """取进程级共享 client；首用惰性创建，关闭后重入会重建。"""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=15)
    return _client


async def close_shared_client() -> None:
    """进程退出前收口连接（进 repl/ask 的 finally 清理链）。"""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None
