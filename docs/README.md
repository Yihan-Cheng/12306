# CR12306 文档中心

项目运行代码与数据库脚本保留在根目录的 `app/`、`database/` 和 `db-init/`；所有说明性材料集中在本目录。

| 目录 / 文档 | 内容 |
|---|---|
| [运行说明.md](运行说明.md) | Windows 一键启动、访问地址与故障排查 |
| [课堂公网演示.md](课堂公网演示.md) | Cloudflare Quick Tunnel 公网开放、课堂当天 Runbook |
| [课堂技术演示.md](课堂技术演示.md) | 指定区间预留少量余票、全班抢票、退票兑现候补的操作流程 |
| [课堂演示手动Runbook.md](课堂演示手动Runbook.md) | 70 人抢 10 张票的课前设置、台上点击顺序和异常处理 |
| [design/](design/) | 数据库与应用各阶段设计、执行和验收报告 |
| [theory/](theory/) | 数据库视角项目分析与高级数据库知识说明 |
| [paper/](paper/) | 课程设计论文 |
| [references/](references/) | 初始界面参考图片 |

数据库迁移以根目录 `database/migrations/` 为唯一可执行来源，文档中的 SQL 仅作设计说明。
