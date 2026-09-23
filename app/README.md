# RailFlow 长三角智慧铁路演示系统

这是数据库课程项目的完整 Web 应用，前端不依赖构建工具，HTTP 服务只使用 Python 标准库。动态库存、订单生命周期、候补匹配、管理员认证与订票削峰缓冲均调用 MySQL V002～V013 的真实表、视图和存储过程。

## 页面

- 用户订票端：<http://127.0.0.1:8080/>
  - 首次使用仅需姓名和密码，浏览器会记住登录账户
  - 城市/车站两级选择；选择城市时自动覆盖该城市全部车站
  - 车次按出发时间排列，同车次席别合并，并准确标注始发、途经和终到
  - 确认页选择席别、乘车人和座位位置，提交后直接完成支付确认
  - 偏好席位不足时自动从其他空闲位置分配，并向用户显示兜底提示
- 管理控制台：<http://127.0.0.1:8080/admin.html>
  - 独立管理员登录入口：<http://127.0.0.1:8080/admin-login.html>
  - 管理接口使用服务端数据库会话与 HttpOnly Cookie，乘客端无法直接调用
  - 运营总览与实时审计事件
  - 车次、车厢、席别和位图占用监控
  - 订单流水、乘客档案与候补公平队列
  - AI 订票员随机压测与指定车次/席别定向压测
  - 按 AI 乘客精确退票/取消预占，或按车次随机批量退票
  - 查看候补队列、手动触发公平兑现，以及监控数据库订票缓冲区

## 启动

推荐直接在项目根目录运行一键启动脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会自动启动 MySQL、Neo4j、Redis，检查迁移并寻找可用的 Python。当前这台电脑的 Python 位于 `C:\Users\Lenovo\.local\bin\python3.12.exe`，没有注册为 `python` 命令；一键脚本已经兼容这种情况。

手动升级已有数据库时可执行：

```powershell
Get-Content database/migrations/V013__admin_auth_and_booking_buffer.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
```

再启动服务：

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
$env:CR12306_ADMIN_USER = 'admin'
$env:CR12306_ADMIN_PASSWORD = '请改成至少8位的强密码'
$env:CR12306_BOOKING_WORKERS = '2'
$env:CR12306_REDIS_ENABLED = '1'
$env:CR12306_REDIS_HOST = '127.0.0.1'
python app/server.py
```

首次登录且 `admin_user` 为空时，服务会根据环境变量创建第一个管理员。未设置环境变量时，课程演示默认值为 `admin / RailFlow@123`，协作或展示前应修改密码配置并清理默认管理员。管理员密码使用 PBKDF2-SHA256 加盐保存，会话令牌只保存 SHA-256 摘要。

用户端“提交订单”先进入 `booking_request_buffer`，后台工作者通过数据库租约和 `FOR UPDATE SKIP LOCKED` 并行领取，再调用原有的 `sp_create_order_hold` 完成最终锁座。查询页与确认页均会重新读取实时区间余票；即使页面快照过期，存储过程仍会在行锁内二次检查并拒绝超卖。

Redis 采用可选的 `LPUSH/BRPOP` 唤醒队列吸收瞬时请求并降低数据库空轮询；MySQL 缓冲表仍是唯一可靠队列。Redis 中的信号即使丢失，工作者也会自动回退为每 0.6 秒轮询 MySQL，不影响请求可靠性。

查询图可用 `& app/sync_query_graph.ps1` 重建。也可安装 `app/requirements.txt` 后运行 `python app/sync_query_graph.py`。

## AI 订票员说明

AI 任务会创建独立模拟账户，并通过 `sp_create_order_hold`、`sp_confirm_order_payment` 和 `sp_create_wait_request` 操作真实演示库存。任务支持 1～500 名用户、1～30 个并发线程、随机/定向车票与自定义支付率。管理员可在同一页面查看每位 AI 乘客的具体订单，单独退票或按车次随机批量释放席位。数据会保留在数据库中，方便检查防超卖、退票回补、订单事件和候补队列；请勿连接生产数据库。

本项目为本机课程演示方案。生产环境还需加入认证授权、连接池、CSRF/TLS、速率限制、持久任务队列与密钥管理。
