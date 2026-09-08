# 长三角 12306 客票综合销售系统——交付索引

本目录集中保存可提交、可评审的设计成果。数据库迁移脚本仍以 `database/migrations` 为唯一可执行源，已经执行的迁移禁止原地修改。

## 当前基线

- MySQL：基础铁路数据 + V002～V006 客票域、跨日时刻、区间位图库存、订单占座/支付/取消/超时/退款、乘车人行程冲突、A/B/C/D/F 位置偏好。
- Neo4j：`Station` 与 `TRAIN_SEGMENT` 运行图，只承担路径发现和候选车次组合，不参与库存扣减事务。
- 范围：长三角、单个运营日；允许列车跨过午夜，但通过 `day_offset` 归一为完整时间点。
- 运载量：尚未配置。编组、车厢、席位及 `train_run_seat` 数据待后续单独设置。
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

## 迁移执行顺序

`V002 → V003 → V004 → V005 → V006`

V006 已先在隔离数据库完成语法、状态机、幂等性及位图对账验证，再应用到 `CR12306`。应用前备份为 `database/backups/CR12306_pre_V006_20260908.sql`。容量数据不属于 V006，应用后正式库的编组、席位和订单行数仍均为 0。

## 下一步

1. 共同确定不同车型/席别的简化运载量，建立编组与具体席位。
2. 生成票价与可售运行实例，开展端到端并发测试。
3. 实现候补整单兑现，再评估是否需要更复杂的跳过与老化策略。
