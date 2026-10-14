# 14 查询延迟与并发优化（30 人同时订票卡顿问题）

## 1. 背景与现象

一次 30 余人同时访问的订票测试中：

- 开场数分钟**页面极慢、难以进入**；
- 之后**逐渐恢复**，用户最终都能订到票；
- 管理端执行 **AI 批量退票等待很久**；
- cloudflared 与 Python 端出现大量 `canceled by remote` / `ConnectionAbortedError` 日志。

排查后确认：日志中的取消错误是**表象**（请求太慢，浏览器主动断开），真正的瓶颈在数据库访问层。

## 2. 实测数据

在本机（Docker Desktop on Windows、MySQL 8.4 容器 `mysql84`）实测：

| 访问方式 | 单次耗时 |
|---|---|
| `docker exec mysql84 mysql ... -e "SELECT 1"` | **134–230 ms** |
| 经连接池执行同一查询（PyMySQL 常连接） | **≈1 ms** |
| `docker exec neo4j-12306 cypher-shell "RETURN 1"` | **2.8–4.4 s** |
| Neo4j bolt 驱动同一查询 | **≈0.1 s** |
| `SELECT * FROM v_order_detail WHERE user_id=25`（纯数据库耗时） | **0.1 ms** |
| 城市对搜索 `scoped-direct`（纯数据库耗时） | **≈640 ms**（440k 行 `train_run_seat` 扇出聚合） |

同时 `SHOW STATUS` 显示 `Threads_running` 很低、`Max_used_connections` 只有 6、`max_connections=151`——**MySQL 本身并不忙**，CPU 全耗在反复创建进程上。

## 3. 根因

### 3.1 主因：每条 SQL 都 `docker exec` 起新进程

原 `mysql_rows` / `neo4j_rows` 的每一次调用都会执行：

```
docker exec mysql84 mysql -e "..."
```

也就是**每条语句 spawn 一个 `docker.exe` + 容器内 `mysql` 客户端进程**，Windows 下单次 130–230 ms 且被 Docker Desktop 串行化。前端按 1.5–2 s 的高频轮询，30 人叠加后每秒产生**数百次进程创建**，直接把机器打满。而查询本身几乎免费（0.1 ms）。

### 3.2 叠加因素

1. 城市对搜索 `scoped_direct_search` 本身约 640 ms，且结果页每 2 s 轮询一次，按人数线性放大。
2. `ThreadingHTTPServer` **每请求一个线程且无上限**，请求堆积时线程爆炸。
3. `SimpleHTTPRequestHandler` 默认 HTTP/1.0，**无 keep-alive**，每次轮询都重建连接。
4. AI 批量退票串行处理，每单 4–6 条 SQL，退 100 单 ≈ 400–600 次 `docker exec`。

## 4. 优化措施

### P0 数据库访问改为持久连接（收益最大）

新增 `app/db.py`：

- **PyMySQL 线程安全连接池**，`mysql_rows(sql, timeout)` 签名不变，100+ 处调用零改动。
- 用 `CLIENT.MULTI_STATEMENTS` 执行 `CALL ...; SELECT @var;` 多语句，遍历 `nextset()` 合并结果集，语义与原 `rows[-1]` 一致；会话变量同连接有效。
- 结果值归一化为与 `mysql --batch --raw` 相同的字符串形态（`datetime`/`Decimal`/`bytes`），保证既有 `json.dumps` 与 `int()/str()` 逻辑不回归。
- **Neo4j 改用官方 bolt 驱动**（`neo4j_rows` 签名不变）。
- 连接取自池前 `ping` 一次，坏连接自动丢弃重建，避免污染后续请求。
- 环境变量：`CR12306_MYSQL_HOST`(默认 `127.0.0.1`)、`CR12306_MYSQL_PORT`(`3307`)、`CR12306_MYSQL_USER`、`CR12306_MYSQL_PASSWORD`、`CR12306_DB`、`CR12306_MYSQL_POOL_SIZE`(默认 `16`)、`CR12306_NEO4J_URI`(`bolt://127.0.0.1:7687`)。
- 保留旧实现并通过 **`CR12306_DB_BACKEND=exec`** 一键回滚。

