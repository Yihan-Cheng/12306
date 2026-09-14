# RailFlow 长三角智慧铁路演示系统

这是数据库课程项目的完整 Web 应用，前端不依赖构建工具，HTTP 服务只使用 Python 标准库。动态库存、订单生命周期与候补匹配均调用 MySQL V002～V011 的真实表、视图和存储过程。

## 页面

- 用户订票端：<http://127.0.0.1:8080/>
  - 直达与一次换乘查询
  - 实时区间余票、座位偏好、经停时刻
  - 演示账户、占座、支付、取消、退款与候补
- 管理控制台：<http://127.0.0.1:8080/admin.html>
  - 运营总览与实时审计事件
  - 车次、车厢、席别和位图占用监控
  - 订单流水、乘客档案与候补公平队列
  - AI 订票员随机压测与指定车次/席别定向压测

## 启动

确保 MySQL 与 Neo4j 容器正在运行，并已执行 V002～V011：

```powershell
python app/server.py
```

默认适配当前课程环境：MySQL 容器 `mysql84`、root 密码 `123456`，Neo4j 容器 `neo4j-12306`、密码 `12345678`。不同环境可覆盖：

```powershell
$env:CR12306_MYSQL_CONTAINER = 'cr12306-mysql'
$env:CR12306_MYSQL_PASSWORD = 'root123'
$env:CR12306_NEO4J_CONTAINER = 'neo4j-12306'
$env:CR12306_NEO4J_PASSWORD = 'your-password'
$env:CR12306_DB = 'CR12306'
$env:CR12306_PORT = '8080'
python app/server.py
```

查询图可用 `& app/sync_query_graph.ps1` 重建。也可安装 `app/requirements.txt` 后运行 `python app/sync_query_graph.py`。

## AI 订票员说明

AI 任务会创建独立模拟账户，并通过 `sp_create_order_hold`、`sp_confirm_order_payment` 和 `sp_create_wait_request` 操作真实演示库存。任务支持 1～500 名用户、1～30 个并发线程、随机/定向车票与自定义支付率。数据会保留在数据库中，方便检查防超卖、订单事件和候补队列；请勿连接生产数据库。

本项目为本机课程演示方案。生产环境还需加入认证授权、连接池、CSRF/TLS、速率限制、持久任务队列与密钥管理。
