# Python 异步编程完全指南

> 本指南带你从零掌握 Python 异步编程，从基础概念到实战应用，适合有同步编程基础的开发者。

## 简介

Python 3.4 引入 `asyncio` 库，3.5 添加 `async/await` 语法，异步编程成为 Python 生态的重要组成部分。异步编程特别适合 I/O 密集型任务，如网络请求、文件操作、数据库查询等。

**为什么需要异步？**

- 同步代码在等待 I/O 时阻塞整个线程
- 异步代码可以在等待时执行其他任务
- 单线程即可实现高并发

---

## 第一章：异步基础

### 1.1 协程与事件循环

协程是异步编程的核心概念。使用 `async def` 定义协程函数，`await` 等待协程执行。

```python
import asyncio
import time

async def say_hello():
    """简单的协程示例"""
    print("开始执行...")
    await asyncio.sleep(1)  # 模拟 I/O 操作
    print("Hello, Async World!")

# 运行协程
asyncio.run(say_hello())
```

### 1.2 并发执行多个任务

使用 `asyncio.gather()` 可以并发执行多个协程：

```python
async def fetch_data(name: str, delay: float) -> str:
    """模拟获取数据"""
    print(f"开始获取 {name}...")
    await asyncio.sleep(delay)
    print(f"完成获取 {name}")
    return f"{name}的数据"

async def main():
    """并发执行多个任务"""
    start = time.time()

    # 并发执行三个任务
    results = await asyncio.gather(
        fetch_data("用户信息", 2),
        fetch_data("订单列表", 1),
        fetch_data("商品详情", 1.5),
    )

    print(f"总耗时: {time.time() - start:.2f}秒")
    print(f"结果: {results}")

asyncio.run(main())
```

**输出示例：**
```
开始获取 用户信息...
开始获取 订单列表...
开始获取 商品详情...
完成获取 订单列表
完成获取 商品详情
完成获取 用户信息
总耗时: 2.00秒
结果: ['用户信息的数据', '订单列表的数据', '商品详情的数据']
```

---

## 第二章：异步 HTTP 客户端

### 2.1 使用 aiohttp 发送请求

`aiohttp` 是最流行的异步 HTTP 客户端库：

```python
import aiohttp
import asyncio
from typing import Any

async def fetch_json(
    session: aiohttp.ClientSession,
    url: str
) -> dict[str, Any]:
    """发送 GET 请求并返回 JSON"""
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.json()

async def fetch_multiple_apis() -> list[dict[str, Any]]:
    """并发请求多个 API"""
    urls = [
        "https://api.github.com/users/python",
        "https://api.github.com/users/microsoft",
        "https://api.github.com/users/openai",
    ]

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_json(session, url) for url in urls]
        return await asyncio.gather(*tasks)

# 运行
results = asyncio.run(fetch_multiple_apis())
for r in results:
    print(f"用户: {r.get('login')}, 关注者: {r.get('followers')}")
```

### 2.2 错误处理与重试

健壮的异步代码需要完善的错误处理：

```python
import aiohttp
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential

class APIError(Exception):
    """API 错误"""
    pass

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
)
async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str
) -> dict:
    """带重试的请求"""
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 429:
                raise APIError("请求过于频繁")
            resp.raise_for_status()
            return await resp.json()
    except aiohttp.ClientError as e:
        print(f"请求失败: {e}")
        raise
```

---

## 第三章：异步数据库操作

### 3.1 使用 SQLAlchemy 2.0 异步模式

SQLAlchemy 2.0 提供原生异步支持：

```python
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    email: Mapped[str]

# 创建异步引擎
engine = create_async_engine(
    "sqlite+aiosqlite:///users.db",
    echo=True,
)

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

async def get_user_by_email(email: str) -> User | None:
    """根据邮箱查询用户"""
    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

async def create_user(name: str, email: str) -> User:
    """创建用户"""
    async with AsyncSessionLocal() as session:
        user = User(name=name, email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
```

### 3.2 批量操作优化

使用批量操作提升性能：

```python
async def bulk_insert_users(users_data: list[dict]) -> None:
    """批量插入用户"""
    async with AsyncSessionLocal() as session:
        users = [User(**data) for data in users_data]
        session.add_all(users)
        await session.commit()
        print(f"成功插入 {len(users)} 条记录")

# 使用示例
users_data = [
    {"name": "Alice", "email": "alice@example.com"},
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Charlie", "email": "charlie@example.com"},
]

asyncio.run(bulk_insert_users(users_data))
```

---

## 总结与建议

### 关键要点

1. **异步适合 I/O 密集型任务** - 网络请求、文件操作、数据库查询
2. **CPU 密集型任务仍需多进程** - 使用 `ProcessPoolExecutor`
3. **避免阻塞事件循环** - 不要在异步代码中使用 `time.sleep()` 或同步 I/O

### 最佳实践

| 场景 | 推荐方案 |
|------|----------|
| HTTP 客户端 | `aiohttp` 或 `httpx` |
| 数据库 ORM | SQLAlchemy 2.0 async |
| Redis | `aioredis` (现已合并到 redis-py) |
| 任务队列 | `arq` 或 `celery` with asyncio |

### 常见陷阱

```python
# 错误：在异步函数中使用同步 sleep
async def bad_example():
    time.sleep(1)  # 阻塞整个事件循环！

# 正确：使用异步 sleep
async def good_example():
    await asyncio.sleep(1)  # 让出控制权
```

### 进一步学习

- [Python 官方 asyncio 文档](https://docs.python.org/zh-cn/3/library/asyncio.html)
- [aiohttp 官方文档](https://docs.aiohttp.org/)
- [SQLAlchemy 2.0 异步指南](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

---

*文档版本: 1.0 | 最后更新: 2026-05-04*
