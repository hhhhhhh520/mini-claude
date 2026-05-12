# 代码之诗

## 一个关于异步的故事

---

深夜，服务器的指示灯在黑暗中闪烁着绿色的微光。

林夏盯着监控屏幕上的红色警报，CPU 占用率已经飙升到 98%。她的电商平台正在经历第一次双十一流量洪峰，而那个承载着百万用户购物车的微服务，快要崩溃了。

"为什么会这样？" 她喃喃自语，手指在键盘上飞快敲击，打开日志文件。

```
[ERROR] Thread pool exhausted. Waiting for available thread...
[ERROR] Request timeout after 30s. User: user_89234
[ERROR] Thread pool exhausted. Waiting for available thread...
```

线程池耗尽。每一个 HTTP 请求都在等待数据库响应时阻塞着线程，而线程总数只有 200 个。200 个线程，面对着每秒 5000 个请求，就像是用茶杯去接瀑布。

她想起了三个月前看过的一篇文章 —— 关于 Python 的异步编程。那时候她觉得"协程"这个词很陌生，`async/await` 的语法也有些奇怪。但现在，她愿意尝试任何可能拯救这个夜晚的东西。

林夏深吸一口气，打开了那个名为 `cart_service.py` 的文件。

---

### 第一章：觉醒

```python
# 原来的同步代码
def get_cart_items(user_id: str) -> list[CartItem]:
    """获取购物车商品"""
    items = db.query(CartItem).filter_by(user_id=user_id).all()
    for item in items:
        item.product = get_product(item.product_id)  # 每次都要查询！
    return items
```

她看出了问题。每个购物车商品都要单独查询商品详情，100 个商品就是 100 次数据库查询，每次查询阻塞线程 50 毫秒，那就是 5 秒的等待时间。

"如果能让这些查询同时进行呢？"

三个小时后，第一版异步代码诞生了：

```python
# 新的异步代码
async def get_cart_items(user_id: str) -> list[CartItem]:
    """获取购物车商品 - 异步版本"""
    async with AsyncSessionLocal() as session:
        items = await session.execute(
            select(CartItem).where(CartItem.user_id == user_id)
        )
        items = items.scalars().all()

        # 并发获取所有商品详情
        product_ids = [item.product_id for item in items]
        products = await asyncio.gather(*[
            get_product_async(pid) for pid in product_ids
        ])

        for item, product in zip(items, products):
            item.product = product
        return items
```

部署。观察。

监控屏幕上的曲线开始下降。95%... 85%... 75%...

---

### 第二章：蜕变

"成功了！" 林夏激动地喊出声。

但警报还没有完全消失。她注意到，虽然 CPU 使用率下降了，但内存占用却开始攀升。异步代码打开了另一扇门 —— 并发量提升了十倍，但每一个连接都在消耗内存。

她需要控制并发量。

```python
# 添加信号量控制并发
semaphore = asyncio.Semaphore(1000)  # 最多 1000 个并发

async def get_cart_items_limited(user_id: str) -> list[CartItem]:
    """带并发控制的版本"""
    async with semaphore:
        return await get_cart_items(user_id)
```

内存曲线开始稳定。70%... 65%... 60%...

---

### 第三章：黎明

凌晨四点，流量洪峰终于过去。

林夏揉了揉酸痛的眼睛，看着监控屏幕上一条平稳的绿色曲线。CPU 占用率 35%，内存占用 45%，平均响应时间 120 毫秒。她成功守护了这次双十一。

她打开终端，敲下了一行新的注释：

```python
# 2026-11-11 04:23
# 从同步到异步，线程池不再哭泣
# 茶杯终于变成了海洋
# —— 林夏
```

---

## 尾声

第二天早上，当其他工程师走进办公室时，他们惊讶地发现监控系统显示着完美的曲线。而林夏趴在桌上，睡得正香，嘴角带着一丝微笑。

她的屏幕上开着一个终端，里面有一行未提交的代码：

```python
# TODO: 把这个故事讲给下一个遇到线程池耗尽的人听
```

---

**后记**

这不是一个虚构的故事。

每一天，在世界各地的服务器机房里，都有无数个"林夏"在面对同样的挑战。线程池耗尽、请求超时、内存溢出 —— 这些问题困扰着每一个需要处理高并发的开发者。

异步编程不是银弹，但它是一把锋利的剑。当你学会正确使用它时，你就能在流量的洪峰中劈开一条生路。

而这一切，只需要一个 `async` 和一个 `await`。

---

*故事作者: Claude* | *献给每一位深夜加班的程序员*
