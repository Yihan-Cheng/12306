# V005 ABCDF 座位位置偏好实施报告

> 执行日期：2026-09-07  
> 目标：Docker `mysql84` / `CR12306`  
> 结果：成功  
> 正式库新增测试数据：0

## 1. 业务规则

- 座席位置代码为 `A/B/C/D/F`，没有 E；
- 用户可以不选位置，此时系统自动分配；
- 用户可以选择 A、B、C、D 或 F；
- 所选位置存在全程可用席位时优先满足；
- 所选位置无票且允许兜底时，从其他全程可用席位中分配；
- 所选位置无票且禁止兜底时，返回 `ORDER_PREFERRED_POSITION_UNAVAILABLE`；
- 多人订单继续遵守整单成功或整单回滚。

## 2. 为什么不用随机分配

兜底策略没有使用 `ORDER BY RAND()`，因为随机结果：

- 不利于重现和解释分配结果；
- 并发测试难以稳定复现；
- 可能把许多完整空闲席位切成碎片；
- 大数据量下排序成本更高。

V005 使用确定性的库存感知顺序：

1. 优先匹配请求位置；
2. 兜底或自动分配时，优先复用已有占用但与本次区间不重叠的席位；
3. 再按已占 bit 数量由多到少选择；
4. 最后按 `seat_id` 确定性排序。

这样会尽量把短区间集中在较少席位上，保留更多完全空闲席位供长区间乘客使用。

## 3. 数据结构变化

`order_item` 新增：

- `requested_position_code`；
- `allow_position_fallback`。

`seat_allocation` 新增：

- `allocated_position_code`；
- `allocation_strategy`。

分配策略取值：

- `PREFERRED`：实际位置等于用户所选位置；
- `FALLBACK_INVENTORY`：所选位置无票，按余票兜底；
- `AUTO_INVENTORY`：用户没有指定位置。

新增 `sp_query_position_availability`，按 A、B、C、D、F 返回指定 OD 的精确位置余票。

## 4. 新版占座接口

`sp_create_order_hold` 增加两个参数：

```text
p_position_code             NULL / A / B / C / D / F
p_allow_position_fallback   TRUE / FALSE
```

V004 尚未接入应用调用方，所以 V005 可以安全升级过程签名。

## 5. 临时库测试结果

测试编组为一排五席：A、B、C、D、F。

| 场景 | 结果 |
|---|---|
| 选择 A，A 可用 | 分配 A，策略 `PREFERRED` |
| 再次选择 A，允许兜底 | 分配 B，策略 `FALLBACK_INVENTORY` |
| 选择 F，禁止兜底，F 可用 | 分配 F，策略 `PREFERRED` |
| 不选位置，A 的后续区间可复用 | 分配 A，策略 `AUTO_INVENTORY` |
| F 已占用，选择 F 且禁止兜底 | 明确失败，不产生订单 |
| 重复相同位置偏好和幂等键 | 返回原订单 |
| 取消 A 的前半区间 | 只清除对应 bit，后半区间保留 |

库存和订单金额对账差异均为 0。

## 6. 正式库状态

- V005 已执行；
- `sp_create_order_hold` 已升级为 11 个参数；
- 已安装 `sp_query_position_availability`；
- `seat`、`ticket_order`、`seat_allocation`、`payment` 仍全部为空；
- 没有提前生成编组和运载量。

## 7. 备份与校验

迁移前备份：`database/backups/CR12306_pre_V005_20260907.sql`

- 大小：931,822 字节；
- SHA-256：`8A65E9B9C09CC172590D0A41ADE92850318F0A5466597942F650CBC480901654`。

V005 SQL SHA-256：

`4CA754DDB95B0C373F02ACDFE6B2DA18B363FCDF78B093CAAF44DA2B15D76DCD`

V005 执行后视为不可变迁移。

