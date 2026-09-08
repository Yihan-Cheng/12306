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

## 快速开始

### 1. 使用 Docker 初始化数据库

```bash
# 拉取 MySQL 镜像并导入数据
docker run -d \
  --name cr12306-mysql \
  -e MYSQL_ROOT_PASSWORD=your_password \
  -p 3306:3306 \
  -v $(pwd)/db-init/CR12306.sql:/docker-entrypoint-initdb.d/CR12306.sql \
  mysql:8.4
```

> Windows PowerShell 用户将 `$(pwd)` 替换为 `${PWD}`

### 2. 运行迁移脚本（可选）

按顺序执行 `database/migrations/` 下的 SQL 文件。

## 协作方式

1. Clone 本仓库
2. 创建新分支：`git checkout -b your-name/feature`
3. 提交更改并推送
4. 发起 Pull Request

## 技术栈

- MySQL 8.4
- Docker
- Python 3
