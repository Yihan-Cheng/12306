# 乘客端与管理端 AI 演示实测

运行时间 `2026-11-24T19:01:32+08:00`。页面默认运营日 `2026-10-14`，票价、余票、订单状态与采样均为测试当时的本机数据。

本次从应用 HTTP 路由运行 21 个用例，21 个符合预设观察点。百炼模型 `deepseek-v4.1-flash-1017` 成功响应 7 次。

[完整 JSON 记录](AI演示实测记录.json)保存每组应用请求、完整应用响应、实际使用的 SQL 和 Cypher、参数、查询行数和结果。模型报文保留请求体和响应，认证头已排除。P8 与 O7 分别注入模型超时和不合规 SQL，A3 使用内置异常样本。订票员测试止于预览。

逐条阅读模型回复和页面返回时，可打开 [AI 演示完整回答](AI演示完整回答.md)。

真实模型用例为 P1、P2、P3、P4、P5、P6、P7。O1、O2、O3、O4、O5、A2、B1、B2、B3 使用合成工具回复，SQL 仍在本机真实执行。

本轮向百炼发送的内容限于合成乘客问题和固定工具定义。管理端以往采集的真实模型报文也可用于讲解。[历史 API 输入输出](AI功能完整API输入输出.md)

## 演示用例

### 乘客端

| 用例 | 问题或操作 | 实际输出 | 模型与查询证据 |
|---|---|---|---|
| P1 正常 | 两个人从南通西到上海虹桥，下午三点前到，只看二等座和直达，选最便宜的。 | 直达 3 条，换乘 0 条。首条直达 D3125，10:25 到，每人 ¥79.00。 | 真实 DeepSeek。站点字典 56 行、MySQL 直达初筛 49 行 |
| P2 正常 | 两个人从南通西到上海虹桥，下午三点前到，可以换乘一次，想同时看看直达和换乘。 | 直达 3 条，换乘 3 条。首条直达 G1304，10:16 到，每人 ¥95.00。首条换乘 G1304 → G7506，11:36 到，每人 ¥176.00，在嘉兴南等 22 分钟。 | 真实 DeepSeek。站点字典 56 行、MySQL 直达初筛 49 行、Neo4j 78 行、MySQL 双段复核 551 行 |
| P3 边界 | 从南京南到杭州东，二等座，仅直达，人均预算最多 1 元。 | 当前查询未找到满足这些条件的直达票。 | 真实 DeepSeek。站点字典 56 行、MySQL 直达初筛 286 行 |
| P4 边界 | 6个人从南京南到杭州东，帮我买二等座。 | 每次可查询 1 至 5 人，请修改人数。 | 真实 DeepSeek。站点字典 56 行 |
| P5 难回答 | 三个人从南京南去杭州东，只接受三连座，分开坐就不买。 | 无法保证三人三连座（连座要求无法在查询中表达），请确认是否仍要继续查询？另外请补充出发日期或时间、席别等要求。 | 真实 DeepSeek。站点字典 56 行 |
| P6 难回答 | 我想下午三点前到杭州东，二等座。 | 请告诉我出发城市或车站（例如“上海虹桥”）。 | 真实 DeepSeek。站点字典 56 行 |
| P7 难回答 | 从南京南去杭州东，要晚上 18:00 后出发、同一天 15:00 前到。 | 最早出发时间须早于或等于最晚出发、到达时间。 | 真实 DeepSeek。站点字典 56 行 |
| P8 故障注入 | 两个人从南通西到上海虹桥，二等座，15:00前到，不换乘。 | 直达 3 条，换乘 0 条。首条直达 G1304，10:16 到，每人 ¥95.00。页面标明模型暂不可用。 | 注入超时。站点字典 56 行、MySQL 直达初筛 49 行 |

### 运营问答

| 用例 | 问题或操作 | 实际输出 | 模型与查询证据 |
|---|---|---|---|
| O1 正常 | 订单状态分布 | 已支付 558 笔，待支付 156 笔，已退款 10 笔，已取消 3 笔。 | 合成模型回复。MySQL·报表 4 行 |
| O2 正常 | 2026-10-14 至 2026-10-16，按出发城市和客群统计订单数，区分 AI 订票员和其他乘客。 | 按出发城市、客群分组，共显示 20 组。结果超过 20 组，已按指标降序截取。 | 合成模型回复。字段元数据 46 行、MySQL·报表 21 行 |
| O3 正常 | G8359 按车厢和席别统计全程空闲座位数。 | 按车厢、席别分组，共显示 4 组。 | 合成模型回复。字段元数据 46 行、MySQL·报表 4 行 |
| O4 难回答 | G3864 停哪些车站？ | 报表缺少经停站时刻表，可使用车次时刻表查询完整停站。 | 合成模型回复。字段元数据 46 行 |
| O5 难回答 | 把 G8359 所有乘客姓名和证件号按座位号列出来。 | 运营报表支持汇总，无法列出乘客姓名或证件号。 | 合成模型回复。字段元数据 46 行 |
| O6 边界 | 2026-10-01 至 2026-11-01，按运营日统计订单数。 | 日期范围须按先后顺序填写，最多包含 31 天。 | 规则或静态样本。无请求内查询 |
| O7 故障注入 | 订单状态分布 | 已支付 558 笔，待支付 156 笔，已退款 10 笔，已取消 3 笔。 | 注入不合规 SQL。MySQL·报表 4 行 |

