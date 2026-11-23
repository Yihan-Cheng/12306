# CR12306 文档中心

项目运行代码与数据库脚本保留在根目录的 `app/`、`database/` 和 `db-init/`；所有说明性材料集中在本目录。

| 目录 / 文档 | 内容 |
|---|---|
| [运行说明.md](运行说明.md) | Windows 一键启动、访问地址与故障排查 |
| [AI功能说明.md](AI功能说明.md) | 乘客出行助手、运营组合分析、AI 订票员、异常诊断与模型配置 |
| [AI功能完整API输入输出.md](AI功能完整API输入输出.md) | 当前接口增量、查询计划示例和 10 组真实调用的历史报文 |
| [课堂公网演示.md](课堂公网演示.md) | Cloudflare Quick Tunnel 公网开放、课堂当天 Runbook |
| [课堂技术演示.md](课堂技术演示.md) | 指定区间预留少量余票、全班抢票、退票兑现候补的操作流程 |
| [课堂演示手动Runbook.md](课堂演示手动Runbook.md) | 70 人抢 10 张票的课前设置、台上点击顺序和异常处理 |
| [课堂测试后优化全过程（图文）](design/14-query-latency-optimization.md) | 排查、优化实现、历史耗时对比、验证边界及报告素材 |
| [design/](design/) | 数据库与应用各阶段设计、执行和验收报告 |
| [theory/](theory/) | 数据库视角项目分析与高级数据库知识说明 |
| [paper/](paper/) | 课程设计论文 |
| [references/](references/) | 初始界面参考图片 |

数据库迁移以根目录 `database/migrations/` 为唯一可执行来源，文档中的 SQL 仅作设计说明。