`app/server.py` 删除 `MYSQL_BASE`/`NEO4J_BASE`/`run_process`/本地 `mysql_rows`/`neo4j_rows`，改为 `from db import DatabaseError, mysql_rows, neo4j_rows`。

### P1 删除搜索热点放大

- `scoped/direct/transfer` 搜索结果加 **短 TTL 内存缓存**（`CR12306_SEARCH_CACHE_TTL`，默认 4 s，按请求 URL 作 key），相同查询并发只打一次库。
- 前端轮询降频并**在标签页隐藏时暂停**：
  - 结果页 `2000ms → 4000ms`；
  - 订单页 `1500ms → 3000ms`；
  - 候补通知 `5000ms → 8000ms`；
  - 管理端总览 `2000ms → 4000ms`；
  - 均加 `if(!document.hidden)` 守卫（`app.js`、`admin.js`）。

### P2 并发与协议

- `Handler.protocol_version = "HTTP/1.1"` 开启 keep-alive，`timeout = 30` 回收空闲连接。
- `BoundedThreadingHTTPServer`：用信号量把并发工作线程限制在 `CR12306_MAX_THREADS`（默认 64），突发时排队而不是无限建线程。
- 静态资源（`.css/.js/.png/...`）加 `Cache-Control: public, max-age=300`。
- `send_json` / 静态响应写入对 `BrokenPipe/ConnectionReset/ConnectionAborted` 做静默处理，消除客户端断连导致的整段 traceback。

### P4 数据库缓冲池

`docker-compose.yml` 为 MySQL 增加 `command: ["--innodb-buffer-pool-size=512M"]`（默认仅 128M，装不下 44 万行热点）。**需重启 mysql 容器生效**。

## 5. 验证结果

```
SELECT 1 单查询：         134–230 ms  →  ≈1 ms
轻接口 /api/waits、/api/orders： ~170 ms → 27–30 ms（含客户端开销，服务端 ≈1–3 ms）
/api/admin/overview（5 条 SQL）： ~1 s → 数十毫秒
scoped-direct 首查：       ~1.3 s（数据库真实成本）
scoped-direct 缓存命中：   ~0.3 s（其中多为 400KB JSON 序列化与客户端开销）
200 条常连接查询总计：     177 ms
```

启动后 `/api/health`、`/api/locations`、`/api/waits`、`/api/orders`、`/api/availability`、`scoped-direct`、静态资源、未登录 `overview` 返回 401 均正常。

## 6. 回滚

出现异常时设置：

```powershell
$env:CR12306_DB_BACKEND = 'exec'
```

即可回到原 `docker exec` 实现，无需改代码。缓冲池调整不影响回滚。

## 7. 遗留与后续

- `scoped_direct_search` 单查询约 640 ms 是**数据库本身的代价**，本次未改 SQL。若城市对搜索仍是热点，可考虑：为 `train_run_seat` 增加覆盖索引、重写聚合减少扇出、或对结果进一步精简字段。
- 换乘搜索（Neo4j 图查询）本身约 2.8 s，属于图查询代价，非本次优化范围。
- 生产化仍需连接池健康检查、限流、CSRF/TLS 与持久任务队列（见 `app/README.md` 结尾）。

## 8. 涉及文件

| 文件 | 变更 |
|---|---|
| `app/db.py` | 新增：MySQL 连接池 + Neo4j bolt + exec 回退 |
| `app/server.py` | 改用 `db` 模块；搜索缓存；HTTP/1.1；有界线程；静态缓存；断连静默 |
| `app/web/app.js` | 轮询降频 + 隐藏暂停 |
| `app/web/admin.js` | 总览轮询降频 + 隐藏暂停 |
| `docker-compose.yml` | MySQL `innodb_buffer_pool_size=512M` |
