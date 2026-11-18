# RailFlow 长三角智慧铁路演示系统

这是数据库课程项目的完整 Web 应用，前端不依赖构建工具，HTTP 服务只使用 Python 标准库。动态库存、订单生命周期、候补匹配、管理员认证、预付候补与订票削峰缓冲均调用 MySQL V002～V019 的真实表、视图和存储过程。

## 页面

- 用户订票端：<http://127.0.0.1:8080/>
  - 首次使用仅需姓名，浏览器会记住登录账户
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
  - 查看自动匹配的候补队列，以及监控数据库订票缓冲区

## 启动

推荐直接在项目根目录运行一键启动脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会自动启动 MySQL、Neo4j、Redis，检查迁移并寻找可用的 Python。当前这台电脑的 Python 位于 `C:\Users\Lenovo\.local\bin\python3.12.exe`，没有注册为 `python` 命令；一键脚本已经兼容这种情况。

手动升级已有数据库时依次执行：

```powershell
Get-Content database/migrations/V013__admin_auth_and_booking_buffer.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V014__wait_prepayment.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V015__add_g8359_extra_service.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V016__unify_demo_service_date.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V017__fast_itinerary_conflict_guard.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V018__fast_order_detail_view.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
Get-Content database/migrations/V019__move_demo_service_date_to_oct14.sql -Raw | docker exec -i mysql84 mysql --default-character-set=utf8mb4 -uroot -p123456 CR12306
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

数据库访问默认走**持久连接池**（`app/db.py`，PyMySQL，宿主 `127.0.0.1:3307`；Neo4j 走 bolt `127.0.0.1:7687`），不再对每条 SQL 执行 `docker exec`。可覆盖：

```powershell
$env:CR12306_DB_BACKEND = 'pool'          # pool（默认）| exec（旧实现，回滚用）
$env:CR12306_MYSQL_HOST = '127.0.0.1'
$env:CR12306_MYSQL_PORT = '3307'
$env:CR12306_MYSQL_POOL_SIZE = '16'
$env:CR12306_NEO4J_URI = 'bolt://127.0.0.1:7687'
$env:CR12306_MAX_THREADS = '64'
$env:CR12306_SEARCH_CACHE_TTL = '4'
```

此时 `CR12306_MYSQL_CONTAINER` / `CR12306_NEO4J_CONTAINER` 仅在 `CR12306_DB_BACKEND=exec` 时生效。

首次登录且 `admin_user` 为空时，服务会根据环境变量创建第一个管理员。未设置环境变量时，课程演示默认值为 `admin / RailFlow@123`，协作或展示前应修改密码配置并清理默认管理员。管理员密码使用 PBKDF2-SHA256 加盐保存，会话令牌只保存 SHA-256 摘要。

用户端“提交订单”先进入 `booking_request_buffer`，后台工作者通过数据库租约和 `FOR UPDATE SKIP LOCKED` 并行领取，再调用原有的 `sp_create_order_hold` 完成最终锁座。查询页每 2 秒静默同步区间余票，确认页提交前再次校验；即使页面快照短暂过期，存储过程仍会在行锁内二次检查并拒绝超卖。

候补请求提前付款。退款、取消预占或其他库存释放会立即按车次与席别触发定向候补匹配，后台线程还会每秒补偿扫描一次，负责外部库存变化、截止失败与自动退款。管理端只负责监控，不再需要人工点击开始匹配。

Redis 采用可选的 `LPUSH/BRPOP` 唤醒队列吸收瞬时请求并降低数据库空轮询；MySQL 缓冲表仍是唯一可靠队列。Redis 中的信号即使丢失，工作者也会自动回退为每 0.6 秒轮询 MySQL，不影响请求可靠性。

查询图可用 `& app/sync_query_graph.ps1` 重建。也可安装 `app/requirements.txt` 后运行 `python app/sync_query_graph.py`。

## 乘客行程助手

两端完整使用流程、数据库口径、模型配置和失败处理见 [AI 功能说明](../docs/AI功能说明.md)。

乘客端也提供独立的“我该怎么买？”行程助手。登录后可在首页输入“两个人从南通西到上海虹桥，下午3点前到，优先直达，可以换乘1次”。演示运行日为 2026-10-14。“可以换乘1次”会查询直达和一次同站换乘，两类各展示至多三条符合人数、到达时限和席别的路线，直达排在前面。“没票再换乘”只在查不到符合条件的直达票时查换乘。“不换乘”只查直达。起终点可以是城市或具体车站。选中方案后进入原有的单人、单段购票确认页。

助手默认使用本地中文规则。要使用模型理解自然语言，可在启动后端的同一个 PowerShell 7 窗口设置下面的环境变量。接口须兼容 Chat Completions 的函数调用（`tools` 和 `tool_choice`）。

```powershell
$env:CR12306_AI_API_KEY = Read-Host '输入模型 API Key' -MaskInput
$env:CR12306_AI_BASE_URL = 'https://api.openai.com/v1'
$env:CR12306_AI_MODEL = 'gpt-4o-mini'
.\start.ps1
```

若服务已在运行，请先在原服务终端按 Ctrl+C，再从配置窗口启动。其他兼容服务可替换地址和模型名。后端仅将本次输入及参数说明发给模型，密钥保存在服务进程环境中。模型提取行程条件，后端负责调用查询、筛选方案和计算金额。模型接口出错时页面会标明已切换为本地规则。可通过 `POST /api/travel-assistant` 提交 `{"question":"从南通西到上海虹桥"}` 检查当前模式和结果。

百炼 `deepseek-v4.1-flash-1017` 已完成两端真实联调，基础地址为 `https://dashscope.aliyuncs.com/compatible-mode/v1`。可将系统级 `DASHSCOPE_API_KEY` 读取到当前进程的 `CR12306_AI_API_KEY`。模型请求默认45秒超时，可通过 `CR12306_AI_TIMEOUT` 调整，百炼请求显式关闭思考模式。详细验收记录见上面的 AI 功能说明。

