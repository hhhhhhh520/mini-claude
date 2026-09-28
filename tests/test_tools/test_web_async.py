"""web 三件套异步化测试（对标 Claude Code 的非阻塞 web 工具）。

背景：web_fetch/web_search/weather 原实现是 async 壳套同步 I/O
（requests / DDGS 直接在事件循环里跑），多 Agent 并行时一个网页抓取
会拖停全部子代理——与本项目"多 Agent 并发"的核心卖点直接冲突。

契约：
1. 非阻塞：两个 web 调用并发执行，总耗时 << 串行耗时（旧实现必红的判据）；
2. 行为保持：SSRF 重定向拦截、正文解析、wttr.in JSON 解析在重构后不变。

所有测试零真实网络：HTTP 层用 monkeypatch 的假响应，DNS 用 localhost
黑名单（纯字符串判断）或整体旁路。
"""

import asyncio
import time
from types import SimpleNamespace

import httpx
import pytest

from mini_claude.tools.web_fetch import WebFetchTool
from mini_claude.tools.weather import WeatherTool
from mini_claude.tools.web_search import WebSearchTool

HTML = (
    "<html><head><title>Example</title></head><body><main>"
    "<p>hello world content line one</p>"
    "<p>hello world content line two</p>"
    "</main></body></html>"
)

WEATHER_JSON = {
    "current_condition": [
        {
            "temp_C": "20",
            "FeelsLikeC": "19",
            "weatherDesc": [{"value": "Sunny"}],
            "humidity": "60",
            "winddir16Point": "NE",
            "windspeedKmph": "12",
            "visibility": "10",
            "uvIndex": "5",
        }
    ],
    "weather": [
        {
            "date": "2026-09-28",
            "maxtempC": "22",
            "mintempC": "15",
            "avgtempC": "18",
            "hourly": [{"weatherDesc": [{"value": "Clear"}]} for _ in range(8)],
            "astronomy": [{"sunshine_hours": "8.0"}],
        }
    ],
    "nearest_area": [{"areaName": [{"value": "Changsha"}], "country": [{"value": "China"}]}],
}


def _httpx_resp(
    status_code=200, url="https://example.com/", text=None, json_data=None, headers=None
):
    kwargs = {"request": httpx.Request("GET", url)}
    if json_data is not None:
        return httpx.Response(status_code, json=json_data, headers=headers or {}, **kwargs)
    return httpx.Response(status_code, text=text or "", headers=headers or {}, **kwargs)


