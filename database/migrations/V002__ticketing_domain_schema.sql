-- 长三角 12306 客票综合销售系统
-- V002: 售票域结构评审稿
-- 目标版本: MySQL 8.4+
--
-- 重要说明：
-- 1. 本脚本当前只供评审，尚未在 CR12306 执行。
-- 2. 编组、车厢、席位和运载量只创建可配置结构，不插入容量数据。
-- 3. train_station 的 day_offset 先允许 NULL；数据清洗后再收紧为 NOT NULL。
-- 4. 所有业务表使用 InnoDB；MySQL 是库存和订单的唯一事实来源。

USE CR12306;

-- ============================================================
-- 1. 扩充现有静态铁路数据
-- ============================================================

ALTER TABLE station
    ADD COLUMN station_code VARCHAR(16) NULL COMMENT '稳定业务站码，待后续补齐' AFTER station_id,
    ADD UNIQUE KEY uk_station_code (station_code);

ALTER TABLE train_station
    ADD COLUMN arrival_day_offset SMALLINT UNSIGNED NULL
        COMMENT '相对始发服务日的到达日偏移，待清洗后改为非空' AFTER arrival_time,
    ADD COLUMN departure_day_offset SMALLINT UNSIGNED NULL
        COMMENT '相对始发服务日的出发日偏移，待清洗后改为非空' AFTER departure_time,
    ADD KEY idx_train_station_lookup (station_id, train_no, station_order);

ALTER TABLE train_segment
    ADD CONSTRAINT chk_train_segment_adjacent
        CHECK (to_order = from_order + 1),
    ADD CONSTRAINT chk_train_segment_distinct_station
        CHECK (from_station_id <> to_station_id),
    ADD KEY idx_train_segment_route
        (from_station_id, to_station_id, departure_time, train_no);

-- ============================================================
-- 2. 席别与可配置编组
-- 当前不插入任何运载量数据
-- ============================================================

