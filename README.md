# 12306 铁路售票数据库系统

数据库系统课程项目 —— 基于 MySQL 的 12306 铁路售票系统。

## 项目结构

```
12306/
├── db-init/              # Docker 数据库初始化 SQL
│   └── CR12306.sql       # 完整数据库导出（含表结构+数据）
├── database/             # 数据库迁移脚本
│   ├── migrations/       # 版本迁移 SQL（V002 ~ V006）
│   ├── backups/          # 迁移前备份
│   └── tests/            # 验收测试
├── 代码/                 # 项目代码
│   ├── mysql2neo4j.py    # MySQL → Neo4j 数据导入
│   └── railway_visualization.py
├── 铁路数据集/           # 铁路相关数据集与可视化
├── 论文/                 # 设计论文
└── Codex/                # 设计文档
```

## 快速开始（Windows）

先安装并打开 Docker Desktop，再在项目根目录双击 `start.cmd`，或在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

脚本会自动完成：

1. 启动 Docker Desktop；
2. 创建或启动 MySQL 8.4、Neo4j 5.26 和 Redis 7.4；
3. 首次运行时依次执行 V002～V013 数据库迁移；
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