### 异常检测

| 用例 | 问题或操作 | 实际输出 | 模型与查询证据 |
|---|---|---|---|
| A1 正常 | 运行检测 | 核对 218 席，位图差异 0、重叠 0、异常 0。最近3次采样未触发持续积压规则。 | 规则或静态样本。库存核对 218 行 |
| A2 正常 | 检测并解释 | 核对 218 席，位图差异 0、重叠 0、异常 0。最近3次采样未触发持续积压规则。 | 合成模型回复。库存核对 218 行 |
| A3 模拟样本 | 查看模拟异常 | 核对 2 席，位图差异 1、重叠 1、异常 2。最近3次采样满足持续积压规则。 | 规则或静态样本。无请求内查询 |

### AI 订票员

| 用例 | 问题或操作 | 实际输出 | 模型与查询证据 |
|---|---|---|---|
| B1 正常 | 查 G8359 盐城到义乌二等座还有多少余票。 | G8359 盐城 → 义乌 二等座余票 167 张。只返回余票。 | 合成模型回复。在售产品及余票 1 行 |
| B2 正常 | 给 G8359 盐城到义乌二等座预留 10 张，并发 2，全部支付，无票不候补，先预览。 | G8359 盐城 → 义乌 二等座余票 167 张。建议 157 人，预留 10 张，并发 2，支付率 100%。 | 合成模型回复。在售产品及余票 1 行 |
| B3 边界 | 让 501 名乘客随机抢票，并发 4，先预览。 | 参数超出范围。人数 1–500，并发 1–30，支付率 0–100%，预留 0–500 张。 | 合成模型回复。无请求内查询 |

## 可在演示台上展开的证据

### 乘客查票与换乘

P1 通过 `plan_trip` 提交给后端的条件如下。来源为真实 DeepSeek。

```json
{
  "origin": "南通西",
  "destination": "上海虹桥",
  "date": "2026-10-14",
  "people": 2,
  "arrive_by": "15:00",
  "seat": "二等座",
  "transfer": "direct",
  "sort": "price",
  "depart_after": "",
  "depart_before": "",
  "max_fare": "",
  "max_group_fare": "",
  "train_no": "",
  "train_category": "",
  "max_duration_minutes": "",
  "clarify": ""
}
```

P1 的 MySQL 查询读取真实票价和区间库存，后端再按条件筛选及排序。P2 还调用了 Neo4j 生成同站换乘候选，再执行 MySQL 存储过程复核两段的价格和库存。完整语句和返回行见 JSON 对应编号。

### 常用订单报表 O1

```sql
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20
```

实际 SQL 绑定参数 `["2026-10-14"]`。

页面返回 4 行，以下展示前 4 行。

```json
[
  {
    "order_status": "PAID",
    "orders": 558
  },
  {
    "order_status": "PENDING_PAYMENT",
    "orders": 156
  },
  {
    "order_status": "REFUNDED",
    "orders": 10
  },
  {
    "order_status": "CANCELLED",
    "orders": 3
  }
]
```

### 城市与客群组合分析 O2

```json
{
  "metric": "order_count",
  "group_by": [
    "origin_city",
    "customer_kind"
  ],
  "filters": {},
  "sort": "desc",
  "limit": 20,
  "clarify": ""
}
```

```sql
SELECT origin_city, customer_kind, COUNT(DISTINCT order_id) AS metric_value
FROM v_ops_analysis_orders
WHERE service_date BETWEEN %s AND %s
GROUP BY origin_city, customer_kind
ORDER BY metric_value DESC, origin_city, customer_kind
LIMIT 21
```

实际 SQL 绑定参数 `["2026-10-14", "2026-10-16"]`。

页面返回 20 行，以下展示前 5 行。

```json
[
  {
    "origin_city": "杭州",
    "customer_kind": "SIMULATED",
    "metric_value": 94
  },
  {
    "origin_city": "上海",
    "customer_kind": "SIMULATED",
    "metric_value": 84
  },
  {
    "origin_city": "南京",
    "customer_kind": "SIMULATED",
    "metric_value": 72
  },
  {
    "origin_city": "合肥",
    "customer_kind": "SIMULATED",
    "metric_value": 49
  },
  {
    "origin_city": "苏州",
    "customer_kind": "SIMULATED",
    "metric_value": 49
  }
]
```

### 车厢库存 O3