def _patch_httpx(monkeypatch, responder):
    """打桩 httpx.AsyncClient.get（现实现的唯一 HTTP 栈）：零真实网络。

    responder(url) -> dict(status_code=, text=, json_data=, headers=)
    """

    async def fake_async_get(self, url, **kwargs):
        r = responder(str(url))
        return _httpx_resp(
            status_code=r.get("status_code", 200),
            url=str(url),
            text=r.get("text"),
            json_data=r.get("json_data"),
            headers=r.get("headers"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_async_get)


@pytest.mark.asyncio
async def test_web_fetch_concurrent_not_blocking(monkeypatch):
    """两次抓取必须并发执行：串行 ≥0.8s，非阻塞 ≈0.4s

    红阶段（同步 requests + time.sleep）实测 0.8s+ 串行；实现切 httpx 后
    本测试用 asyncio.sleep 慢桩锁死并发语义。
    """
    monkeypatch.setattr("mini_claude.tools.web_fetch._check_ssrf", lambda url: (True, "OK"))

    async def slow_async_get(self, url, **kwargs):
        await asyncio.sleep(0.4)
        return _httpx_resp(status_code=200, url=str(url), text=HTML)

    monkeypatch.setattr(httpx.AsyncClient, "get", slow_async_get)

    tool = WebFetchTool()
    # 预热默认线程池：SSRF 检查经 asyncio.to_thread 卸载，冷启动首个线程有
    # ~0.2s 抖动，不预热会污染并发计时（与被测行为无关的测试噪声）
    await asyncio.to_thread(int)
    # 预热共享 httpx client：构造会同步加载 SSL 证书库（Windows ~0.2-0.4s，
    # 随磁盘/Defender 状态漂移），冷构造恰好落在首个 execute 的阻塞段会把
    # 两次并发 sleep 串行化（实测 0.81s 假阳性）——与被测的并发语义无关
    from mini_claude.tools._http import get_shared_client

    get_shared_client()
    start = time.perf_counter()
    results = await asyncio.gather(
        tool.execute("https://example.com/a"),
        tool.execute("https://example.com/b"),
    )
    elapsed = time.perf_counter() - start

    assert all("hello world content line one" in r for r in results)
    assert elapsed < 0.7, f"两次抓取耗时 {elapsed:.2f}s——web_fetch 仍阻塞事件循环（串行特征 ≥0.8s）"


@pytest.mark.asyncio
async def test_web_search_concurrent_not_blocking(monkeypatch):
    """两次搜索必须并发：ddgs 是同步库，必须经线程卸载（旧实现实测 1.2s 串行）"""
    fake_ddgs = _make_fake_ddgs_module(sleep=0.15)
    monkeypatch.setitem(__import__("sys").modules, "ddgs", fake_ddgs)

    tool = WebSearchTool()
    # 线程池预热（同 fetch 测试）
    await asyncio.to_thread(int)
    start = time.perf_counter()
    results = await asyncio.gather(
        tool.execute("query one"),
        tool.execute("query two"),
    )
    elapsed = time.perf_counter() - start

    assert all("Result A" in r for r in results)
    # 并行 ≈0.3s（每次搜索 2 条结果 × 0.15s sleep），串行 ≥0.6s
    assert elapsed < 0.45, (
        f"两次搜索耗时 {elapsed:.2f}s——web_search 仍阻塞事件循环（串行特征 ≥0.6s）"
    )


def _make_fake_ddgs_module(sleep: float):
    """构造假 ddgs 模块：text() 在线程里 sleep 后产出结果"""

    class FakeDDGS:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def text(self, query, max_results=5):
            results = [
                {"title": "Result A", "href": "https://example.com/a", "body": "body A"},
                {"title": "Result B", "href": "https://example.com/b", "body": "body B"},
            ][:max_results]
            for r in results:
                time.sleep(sleep)
                yield r

    module = SimpleNamespace(DDGS=FakeDDGS)
    return module


@pytest.mark.asyncio
async def test_weather_json_contract(monkeypatch):
    """weather 走 httpx.AsyncClient：wttr.in JSON 解析行为保持"""

    async def fake_get(self, url, **kwargs):
        return _httpx_resp(json_data=WEATHER_JSON, url=str(url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    tool = WeatherTool()
    output = await tool.execute("Changsha", days=1)

    assert "Weather for Changsha, China" in output
    assert "Temperature: 20°C" in output
    assert "2026-09-28" in output


@pytest.mark.asyncio
async def test_shared_http_client_reused(monkeypatch):
    """共享 client 单例：避免每次调用构造 AsyncClient（SSL 证书库同步加载 ~0.2s，会冻结事件循环）"""
    from mini_claude.tools._http import close_shared_client, get_shared_client

    try:
        c1 = get_shared_client()
        c2 = get_shared_client()
        assert c1 is c2, "同进程必须复用同一 httpx client"
    finally:
        await close_shared_client()

    c3 = get_shared_client()
    assert c3 is not c1 or c1.is_closed, "close 后重入应重建可用 client"
    await close_shared_client()


@pytest.mark.asyncio
async def test_web_fetch_redirect_to_private_ip_blocked(monkeypatch):
    """契约保持：重定向到内网地址必须被逐跳 SSRF 检查拦截（真实 _check_ssrf）"""
    _patch_httpx(
        monkeypatch,
        lambda url: (
            {"status_code": 302, "headers": {"location": "http://127.0.0.1/secret"}}
            if url.rstrip("/") == "https://example.com/start"
            else {"status_code": 200, "text": HTML}
        ),
    )
    tool = WebFetchTool()
    output = await tool.execute("https://example.com/start")
    assert "Redirect to blocked address" in output


@pytest.mark.asyncio
async def test_web_fetch_success_parses_content(monkeypatch):
    """契约保持：标题 + 正文提取 + 截断行为不变"""
    monkeypatch.setattr("mini_claude.tools.web_fetch._check_ssrf", lambda url: (True, "OK"))
    _patch_httpx(
        monkeypatch,
        lambda url: {"status_code": 200, "text": HTML},
    )
    tool = WebFetchTool()
    output = await tool.execute("https://example.com/page")
    assert "Title: Example" in output
    assert "hello world content line one" in output
