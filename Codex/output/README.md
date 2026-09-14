# 长三角 12306 客票综合销售系统——交付索引

当前进度：`[███████████████████░] 95%`　[查看详细进度](PROJECT_PROGRESS.md)

本目录集中保存可提交、可评审的设计成果。数据库迁移脚本仍以 `database/migrations` 为唯一可执行源，已经执行的迁移禁止原地修改。

## 当前基线

- MySQL：基础铁路数据 + V002～V006 客票域、跨日时刻、区间位图库存、订单占座/支付/取消/超时/退款、乘车人行程冲突、A/B/C/D/F 位置偏好。
- Neo4j：`Station` 与 `TRAIN_SEGMENT` 运行图，只承担路径发现和候选车次组合，不参与库存扣减事务。
- 范围：长三角、单个运营日；允许列车跨过午夜，但通过 `day_offset` 归一为完整时间点。
- 运载量：已通过 V007 配置 3 种课程缩编模板、816 个模板座位和 440174 个运行席位；所有库存位图初始为 0。
- 核心一致性：MySQL 是订单、支付和库存的唯一事实源；位图的一位对应一个相邻运行区间。

## 文档目录

| 文档 | 内容 |
|---|---|
| [01-domain-model-design.md](design/01-domain-model-design.md) | 领域边界、核心实体和业务不变量 |
| [02-logical-schema-review.md](design/02-logical-schema-review.md) | 逻辑模型、约束、索引和 MySQL/Neo4j 分工 |
| [03-midnight-normalization-report.md](design/03-midnight-normalization-report.md) | 跨午夜时刻清洗规则与验证 |
| [04-v002-v003-execution-report.md](design/04-v002-v003-execution-report.md) | 客票域建表与运行实例初始化报告 |
| [05-v004-inventory-core-report.md](design/05-v004-inventory-core-report.md) | 区间位图、并发占座、支付与取消 |
| [06-v005-seat-position-report.md](design/06-v005-seat-position-report.md) | A/B/C/D/F 位置选择和余票兜底策略 |
| [07-order-lifecycle-design.md](design/07-order-lifecycle-design.md) | 行程冲突、超时释放与退款设计 |
| [08-capacity-and-encoding-design.md](design/08-capacity-and-encoding-design.md) | UTF-8 规范、课程缩编编组与具体座位容量 |
| [09-distance-fare-and-sale-design.md](design/09-distance-fare-and-sale-design.md) | 相邻区间里程估算、数据驱动票价与模拟开售 |
| [10-waitlist-fairness-design.md](design/10-waitlist-fairness-design.md) | 候补整单兑现、FIFO、有界跳过与崩溃恢复 |
| [11-query-architecture-and-execution.md](design/11-query-architecture-and-execution.md) | MySQL 直达余票、Neo4j 换乘候选与权威复核 |
| [12-web-application-design-and-execution.md](design/12-web-application-design-and-execution.md) | HTTP API、演示界面、安全边界与端到端验收 |

## 迁移执行顺序

`V002 → V003 → V004 → V005 → V006 → V007 → V008 → V009 → V010 → V011`

V006 已完成订单生命周期，V007 已完成容量配置。两者均先在隔离库验收再应用到 `CR12306`；对应执行前备份分别为 `database/backups/CR12306_pre_V006_20260908.sql` 和 `database/backups/CR12306_pre_V007_20260909.sql`。

## 下一步

1. 开展查询、位置选择、占座、支付、取消、超时、退款、候补的端到端并发压测。
2. 完成索引/锁分析和备份恢复演练。
3. 整理最终课程报告与演示脚本。
