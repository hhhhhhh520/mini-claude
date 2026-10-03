"""_shared LLM provider 懒加载单例测试（2026-10-03 拔除导入期副作用）。

回归锚点（2026-10-02 事故）：ask 首次导入 agent.nodes._shared 发生在测试把
LLMProvider 打补丁的窗口内，模块导入期的 `llm_provider = LLMProvider()` 把
假 provider 铸进全局单例，同进程后续 20 个图测试全炸（单跑全过——导入序敏感）。

锁定契约：
- 导入 _shared 零构造（导入期副作用拔除）
- get_llm_provider() 懒创建且幂等（同一实例）
- rebuild_llm_provider 仍换新单例（/model 热切换语义不变）
- nodes 包级 `llm_provider` 属性经模块 __getattr__ 懒转发（测试兼容面不断）
"""

import importlib
import sys

from mini_claude.llm.provider import LLMProvider


def test_import_under_patch_window_bakes_nothing(monkeypatch):
    """回归用例：补丁窗口内首次导入 _shared，导入期不得构造 provider。"""

    class _FakeProvider:  # 当年炸掉 20 个图测试的形态：没有 model/chat
        pass

    import mini_claude.agent.nodes as nodes_pkg
    from mini_claude.llm import provider as provider_mod

    orig_mod = sys.modules["mini_claude.agent.nodes._shared"]
    # 导入机制会同时改写父包属性——两处都要显式还原，否则 fresh 模块
    # （其 LLMProvider 名绑定的是假类）泄漏给后续用例，重演本次事故
    monkeypatch.setattr(nodes_pkg, "_shared", orig_mod)
    monkeypatch.setattr(provider_mod, "LLMProvider", _FakeProvider)
    monkeypatch.delitem(sys.modules, "mini_claude.agent.nodes._shared", raising=False)
    mod = importlib.import_module("mini_claude.agent.nodes._shared")

    assert mod is not orig_mod, "前提：确实发生了全新导入"
    assert mod.llm_provider is None, "导入期不得构造 provider 实例（零导入期副作用）"


def test_get_llm_provider_lazy_creates_and_reuses():
    mod = importlib.import_module("mini_claude.agent.nodes._shared")
    p1 = mod.get_llm_provider()
    p2 = mod.get_llm_provider()
    assert p1 is p2, "同一单例"
    assert isinstance(p1, LLMProvider)


def test_rebuild_still_swaps_singleton():
    mod = importlib.import_module("mini_claude.agent.nodes._shared")
    old = mod.get_llm_provider()
    new = mod.rebuild_llm_provider("test-model-x")
    try:
        assert new is not old
        assert mod.get_llm_provider() is new
        assert new.model == "test-model-x"
    finally:
        mod.rebuild_llm_provider()  # 还原默认模型


def test_nodes_package_attr_lazy_forwards():
    """nodes.llm_provider 兼容面：经 __getattr__ 懒转发到访问器。"""
    from mini_claude.agent import nodes

    assert isinstance(nodes.llm_provider, LLMProvider)
    # 与 _shared 单例同源
    from mini_claude.agent.nodes import _shared

    assert nodes.llm_provider is _shared.get_llm_provider()


def test_patching_shared_attr_is_respected_by_accessor(monkeypatch):
    """test_reflect_node 的既有模式（按属性 patch 单例）必须继续生效。"""
    from mini_claude.agent.nodes import _shared

    sentinel = object()
    monkeypatch.setattr(_shared, "llm_provider", sentinel)
    assert _shared.get_llm_provider() is sentinel, "访问器不得覆盖已注入的实例"
