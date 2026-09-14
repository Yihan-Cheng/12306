# V011 后端接口与演示界面设计执行报告

## 1. 目标与架构

本阶段把数据库能力组合成可操作的本地演示系统：

```text
浏览器 HTML/CSS/JavaScript
          ↓ JSON/HTTP
Python ThreadingHTTPServer（本地适配层）
     ├─ mysql 客户端 → MySQL 存储过程/视图
     └─ cypher-shell → Neo4j 候选路径
```

本机 pip 代理无法访问包索引，因此选用 Python 标准库并调用容器内命令行客户端，保证当前环境真正可运行。适配层只做参数校验、序列化和接口编排；位图、锁、订单、退款和候补仍由 MySQL 控制。

## 2. HTTP 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/api/health` | MySQL/Neo4j 健康检查 |
| GET | `/api/stations` | 45 个长三角车站 |
| GET | `/api/search/direct` | 直达票价、余票、位置余票 |
| GET | `/api/search/transfer` | Neo4j 候选 + MySQL 两程复核 |
| POST | `/api/register` | 演示账户与模拟乘车人 |
| POST | `/api/orders` | 整单占座 |
| GET | `/api/orders` | 订单和具体席位 |
| POST | `/api/orders/{id}/pay` | 支付确认 |
| POST | `/api/orders/{id}/cancel` | 取消未支付订单 |
| POST | `/api/orders/{id}/refund` | 已支付订单退款 |
| POST | `/api/waits` | 创建候补请求 |

## 3. V011 数据库支持

`sp_register_demo_account` 使用用户名唯一键和模拟证件哈希实现幂等账户准备。浏览器先用 Web Crypto 计算 SHA-256 密码摘要；模拟证件也只保存 SHA-256。

`v_order_detail` 组合订单、乘车人、运行实例、到发站、席别、车厢座号、位置分配策略和库存分配状态，为订单页面提供只读模型。

## 4. 界面能力

- 45 站选择与起终点交换；
- 固定运营日、1～5 人可满足性查询；
- A/B/C/D/F 偏好及余票兜底；
- 直达和一次换乘标签页；
- 余票、指定位置余票、里程、票价和历时；
- 账户、占座、订单、支付、取消、退款和候补；
- 当前项目 95% 进度条；
- 桌面和窄屏响应式布局。

界面账户目前配置一名乘车人，多人查询用于观察库存可满足性；数据库过程本身已经支持 1～5 人。

## 5. 安全边界

- HTTP 只绑定 `127.0.0.1`；
- ID、人数、日期、位置均做白名单或范围校验；
- 任意文本转为 UTF-8 十六进制 SQL 字面量；
- 静态文件必须解析在 `app/web` 内；
- 正式生产仍需要密码 KDF、登录会话、权限中间件、CSRF、TLS、连接池和秘密管理，本项目不伪装达到生产安全等级。

## 6. 验收结果（2026-09-09）

所有写操作在完整隔离库 `CR12306_app_check` 执行：

| 场景 | 结果 |
|---|---|
| HTTP 健康检查 | MySQL 1798、Neo4j 1798 |
| 车站接口 | 45 个站，汉字正常 |
| 上海虹桥—杭州东直达 | 396 条，约 1 秒 |
| A 位优先占座 | 1 车 01A，`PREFERRED` |
| 支付和退款 | `PENDING_PAYMENT → PAID → REFUNDED` |
| F 位严格占座和取消 | 成功，最终 `CANCELLED` |
| 上海虹桥—黄山北换乘 | 192 个席别组合，约 3.8 秒 |
| 首个换乘方案 | D377 → G7482，杭州南换乘 61 分钟，总价 215.50 元 |

换乘 HTTP 初测曾因 `cypher-shell --format plain` 在逗号后保留空格，产生带前导空格的字段名；修正 CSV 解析的 `skipinitialspace` 后重新验收通过。

正式迁移为 `database/migrations/V011__application_api_support.sql`，迁移前备份为 `database/backups/CR12306_pre_V011_20260909.sql`。

## 7. 剩余工作

最后阶段重点是可证明性：端到端并发压测、慢查询与索引分析、隔离级别实验、备份恢复演练、最终课程报告和演示脚本。