## 管理端功能

### 运营问答

管理员登录后打开「运营问答」，选择列车运营日并输入问题。可询问「G8359 哪个区间候补人数最多？这个区间的二等座还剩多少？」「订单状态分布」「G8359 已支付订单有多少笔？」「缓冲请求状态分布」。候补排行支持指定前 1 至 20 项。运营日指班次的出发日期，当前订单状态包含演示压测产生的订单。

问答使用受限的 NL2SQL。配置乘客助手使用的 `CR12306_AI_*` 后，模型根据报表视图和指标定义输出 SQL。后端仅执行与获准查询结构一致的参数化 SELECT；无 Key 时由本地语法规则生成 SQL。遇到越界 SQL 会尝试本地规则，无法识别的问题返回澄清。结果显示使用模式、作用范围、口径、数据、执行的 SQL 和绑定参数。查询时间上限为 4 秒，最多返回 20 行。

首次使用或从旧版升级时，在运行服务的 Python 环境执行 `python -m pip install -r app/requirements.txt`，以支持 MySQL 8 的账号认证。`start.ps1` 会安装 V020 报表视图和只读角色，并为当前服务端口创建专用 MySQL 读取账号。手动部署可先执行 V020，将角色 `railflow_ops_reports` 授予专用账号并设为默认角色，然后通过 `CR12306_OPS_DB_USER`、`CR12306_OPS_DB_PASSWORD` 提供凭据。读取报表使用独立连接和只读事务。

### 异常检测

管理台「异常检测」可按日期与车次核对席位占用位图、有效分配合并位图以及重叠分配。后台每5秒采样全库订票缓冲，连续3次覆盖10秒且排队数、最老等待均增长时告警。「检测并解释」可使用共用模型 API 生成辅助诊断，无 Key 或接口失败时提供本地解释。检测状态由规则计算。

「用模拟样本验证规则」展示独立的位图错误、重叠分配和积压证据。样本经相同规则判定，页面标明模拟数据。启动脚本会安装 V021 视图并授权现有只读角色，采样历史保存在服务内存，重启后重新积累。详细口径和验证步骤见 [AI 功能说明](../docs/AI功能说明.md)。

### 模拟订票员说明

AI 任务会创建独立模拟账户，并通过 `sp_create_order_hold`、`sp_confirm_order_payment` 和 `sp_create_wait_request` 操作真实演示库存。任务支持 1～500 名用户、1～30 个并发线程、随机/定向车票与自定义支付率。管理员可在同一页面查看每位 AI 乘客的具体订单，单独退票或按车次随机批量释放席位。数据会保留在数据库中，方便检查防超卖、退票回补、订单事件和候补队列；请勿连接生产数据库。

本项目为本机课程演示方案。生产环境还需加入认证授权、连接池健康检查与限流、CSRF/TLS、持久任务队列与密钥管理。查询延迟与并发优化的完整分析与实测见 `docs/design/14-query-latency-optimization.md`。