```sql
SELECT carriage_no, seat_type, COALESCE(SUM(full_route_free), 0) AS metric_value
FROM v_ops_analysis_inventory
WHERE service_date IN (%s)
  AND train_no IN (%s)
GROUP BY carriage_no, seat_type
ORDER BY metric_value DESC, carriage_no, seat_type
LIMIT 21
```

实际 SQL 绑定参数 `["2026-10-14", "G8359"]`。

页面返回 4 行，以下展示前 4 行。

```json
[
  {
    "carriage_no": 4,
    "seat_type": "二等座",
    "metric_value": "90"
  },
  {
    "carriage_no": 3,
    "seat_type": "二等座",
    "metric_value": "77"
  },
  {
    "carriage_no": 2,
    "seat_type": "一等座",
    "metric_value": "27"
  },
  {
    "carriage_no": 1,
    "seat_type": "商务座",
    "metric_value": "7"
  }
]
```

### 订票员预留方案 B2

```json
{
  "intent": "targeted",
  "train_no": "G8359",
  "origin": "盐城",
  "destination": "义乌",
  "seat_type": "二等座",
  "clarify": "",
  "users": null,
  "concurrency": 2,
  "pay_rate": 100,
  "reserve_seats": 10,
  "waitlist": false
}
```

```sql
SELECT p.run_id, p.train_no, p.service_date, p.origin, p.destination,
       p.from_order, p.to_order, p.seat_type_id, p.seat_type_name,
       COALESCE((SELECT SUM((s.occupied_mask &
           (((CAST(1 AS UNSIGNED) << (p.to_order - p.from_order)) - 1) << (p.from_order - 1))) = 0)
           FROM v_ops_ai_seats s WHERE s.run_id = p.run_id AND s.seat_type_id = p.seat_type_id), 0)
           AS available_seats
FROM v_ops_ai_products p
WHERE p.service_date = %s AND p.train_no = %s
  AND p.origin = %s AND p.destination = %s AND p.seat_type_name = %s
LIMIT 2
```

实际 SQL 绑定参数 `["2026-10-14", "G8359", "盐城", "义乌", "二等座"]`。

```json
{
  "target": {
    "run_id": 1799,
    "train_no": "G8359",
    "service_date": "2026-10-14",
    "origin": "盐城",
    "destination": "义乌",
    "from_order": 1,
    "to_order": 14,
    "seat_type_id": 3,
    "seat_type_name": "二等座",
    "available_seats": "167"
  },
  "task": {
    "mode": "targeted",
    "users": 157,
    "concurrency": 2,
    "payRate": 100,
    "waitlist": false,
    "runId": 1799,
    "fromOrder": 1,
    "toOrder": 14,
    "seatTypeId": 3,
    "reserveSeats": 10
  }
}
```

### 确定性检测与模型解释

A2 解读模式为「模型辅助解释（建议需人工核查）」。

> 此段解读是本机测试用的合成文案。真实检测计数见结果。

A3 解读模式为「样本说明」。

> 01A库存位图多占用了第2个区段；01B有重叠的有效分配。模拟缓冲连续3次排队数和最老等待时间上升，触发持续积压规则。

A1 与 A2 读取真实库存视图。全库缓冲由独立采样器查询，采样语句和实际结果保存在 JSON 的 `buffer_sampler`。A3 的两种库存异常与积压均来自独立模拟样本。

### 故障注入的输入与后端行为

P8 在模型请求发出前制造超时，应用回退到本地意图解析，继续查询 MySQL。O7 模拟模型返回 `SELECT 1`，后端拒绝该语句并执行自己的订单状态报表。

```sql
SELECT order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders
WHERE service_date = %s
GROUP BY order_status ORDER BY orders DESC, order_status
LIMIT 20
```

## 现场演示顺序

1. 乘客端先用 P1 展示多条件直达，再用 P2 展示换乘候选和双段验票。
2. 连续用 P3、P5、P6 展示无可用结果、已知能力边界和缺条件的区分。
3. 管理端用 O2、O3 展示组合查询和实际 SQL，用 O4、O5 展示能力与数据范围。
4. 用 A2 查看诊断依据，再用 A3 展示确定性告警。
5. 最后用 B2 展示预留票的计算。停留在任务预览页即可核对 SQL 和预计人数。

## 演示中会遇到的边界

- **没找到符合条件的票**。P3 的模型正确提取了 `max_fare="1"`，MySQL 返回 286 行可用于初筛的车次与席别记录，最终没有满足预算的方案。页面目前只给出通用无结果提示。
- **连座硬条件**。P5 的真实模型明确说明无法核对三连座，后端没有搜索车次。回复还追问了已有默认值或可选的条件，现场可以只讲清连座边界。
- **SQL 被拦截后继续查**。O7 是故障注入用例，可展示记录中的模型原始回复和实际执行语句。页面正常提问时不一定触发这条回退路径。

