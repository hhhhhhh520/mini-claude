"""MCP OAuth token 落盘存储测试（SDK 无关——纯文件 I/O）。

形态：~/.mini-claude/mcp-auth/<server>.json
    {"server", "client_info", "tokens", "obtained_at", "expires_at"}
- 0600 权限语义（POSIX 实 chmod；Windows 无此语义，尽力而为）
- 坏 JSON 不炸：当空处理，下次写入覆盖
- FileTokenStorage 返回/接受纯 dict；pydantic 模型靠 model_dump 鸭子类型兼容
"""

import json
import os
import time
from types import SimpleNamespace

import pytest

from mini_claude.mcp.token_store import FileTokenStorage, _to_plain, token_file_path


@pytest.fixture
def home(tmp_path):
    return tmp_path / "home"


def test_token_file_path_layout(home):
    p = token_file_path("remote", home_dir=home)
    assert p == home / ".mini-claude" / "mcp-auth" / "remote.json"


@pytest.mark.asyncio
async def test_roundtrip_tokens_and_client_info(home):
    store = FileTokenStorage("remote", home_dir=home)
    assert await store.get_tokens() is None
    assert await store.get_client_info() is None

    tokens = {"access_token": "at1", "token_type": "Bearer", "expires_in": 3600}
    await store.set_tokens(tokens)
    client = {"client_id": "cid", "redirect_uris": ["http://127.0.0.1:1/cb"]}
    await store.set_client_info(client)

    assert (await store.get_tokens())["access_token"] == "at1"
    assert (await store.get_client_info())["client_id"] == "cid"


@pytest.mark.asyncio
async def test_set_accepts_pydantic_like_object(home):
    """SDK 传入的是 pydantic 模型——靠 model_dump 鸭子类型收下。"""

    class FakeModel:
        def model_dump(self, mode="json"):
            return {"access_token": "pyd"}

    store = FileTokenStorage("remote", home_dir=home)
    await store.set_tokens(FakeModel())
    assert (await store.get_tokens())["access_token"] == "pyd"


@pytest.mark.asyncio
async def test_expiry_recorded_from_expires_in(home):
    store = FileTokenStorage("remote", home_dir=home)
    before = time.time()
    await store.set_tokens({"access_token": "at", "expires_in": 600})
    snap = store.snapshot()
    assert snap["has_tokens"] is True
    assert snap["obtained_at"] >= before
    assert snap["expires_at"] == pytest.approx(snap["obtained_at"] + 600, abs=1.0)


@pytest.mark.asyncio
async def test_expiry_absent_when_no_expires_in(home):
    store = FileTokenStorage("remote", home_dir=home)
    await store.set_tokens({"access_token": "at"})
    assert store.snapshot()["expires_at"] is None


@pytest.mark.asyncio
async def test_corrupt_file_treated_as_empty(home):
    store = FileTokenStorage("remote", home_dir=home)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json", encoding="utf-8")
    assert await store.get_tokens() is None
    assert await store.get_client_info() is None
    # 下次写入覆盖坏文件
    await store.set_tokens({"access_token": "fresh"})
    assert (await store.get_tokens())["access_token"] == "fresh"


@pytest.mark.asyncio
async def test_clear_removes_file(home):
    store = FileTokenStorage("remote", home_dir=home)
    await store.set_tokens({"access_token": "at"})
    await store.clear()
    assert not store.path.exists()
    assert await store.get_tokens() is None
    await store.clear()  # 幂等


@pytest.mark.asyncio
async def test_servers_are_isolated(home):
    a = FileTokenStorage("alpha", home_dir=home)
    b = FileTokenStorage("beta", home_dir=home)
    await a.set_tokens({"access_token": "A"})
    assert (await b.get_tokens()) is None
    assert (await a.get_tokens())["access_token"] == "A"


@pytest.mark.asyncio
async def test_snapshot_empty_when_no_file(home):
    store = FileTokenStorage("ghost", home_dir=home)
    assert store.snapshot() is None


@pytest.mark.asyncio
async def test_snapshot_merges_client_info_state(home):
    store = FileTokenStorage("remote", home_dir=home)
    await store.set_client_info({"client_id": "cid"})
    snap = store.snapshot()
    assert snap["has_client_info"] is True
    assert snap["has_tokens"] is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX 文件权限语义")
@pytest.mark.asyncio
async def test_file_mode_0600_on_posix(home):
    store = FileTokenStorage("remote", home_dir=home)
    await store.set_tokens({"access_token": "secret"})
    assert (os.stat(store.path).st_mode & 0o777) == 0o600


@pytest.mark.asyncio
async def test_file_content_is_valid_json(home):
    store = FileTokenStorage("remote", home_dir=home)
    await store.set_tokens({"access_token": "at"})
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["server"] == "remote"
    assert data["tokens"]["access_token"] == "at"


def test_non_dict_payload_rejected():
    """SimpleNamespace 无 model_dump 时的防御：不炸，按 dict 失败路径处理。

    （锁定行为：set 非法载荷抛 TypeError，而不是写坏文件。）
    """
    with pytest.raises(TypeError):
        _to_plain(SimpleNamespace(access_token="x"))
