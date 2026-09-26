# 12306 铁路售票数据库系统

数据库系统课程项目 —— 基于 MySQL 的 12306 铁路售票系统。

## 项目结构

```
12306/
├── app/                  # Python 服务、用户端和独立管理端
├── database/             # V002～V015 迁移、验收脚本和备份
├── db-init/              # Docker 首次初始化 SQL
├── docs/                 # 运行说明、设计文档、理论分析和论文
├── 代码/                 # MySQL → Neo4j 与数据可视化工具
├── 铁路数据集/           # 原始铁路数据与辅助项目
├── docker-compose.yml    # MySQL、Neo4j、Redis
├── start.cmd             # Windows 双击启动入口
└── start.ps1             # 完整启动与迁移脚本
```

文档统一入口见 [docs/README.md](docs/README.md)。

## 快速开始（Windows）

先安装并打开 Docker Desktop，再在项目根目录双击 `start.cmd`，或在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会自动完成：

1. 启动 Docker Desktop；
2. 创建或启动 MySQL 8.4、Neo4j 5.26 和 Redis 7.4；
3. 首次运行时依次执行 V002～V015 数据库迁移；
4. 必要时从 MySQL 重建 Neo4j 查询图；
5. 自动寻找本机 Python 3 并启动 Web 服务。

启动完成后访问：

- 用户端：<http://127.0.0.1:8080/>
- 管理端：<http://127.0.0.1:8080/admin-login.html>
- 首次管理员：`admin / RailFlow@123`

如果 8080 被占用：

```powershell
.\start.ps1 -Port 8090
```

如果暂时不想启动 Redis：

```powershell
.\start.ps1 -NoRedis
```

Redis 只是瞬时流量的唤醒与加速层；订单请求会先持久化到 MySQL 的 `booking_request_buffer`，所以 Redis 不可用时系统会自动退回 MySQL 轮询，不会丢失订单。

## 已实现能力

- 城市/车站两级搜索、实时区间余票和按时间排序；
- 位图库存、防超卖、偏好选座、订单支付与退票；
- 预付候补、库存释放后自动匹配及失败退款；
- “我的订单”查看动态电子车票；
- 独立登录的运营控制台、库存座位图和 AI 订票压测；
- MySQL 持久化缓冲区、Redis 唤醒加速和 Neo4j 路径查询。

## 协作方式

1. Clone 本仓库
2. 创建新分支：`git checkout -b your-name/feature`
3. 提交更改并推送
4. 发起 Pull Request

## 技术栈

- MySQL 8.4
- Neo4j 5.26
- Redis 7.4（可选加速层）
- Docker
- Python 3.11+
