# V006 订单生命周期设计与执行报告

## 1. 本阶段范围

本阶段补齐三个直接影响库存正确性的能力：同一乘车人的时间冲突检查、未支付订单的批量超时释放、已支付订单退款释放。它不创建编组、车厢或座位，也不设置列车运载量。

## 2. 乘车人行程冲突

### 业务不变量

同一 `passenger_id` 不能同时持有时间相交的 `HELD` 或 `CONFIRMED` 车票。采用半开区间 `[departure_at, arrival_at)`：前一行程到达时间恰好等于后一行程发车时间时不冲突。

### 数据库实现

在 `order_item` 插入前执行触发器：

1. 对 `passenger` 主键行执行 `SELECT ... FOR UPDATE`，把同一乘车人的并发下单串行化；
2. 从 `v_train_run_stop` 读取新行程的完整起止时间；
3. 使用 `existing_departure < new_arrival AND existing_arrival > new_departure` 检查有效订单项；
4. 冲突时抛出 `PASSENGER_ITINERARY_CONFLICT`，整个占座事务回滚，已置位的库存也随事务恢复。

仅依赖“先查询再插入”无法阻止两个并发事务同时通过检查，因此必须有乘车人级锁。课程项目规模下该锁粒度足够小，也比维护额外的时间范围锁表更清晰。

## 3. 支付超时释放

`sp_expire_order_holds(batch_size, expired_count)` 每次领取有限数量的到期订单，并使用 `FOR UPDATE SKIP LOCKED` 支持多个清理工作者互不等待。处理过程全部位于一个事务：

- 锁定到期的 `PENDING_PAYMENT` 订单；
- 锁定对应 `HOLD` 分配及 `train_run_seat`；
- 清除每条分配占用的区间位；
- 分配改为 `RELEASED`，订单项改为 `TIMEOUT`，订单改为 `TIMEOUT`；
- 写入不可变的库存事件和订单事件。

过程按 `(run_id, seat_id, allocation_id)` 固定顺序加锁，以降低死锁概率。再次执行不会重复释放，因为终态订单和分配不再符合领取条件。

## 4. 退款

新增 `refund` 表记录退款请求事实，`refund_request_no` 提供接口幂等性。`sp_refund_paid_order` 只接受当前用户拥有的 `PAID` 订单；同一退款请求号重放时返回原退款记录。

退款成功事务同时完成：释放所有 `CONFIRMED` 区间、订单项转为 `REFUNDED`、订单转为 `REFUNDED`、原成功支付转为 `REFUNDED`、追加退款/库存/订单审计记录。课程项目暂不模拟第三方支付异步退款，因此一次事务内记录成功；后续如接入真实支付渠道，应扩展为 `REQUESTED → PROCESSING → SUCCESS/FAILED` 状态机，且只在退款成功后释放票额。

## 5. 与位置偏好的关系

位置偏好只影响首次分配：

- 指定 A/B/C/D/F 且有满足条件的余票：分配该位置；
- 无指定位置或允许兜底：按现有余票进行确定性分配；
- 指定位置无票且禁止兜底：下单失败。

超时或退款释放的是既有 `segment_mask`，与位置字母无关。释放后的席位自然重新参与下一次位置选择和候补匹配。

## 6. 一致性与验收标准

- 任意时刻 `v_inventory_reconciliation.is_consistent = 1`；
- 超时过程重复执行，第二次 `expired_count = 0`；
- 同一退款请求重放只产生一条退款记录，不重复清位；
- 两个并发事务不能为同一乘车人建立时间重叠的有效票；
- 审计事件中的 `mask_before`、`segment_mask`、`mask_after` 可还原每次变化；
- V006 执行前后正式库的编组和席位数量保持不变。

## 7. 执行结果（2026-09-08）

V006 已在 MySQL 8.4 完成以下验证后应用到正式库：

| 验收项 | 结果 |
|---|---|
| 建表、触发器、存储过程编译 | 通过 |
| 已确认行程与新行程时间重叠 | 拒绝，失败订单整体回滚 |
| 退款首次执行 | 订单、订单项、支付与分配进入正确终态，位图释放 |
| 同一退款请求号重放 | 返回相同 `refund_id`，不重复释放 |
| 已退款后购买不重叠的相邻区段 | 允许 |
| 到期订单首次批量清理 | `expired_count = 1` |
| 到期任务重放 | `expired_count = 0` |
| 位图对账 | 不一致记录为 0 |
| 正式库空批次清理 | `expired_count = 0` |
| 正式库容量与交易数据 | 编组 0、席位 0、运行席位 0、订单 0 |

可重复验收脚本位于 `database/tests/V006__order_lifecycle_acceptance.sql`，只允许在隔离测试库执行。正式迁移位于 `database/migrations/V006__order_lifecycle.sql`，迁移前备份位于 `database/backups/CR12306_pre_V006_20260908.sql`。