CREATE TABLE seat_type (
    seat_type_id       SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
    seat_type_code     VARCHAR(20) NOT NULL,
    seat_type_name     VARCHAR(40) NOT NULL,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    display_order      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (seat_type_id),
    UNIQUE KEY uk_seat_type_code (seat_type_code),
    UNIQUE KEY uk_seat_type_name (seat_type_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='席别字典，不包含具体容量';

CREATE TABLE formation_template (
    formation_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    formation_code     VARCHAR(40) NOT NULL,
    formation_name     VARCHAR(100) NOT NULL,
    applicable_train_type VARCHAR(20) NULL,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    description        VARCHAR(500) NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (formation_id),
    UNIQUE KEY uk_formation_code (formation_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='可配置列车编组模板，后续再设置运载量';

CREATE TABLE carriage_template (
    carriage_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    formation_id       BIGINT UNSIGNED NOT NULL,
    carriage_no        SMALLINT UNSIGNED NOT NULL,
    carriage_code      VARCHAR(20) NOT NULL,
    carriage_name      VARCHAR(80) NULL,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (carriage_id),
    UNIQUE KEY uk_carriage_number (formation_id, carriage_no),
    UNIQUE KEY uk_carriage_code (formation_id, carriage_code),
    CONSTRAINT fk_carriage_formation
        FOREIGN KEY (formation_id) REFERENCES formation_template (formation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_carriage_no CHECK (carriage_no >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='编组内的车厢模板';

CREATE TABLE seat (
    seat_id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    carriage_id        BIGINT UNSIGNED NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    seat_no            VARCHAR(20) NOT NULL,
    row_no             SMALLINT UNSIGNED NULL,
    position_code      VARCHAR(20) NULL COMMENT 'A/B/C/D/F、上铺/中铺/下铺等',
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (seat_id),
    UNIQUE KEY uk_carriage_seat_no (carriage_id, seat_no),
    KEY idx_seat_type (seat_type_id, carriage_id),
    CONSTRAINT fk_seat_carriage
        FOREIGN KEY (carriage_id) REFERENCES carriage_template (carriage_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='可复用的具体席位单元；记录数决定编组运载量';

-- ============================================================
-- 3. 当日列车运行实例
-- ============================================================

CREATE TABLE train_run (
    run_id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    train_no           VARCHAR(20) NOT NULL,
    service_date       DATE NOT NULL COMMENT '裁剪后长三角区域运行片段起点的服务日',
    formation_id       BIGINT UNSIGNED NULL COMMENT '容量确定后再分配编组',
    stop_count         SMALLINT UNSIGNED NOT NULL,
    segment_count      SMALLINT UNSIGNED NOT NULL,
    run_status         VARCHAR(20) NOT NULL DEFAULT 'PLANNED',
    sale_start_at      DATETIME(6) NULL,
    sale_end_at        DATETIME(6) NULL,
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (run_id),
    UNIQUE KEY uk_train_run_service (train_no, service_date),
    KEY idx_train_run_sale (service_date, run_status, train_no),
    KEY idx_train_run_formation (formation_id),
    CONSTRAINT fk_train_run_train
        FOREIGN KEY (train_no) REFERENCES train (train_no)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_train_run_formation
        FOREIGN KEY (formation_id) REFERENCES formation_template (formation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_train_run_stop_count CHECK (stop_count >= 2),
    CONSTRAINT chk_train_run_segment_count
        CHECK (segment_count = stop_count - 1 AND segment_count BETWEEN 1 AND 63),
    CONSTRAINT chk_train_run_status
        CHECK (run_status IN ('PLANNED', 'ON_SALE', 'STOP_SALE', 'CANCELLED', 'FINISHED')),
    CONSTRAINT chk_train_run_sale_window
        CHECK (sale_start_at IS NULL OR sale_end_at IS NULL OR sale_start_at < sale_end_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='某一服务日的可售列车运行实例';

CREATE TABLE train_run_seat (
    run_id             BIGINT UNSIGNED NOT NULL,
    seat_id            BIGINT UNSIGNED NOT NULL,
    occupied_mask      BIGINT UNSIGNED NOT NULL DEFAULT 0,
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (run_id, seat_id),
    CONSTRAINT fk_run_seat_run
        FOREIGN KEY (run_id) REFERENCES train_run (run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_run_seat_seat
        FOREIGN KEY (seat_id) REFERENCES seat (seat_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='运行实例上的席位位图当前状态；位与条件不可直接利用 occupied_mask 的 B-Tree 索引';

CREATE TABLE run_fare (
    run_fare_id        BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id             BIGINT UNSIGNED NOT NULL,
    from_order         SMALLINT UNSIGNED NOT NULL,
    to_order           SMALLINT UNSIGNED NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    amount             DECIMAL(10, 2) NOT NULL,
    currency           CHAR(3) NOT NULL DEFAULT 'CNY',
    sale_status        VARCHAR(20) NOT NULL DEFAULT 'OPEN',
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (run_fare_id),
    UNIQUE KEY uk_run_fare_product (run_id, from_order, to_order, seat_type_id),
    KEY idx_run_fare_search (run_id, seat_type_id, from_order, to_order),
    CONSTRAINT fk_run_fare_run
        FOREIGN KEY (run_id) REFERENCES train_run (run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_run_fare_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_run_fare_order CHECK (from_order >= 1 AND to_order > from_order),
    CONSTRAINT chk_run_fare_amount CHECK (amount >= 0),
    CONSTRAINT chk_run_fare_status CHECK (sale_status IN ('OPEN', 'CLOSED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='运行实例、OD 与席别组成的可售产品及票价';

-- ============================================================
-- 4. 用户、乘车人与订单
-- ============================================================

CREATE TABLE app_user (
    user_id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username           VARCHAR(64) NOT NULL,
    password_hash      VARCHAR(255) NOT NULL,
    user_status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (user_id),
    UNIQUE KEY uk_app_user_username (username),
    CONSTRAINT chk_app_user_status
        CHECK (user_status IN ('ACTIVE', 'LOCKED', 'DISABLED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='购票账户';

CREATE TABLE passenger (
    passenger_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    owner_user_id      BIGINT UNSIGNED NOT NULL,
    passenger_name     VARCHAR(80) NOT NULL,
    document_type      VARCHAR(20) NOT NULL DEFAULT 'SIMULATED',
    document_hash      BINARY(32) NOT NULL COMMENT '模拟证件标识的 SHA-256，不存真实明文',
    passenger_status   VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (passenger_id),
    UNIQUE KEY uk_passenger_document (document_type, document_hash),
    KEY idx_passenger_owner (owner_user_id, passenger_status),
    CONSTRAINT fk_passenger_owner
        FOREIGN KEY (owner_user_id) REFERENCES app_user (user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_passenger_status
        CHECK (passenger_status IN ('ACTIVE', 'DISABLED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='账户管理的模拟乘车人';

CREATE TABLE ticket_order (
    order_id           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no           VARCHAR(40) NOT NULL,
    user_id            BIGINT UNSIGNED NOT NULL,
    order_status       VARCHAR(24) NOT NULL,
    total_amount       DECIMAL(12, 2) NOT NULL DEFAULT 0,
    currency           CHAR(3) NOT NULL DEFAULT 'CNY',
    expires_at         DATETIME(6) NULL,
    idempotency_key    VARCHAR(80) NOT NULL,
    order_source       VARCHAR(20) NOT NULL DEFAULT 'WEB',
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_id),
    UNIQUE KEY uk_ticket_order_no (order_no),
    UNIQUE KEY uk_ticket_order_idempotency (user_id, idempotency_key),
    KEY idx_ticket_order_expiry (order_status, expires_at, order_id),
    KEY idx_ticket_order_user_time (user_id, created_at),
    CONSTRAINT fk_ticket_order_user
        FOREIGN KEY (user_id) REFERENCES app_user (user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_ticket_order_amount CHECK (total_amount >= 0),
    CONSTRAINT chk_ticket_order_status CHECK (
        order_status IN (
            'PENDING_PAYMENT', 'PAID', 'CANCELLED', 'TIMEOUT',
            'REFUNDING', 'REFUNDED'
        )
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='订单头；CREATING 状态只存在于事务内部';

CREATE TABLE order_item (
    order_item_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id           BIGINT UNSIGNED NOT NULL,
    passenger_id       BIGINT UNSIGNED NOT NULL,
    run_id             BIGINT UNSIGNED NOT NULL,
    from_order         SMALLINT UNSIGNED NOT NULL,
    to_order           SMALLINT UNSIGNED NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    price_snapshot     DECIMAL(10, 2) NOT NULL,
    item_status        VARCHAR(20) NOT NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_item_id),
    UNIQUE KEY uk_order_passenger_run (order_id, passenger_id, run_id),
    KEY idx_order_item_order (order_id, order_item_id),
    KEY idx_order_item_passenger_run (passenger_id, run_id, item_status),
    KEY idx_order_item_run_route (run_id, from_order, to_order, seat_type_id),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_item_passenger
        FOREIGN KEY (passenger_id) REFERENCES passenger (passenger_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_item_run
        FOREIGN KEY (run_id) REFERENCES train_run (run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_order_item_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_item_route CHECK (from_order >= 1 AND to_order > from_order),
    CONSTRAINT chk_order_item_price CHECK (price_snapshot >= 0),
    CONSTRAINT chk_order_item_status CHECK (
        item_status IN ('HELD', 'CONFIRMED', 'CANCELLED', 'TIMEOUT', 'REFUNDED')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='一名乘车人的一张票';

CREATE TABLE seat_allocation (
    allocation_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_item_id      BIGINT UNSIGNED NOT NULL,
    run_id             BIGINT UNSIGNED NOT NULL,
    seat_id            BIGINT UNSIGNED NOT NULL,
    from_order         SMALLINT UNSIGNED NOT NULL,
    to_order           SMALLINT UNSIGNED NOT NULL,
    segment_mask       BIGINT UNSIGNED NOT NULL,
    allocation_status  VARCHAR(20) NOT NULL,
    held_until         DATETIME(6) NULL,
    allocated_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    released_at        DATETIME(6) NULL,
    release_reason     VARCHAR(40) NULL,
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (allocation_id),
    UNIQUE KEY uk_allocation_order_item (order_item_id),
    KEY idx_allocation_run_seat (run_id, seat_id, allocation_status),
    KEY idx_allocation_expiry (allocation_status, held_until, allocation_id),
    CONSTRAINT fk_allocation_order_item
        FOREIGN KEY (order_item_id) REFERENCES order_item (order_item_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_allocation_run_seat
        FOREIGN KEY (run_id, seat_id) REFERENCES train_run_seat (run_id, seat_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_allocation_route CHECK (from_order >= 1 AND to_order > from_order),
    CONSTRAINT chk_allocation_mask CHECK (segment_mask > 0),
    CONSTRAINT chk_allocation_status
        CHECK (allocation_status IN ('HOLD', 'CONFIRMED', 'RELEASED')),
    CONSTRAINT chk_allocation_hold_expiry CHECK (
        (allocation_status = 'HOLD' AND held_until IS NOT NULL)
        OR allocation_status <> 'HOLD'
    ),
    CONSTRAINT chk_allocation_release_time CHECK (
        (allocation_status = 'RELEASED' AND released_at IS NOT NULL)
        OR allocation_status <> 'RELEASED'
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='席位分配事实；历史释放记录不删除';

CREATE TABLE payment (
    payment_id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id           BIGINT UNSIGNED NOT NULL,
    payment_request_no VARCHAR(64) NOT NULL,
    channel_trade_no   VARCHAR(80) NULL,
    payment_status     VARCHAR(20) NOT NULL,
    amount             DECIMAL(12, 2) NOT NULL,
    requested_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    paid_at            DATETIME(6) NULL,
    failure_reason     VARCHAR(200) NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (payment_id),
    UNIQUE KEY uk_payment_request_no (payment_request_no),
    UNIQUE KEY uk_payment_channel_trade (channel_trade_no),
    KEY idx_payment_order (order_id, payment_status),
    CONSTRAINT fk_payment_order
        FOREIGN KEY (order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_payment_amount CHECK (amount >= 0),
    CONSTRAINT chk_payment_status
        CHECK (payment_status IN ('INIT', 'SUCCESS', 'FAILED', 'CLOSED', 'REFUNDED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='支付尝试和幂等回调记录';

-- ============================================================
-- 5. 候补
-- ============================================================

CREATE TABLE wait_request (
    wait_request_id    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    wait_request_no    VARCHAR(40) NOT NULL,
    user_id            BIGINT UNSIGNED NOT NULL,
    run_id             BIGINT UNSIGNED NOT NULL,
    from_order         SMALLINT UNSIGNED NOT NULL,
    to_order           SMALLINT UNSIGNED NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    passenger_count    SMALLINT UNSIGNED NOT NULL,
    wait_status        VARCHAR(24) NOT NULL DEFAULT 'WAITING',
    idempotency_key    VARCHAR(80) NOT NULL,
    skip_count         INT UNSIGNED NOT NULL DEFAULT 0,
    retry_count        INT UNSIGNED NOT NULL DEFAULT 0,
    cutoff_at          DATETIME(6) NOT NULL,
    matched_order_id   BIGINT UNSIGNED NULL,
    version            INT UNSIGNED NOT NULL DEFAULT 0,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (wait_request_id),
    UNIQUE KEY uk_wait_request_no (wait_request_no),
    UNIQUE KEY uk_wait_request_idempotency (user_id, idempotency_key),
    UNIQUE KEY uk_wait_matched_order (matched_order_id),
    KEY idx_wait_match_queue
        (run_id, seat_type_id, wait_status, created_at, wait_request_id),
    KEY idx_wait_cutoff (wait_status, cutoff_at, wait_request_id),
    CONSTRAINT fk_wait_request_user
        FOREIGN KEY (user_id) REFERENCES app_user (user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_wait_request_run
        FOREIGN KEY (run_id) REFERENCES train_run (run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_wait_request_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_wait_request_order
        FOREIGN KEY (matched_order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_wait_request_route CHECK (from_order >= 1 AND to_order > from_order),
    CONSTRAINT chk_wait_request_passenger_count CHECK (passenger_count >= 1),
    CONSTRAINT chk_wait_request_status CHECK (
        wait_status IN ('WAITING', 'MATCHED_HOLD', 'FULFILLED', 'CANCELLED', 'EXPIRED')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='候补请求；第一阶段整单兑现';

CREATE TABLE wait_passenger (
    wait_request_id    BIGINT UNSIGNED NOT NULL,
    passenger_id       BIGINT UNSIGNED NOT NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (wait_request_id, passenger_id),
    KEY idx_wait_passenger_passenger (passenger_id, wait_request_id),
    CONSTRAINT fk_wait_passenger_request
        FOREIGN KEY (wait_request_id) REFERENCES wait_request (wait_request_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_wait_passenger_passenger
        FOREIGN KEY (passenger_id) REFERENCES passenger (passenger_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='候补请求中的乘车人';

-- ============================================================
-- 6. 只追加审计事件
-- ============================================================

CREATE TABLE order_event (
    order_event_id     BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id           BIGINT UNSIGNED NOT NULL,
    event_type         VARCHAR(40) NOT NULL,
    from_status        VARCHAR(24) NULL,
    to_status          VARCHAR(24) NOT NULL,
    actor_type         VARCHAR(20) NOT NULL,
    actor_id           VARCHAR(80) NULL,
    trace_id           VARCHAR(80) NOT NULL,
    reason_code        VARCHAR(40) NULL,
    event_data         JSON NULL,
    occurred_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (order_event_id),
    KEY idx_order_event_order (order_id, order_event_id),
    KEY idx_order_event_trace (trace_id),
    CONSTRAINT fk_order_event_order
        FOREIGN KEY (order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_order_event_actor
        CHECK (actor_type IN ('USER', 'SYSTEM', 'ADMIN', 'PAYMENT'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='只追加的订单状态审计日志';

CREATE TABLE inventory_event (
    inventory_event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    run_id             BIGINT UNSIGNED NOT NULL,
    seat_id            BIGINT UNSIGNED NOT NULL,
    allocation_id      BIGINT UNSIGNED NULL,
    order_item_id      BIGINT UNSIGNED NULL,
    event_type         VARCHAR(30) NOT NULL,
    segment_mask       BIGINT UNSIGNED NOT NULL,
    mask_before        BIGINT UNSIGNED NOT NULL,
    mask_after         BIGINT UNSIGNED NOT NULL,
    trace_id           VARCHAR(80) NOT NULL,
    reason_code        VARCHAR(40) NULL,
    occurred_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (inventory_event_id),
    KEY idx_inventory_event_seat (run_id, seat_id, inventory_event_id),
    KEY idx_inventory_event_order_item (order_item_id, inventory_event_id),
    KEY idx_inventory_event_trace (trace_id),
    CONSTRAINT fk_inventory_event_run_seat
        FOREIGN KEY (run_id, seat_id) REFERENCES train_run_seat (run_id, seat_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_inventory_event_allocation
        FOREIGN KEY (allocation_id) REFERENCES seat_allocation (allocation_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_inventory_event_order_item
        FOREIGN KEY (order_item_id) REFERENCES order_item (order_item_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_inventory_event_mask CHECK (segment_mask > 0),
    CONSTRAINT chk_inventory_event_type
        CHECK (event_type IN ('HOLD', 'CONFIRM', 'RELEASE', 'RECONCILE'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='只追加的库存位图审计日志';

-- ============================================================
-- 7. 运行时刻查询视图
-- day_offset 清洗完成后才会返回完整的到发 DATETIME
-- ============================================================

CREATE VIEW v_train_run_stop AS
SELECT
    tr.run_id,
    tr.train_no,
    tr.service_date,
    ts.station_order,
    ts.station_id,
    CASE
        WHEN ts.arrival_time IS NULL OR ts.arrival_day_offset IS NULL THEN NULL
        ELSE TIMESTAMPADD(
            DAY,
            ts.arrival_day_offset,
            TIMESTAMP(tr.service_date, ts.arrival_time)
        )
    END AS arrival_at,
    CASE
        WHEN ts.departure_time IS NULL OR ts.departure_day_offset IS NULL THEN NULL
        ELSE TIMESTAMPADD(
            DAY,
            ts.departure_day_offset,
            TIMESTAMP(tr.service_date, ts.departure_time)
        )
    END AS departure_at,
    tr.run_status
FROM train_run AS tr
JOIN train_station AS ts
  ON ts.train_no = tr.train_no;

-- V003 将负责时间清洗、day_offset 回填和 train_run 初始化。
-- 编组容量确定后再通过独立迁移插入 formation/carriage/seat，
-- 并为指定 train_run 生成 train_run_seat，不能在本迁移中假设容量。
