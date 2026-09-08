-- 长三角 12306 客票综合销售系统
-- V004: 位图库存核心函数、事务过程与对账视图
-- 前置迁移: V002, V003
-- 目标版本: MySQL 8.4+
--
-- 本迁移只安装数据库能力，不插入编组、席位、运载量或业务数据。

USE CR12306;

DELIMITER $$

-- ============================================================
-- 1. 将左闭右开的停站区间 [from_order, to_order) 转成位图
-- 最多支持 63 个相邻区间，即停站序号最大为 64。
-- ============================================================

CREATE FUNCTION fn_segment_mask(
    p_from_order SMALLINT UNSIGNED,
    p_to_order   SMALLINT UNSIGNED
)
RETURNS BIGINT UNSIGNED
DETERMINISTIC
NO SQL
BEGIN
    IF p_from_order IS NULL
       OR p_to_order IS NULL
       OR p_from_order < 1
       OR p_to_order <= p_from_order
       OR p_to_order > 64 THEN
        RETURN NULL;
    END IF;

    RETURN (
        ((CAST(1 AS UNSIGNED) << (p_to_order - p_from_order)) - 1)
        << (p_from_order - 1)
    );
END$$

-- ============================================================
-- 2. 精确余票查询
-- 返回给定运行实例、OD 和席别下全程可用的具体席位数量。
-- ============================================================

CREATE PROCEDURE sp_query_availability(
    IN p_run_id       BIGINT UNSIGNED,
    IN p_from_order   SMALLINT UNSIGNED,
    IN p_to_order     SMALLINT UNSIGNED,
    IN p_seat_type_id SMALLINT UNSIGNED
)
proc: BEGIN
    DECLARE v_segment_count SMALLINT UNSIGNED DEFAULT NULL;
    DECLARE v_request_mask BIGINT UNSIGNED DEFAULT NULL;

    SELECT MAX(segment_count)
      INTO v_segment_count
      FROM train_run
     WHERE run_id = p_run_id;

    SET v_request_mask = fn_segment_mask(p_from_order, p_to_order);

    IF v_segment_count IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'INVENTORY_RUN_NOT_FOUND';
    END IF;

    IF v_request_mask IS NULL OR p_to_order > v_segment_count + 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'INVENTORY_INVALID_ROUTE';
    END IF;

    SELECT
        p_run_id AS run_id,
        p_from_order AS from_order,
        p_to_order AS to_order,
        p_seat_type_id AS seat_type_id,
        v_request_mask AS request_mask,
        COUNT(*) AS total_seats,
        COALESCE(SUM((trs.occupied_mask & v_request_mask) = 0), 0) AS available_seats
    FROM train_run AS tr
    JOIN train_run_seat AS trs
      ON trs.run_id = tr.run_id
    JOIN seat AS s
      ON s.seat_id = trs.seat_id
     AND s.active = TRUE
     AND s.seat_type_id = p_seat_type_id
    JOIN carriage_template AS ct
      ON ct.carriage_id = s.carriage_id
     AND ct.active = TRUE
     AND ct.formation_id = tr.formation_id
    WHERE tr.run_id = p_run_id;
END$$

-- ============================================================
-- 3. 创建整单支付占座
-- p_passenger_ids 示例: JSON_ARRAY(101, 102)
-- 过程自行开始和提交事务，调用方不得在外层已有事务中调用。
-- ============================================================

CREATE PROCEDURE sp_create_order_hold(
    IN  p_user_id          BIGINT UNSIGNED,
    IN  p_run_id           BIGINT UNSIGNED,
    IN  p_from_order       SMALLINT UNSIGNED,
    IN  p_to_order         SMALLINT UNSIGNED,
    IN  p_seat_type_id     SMALLINT UNSIGNED,
    IN  p_passenger_ids    JSON,
    IN  p_idempotency_key  VARCHAR(80),
    IN  p_hold_seconds     INT UNSIGNED,
    OUT p_order_id         BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_formation_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_segment_count SMALLINT UNSIGNED DEFAULT NULL;
    DECLARE v_run_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_request_mask BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_passenger_count INT UNSIGNED DEFAULT 0;
    DECLARE v_valid_passenger_count INT UNSIGNED DEFAULT 0;
    DECLARE v_existing_order_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_existing_item_count INT UNSIGNED DEFAULT 0;
    DECLARE v_existing_match_count INT UNSIGNED DEFAULT 0;
    DECLARE v_duplicate_order BOOLEAN DEFAULT FALSE;
    DECLARE v_fare DECIMAL(10, 2) DEFAULT NULL;
    DECLARE v_total_amount DECIMAL(12, 2) DEFAULT 0;
    DECLARE v_order_no VARCHAR(40);
    DECLARE v_trace_id VARCHAR(80);
    DECLARE v_expires_at DATETIME(6);
    DECLARE v_i INT UNSIGNED DEFAULT 1;
    DECLARE v_passenger_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_seat_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_mask_before BIGINT UNSIGNED DEFAULT 0;
    DECLARE v_mask_after BIGINT UNSIGNED DEFAULT 0;
    DECLARE v_order_item_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_allocation_id BIGINT UNSIGNED DEFAULT NULL;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
        RESIGNAL;
    END;

    IF p_idempotency_key IS NULL OR CHAR_LENGTH(TRIM(p_idempotency_key)) = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_KEY_REQUIRED';
    END IF;

    IF p_hold_seconds IS NULL OR p_hold_seconds < 30 OR p_hold_seconds > 1800 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_INVALID_HOLD_SECONDS';
    END IF;

    IF p_passenger_ids IS NULL OR JSON_TYPE(p_passenger_ids) <> 'ARRAY' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_PASSENGERS_MUST_BE_JSON_ARRAY';
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
    CREATE TEMPORARY TABLE tmp_hold_passenger (
        ordinal      INT UNSIGNED NOT NULL,
        passenger_id BIGINT UNSIGNED NOT NULL,
        PRIMARY KEY (ordinal),
        UNIQUE KEY uk_tmp_hold_passenger (passenger_id)
    ) ENGINE=MEMORY;

    INSERT INTO tmp_hold_passenger (ordinal, passenger_id)
    SELECT jt.ordinal, jt.passenger_id
    FROM JSON_TABLE(
        p_passenger_ids,
        '$[*]' COLUMNS (
            ordinal FOR ORDINALITY,
            passenger_id BIGINT UNSIGNED PATH '$' ERROR ON EMPTY ERROR ON ERROR
        )
    ) AS jt;

    SELECT COUNT(*) INTO v_passenger_count
    FROM tmp_hold_passenger;

    IF v_passenger_count < 1 OR v_passenger_count > 5
       OR v_passenger_count <> JSON_LENGTH(p_passenger_ids) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_PASSENGER_COUNT_INVALID_OR_DUPLICATED';
    END IF;

    SELECT COUNT(*)
      INTO v_valid_passenger_count
      FROM tmp_hold_passenger AS tp
      JOIN passenger AS p
        ON p.passenger_id = tp.passenger_id
       AND p.owner_user_id = p_user_id
       AND p.passenger_status = 'ACTIVE';

    IF v_valid_passenger_count <> v_passenger_count THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_PASSENGER_NOT_OWNED_OR_DISABLED';
    END IF;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    SELECT MAX(order_id)
      INTO v_existing_order_id
      FROM ticket_order
     WHERE user_id = p_user_id
       AND idempotency_key = p_idempotency_key;

    IF v_existing_order_id IS NOT NULL THEN
        SELECT
            COUNT(*),
            COALESCE(SUM(
                oi.run_id = p_run_id
                AND oi.from_order = p_from_order
                AND oi.to_order = p_to_order
                AND oi.seat_type_id = p_seat_type_id
                AND tp.passenger_id IS NOT NULL
            ), 0)
          INTO v_existing_item_count, v_existing_match_count
          FROM order_item AS oi
          LEFT JOIN tmp_hold_passenger AS tp
            ON tp.passenger_id = oi.passenger_id
         WHERE oi.order_id = v_existing_order_id;

        IF v_existing_item_count <> v_passenger_count
           OR v_existing_match_count <> v_passenger_count THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_CONFLICT';
        END IF;

        SET p_order_id = v_existing_order_id;
        COMMIT;
        DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
        LEAVE proc;
    END IF;

    SET v_not_found = FALSE;
    SELECT formation_id, segment_count, run_status
      INTO v_formation_id, v_segment_count, v_run_status
     FROM train_run
     WHERE run_id = p_run_id
     FOR SHARE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_RUN_NOT_FOUND';
    END IF;

    IF v_run_status <> 'ON_SALE' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_RUN_NOT_ON_SALE';
    END IF;

    IF v_formation_id IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_RUN_HAS_NO_FORMATION';
    END IF;

    SET v_request_mask = fn_segment_mask(p_from_order, p_to_order);
    IF v_request_mask IS NULL OR p_to_order > v_segment_count + 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_INVALID_ROUTE';
    END IF;

    SET v_not_found = FALSE;
    SELECT amount
      INTO v_fare
      FROM run_fare
     WHERE run_id = p_run_id
       AND from_order = p_from_order
       AND to_order = p_to_order
       AND seat_type_id = p_seat_type_id
       AND sale_status = 'OPEN'
     FOR SHARE;

    IF v_not_found OR v_fare IS NULL THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_FARE_NOT_FOUND_OR_CLOSED';
    END IF;

    SET v_total_amount = v_fare * v_passenger_count;
    SET v_order_no = CONCAT('O', UPPER(REPLACE(UUID(), '-', '')));
    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
    SET v_expires_at = TIMESTAMPADD(SECOND, p_hold_seconds, NOW(6));

    BEGIN
        DECLARE CONTINUE HANDLER FOR 1062 SET v_duplicate_order = TRUE;

        INSERT INTO ticket_order (
            order_no, user_id, order_status, total_amount, currency,
            expires_at, idempotency_key, order_source
        ) VALUES (
            v_order_no, p_user_id, 'PENDING_PAYMENT', v_total_amount, 'CNY',
            v_expires_at, p_idempotency_key, 'WEB'
        );
    END;

    IF v_duplicate_order THEN
        SELECT MAX(order_id)
          INTO v_existing_order_id
          FROM ticket_order
         WHERE user_id = p_user_id
           AND idempotency_key = p_idempotency_key;

        IF v_existing_order_id IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'ORDER_UNEXPECTED_UNIQUE_CONFLICT';
        END IF;

        SELECT
            COUNT(*),
            COALESCE(SUM(
                oi.run_id = p_run_id
                AND oi.from_order = p_from_order
                AND oi.to_order = p_to_order
                AND oi.seat_type_id = p_seat_type_id
                AND tp.passenger_id IS NOT NULL
            ), 0)
          INTO v_existing_item_count, v_existing_match_count
          FROM order_item AS oi
          LEFT JOIN tmp_hold_passenger AS tp
            ON tp.passenger_id = oi.passenger_id
         WHERE oi.order_id = v_existing_order_id;

        IF v_existing_item_count <> v_passenger_count
           OR v_existing_match_count <> v_passenger_count THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_CONFLICT';
        END IF;

        SET p_order_id = v_existing_order_id;
        COMMIT;
        DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
        LEAVE proc;
    END IF;

    SET p_order_id = LAST_INSERT_ID();

    WHILE v_i <= v_passenger_count DO
        SELECT passenger_id
          INTO v_passenger_id
          FROM tmp_hold_passenger
         WHERE ordinal = v_i;

        SET v_not_found = FALSE;
        SET v_seat_id = NULL;
        SET v_mask_before = 0;

        SELECT trs.seat_id, trs.occupied_mask
          INTO v_seat_id, v_mask_before
          FROM train_run_seat AS trs
          JOIN seat AS s
            ON s.seat_id = trs.seat_id
           AND s.active = TRUE
           AND s.seat_type_id = p_seat_type_id
          JOIN carriage_template AS ct
            ON ct.carriage_id = s.carriage_id
           AND ct.active = TRUE
           AND ct.formation_id = v_formation_id
         WHERE trs.run_id = p_run_id
           AND (trs.occupied_mask & v_request_mask) = 0
         ORDER BY trs.seat_id
         LIMIT 1
         FOR UPDATE;

        IF v_not_found OR v_seat_id IS NULL THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'ORDER_INSUFFICIENT_INVENTORY';
        END IF;

        UPDATE train_run_seat
           SET occupied_mask = occupied_mask | v_request_mask,
               version = version + 1
         WHERE run_id = p_run_id
           AND seat_id = v_seat_id
           AND (occupied_mask & v_request_mask) = 0;

        IF ROW_COUNT() <> 1 THEN
            SIGNAL SQLSTATE '40001'
                SET MESSAGE_TEXT = 'ORDER_INVENTORY_CONCURRENT_CONFLICT';
        END IF;

        SET v_mask_after = v_mask_before | v_request_mask;

        INSERT INTO order_item (
            order_id, passenger_id, run_id, from_order, to_order,
            seat_type_id, price_snapshot, item_status
        ) VALUES (
            p_order_id, v_passenger_id, p_run_id, p_from_order, p_to_order,
            p_seat_type_id, v_fare, 'HELD'
        );

        SET v_order_item_id = LAST_INSERT_ID();

        INSERT INTO seat_allocation (
            order_item_id, run_id, seat_id, from_order, to_order,
            segment_mask, allocation_status, held_until
        ) VALUES (
            v_order_item_id, p_run_id, v_seat_id, p_from_order, p_to_order,
            v_request_mask, 'HOLD', v_expires_at
        );

        SET v_allocation_id = LAST_INSERT_ID();

        INSERT INTO inventory_event (
            run_id, seat_id, allocation_id, order_item_id, event_type,
            segment_mask, mask_before, mask_after, trace_id, reason_code
        ) VALUES (
            p_run_id, v_seat_id, v_allocation_id, v_order_item_id, 'HOLD',
            v_request_mask, v_mask_before, v_mask_after, v_trace_id, 'ORDER_CREATED'
        );

        SET v_i = v_i + 1;
    END WHILE;

    INSERT INTO order_event (
        order_id, event_type, from_status, to_status,
        actor_type, actor_id, trace_id, reason_code
    ) VALUES (
        p_order_id, 'ORDER_HOLD_CREATED', NULL, 'PENDING_PAYMENT',
        'USER', CAST(p_user_id AS CHAR), v_trace_id, 'ORDER_CREATED'
    );

    COMMIT;
    DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
END$$

-- ============================================================
-- 4. 支付成功确认
-- 重复的 payment_request_no 返回同一结果，不会重复确认库存。
-- ============================================================

CREATE PROCEDURE sp_confirm_order_payment(
    IN  p_user_id            BIGINT UNSIGNED,
    IN  p_order_id           BIGINT UNSIGNED,
    IN  p_payment_request_no VARCHAR(64),
    IN  p_channel_trade_no   VARCHAR(80),
    IN  p_amount             DECIMAL(12, 2),
    OUT p_payment_id         BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_order_user_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_order_status VARCHAR(24) DEFAULT NULL;
    DECLARE v_total_amount DECIMAL(12, 2) DEFAULT NULL;
    DECLARE v_expires_at DATETIME(6) DEFAULT NULL;
    DECLARE v_existing_payment_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_existing_order_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_existing_amount DECIMAL(12, 2) DEFAULT NULL;
    DECLARE v_existing_status VARCHAR(20) DEFAULT NULL;
    DECLARE v_trace_id VARCHAR(80);

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_payment_request_no IS NULL
       OR CHAR_LENGTH(TRIM(p_payment_request_no)) = 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_REQUEST_NO_REQUIRED';
    END IF;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    SELECT MAX(payment_id)
      INTO v_existing_payment_id
      FROM payment
     WHERE payment_request_no = p_payment_request_no;

    IF v_existing_payment_id IS NOT NULL THEN
        SELECT order_id, amount, payment_status
          INTO v_existing_order_id, v_existing_amount, v_existing_status
          FROM payment
         WHERE payment_id = v_existing_payment_id;

        IF v_existing_order_id <> p_order_id
           OR v_existing_amount <> p_amount
           OR v_existing_status <> 'SUCCESS' THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'PAYMENT_IDEMPOTENCY_CONFLICT';
        END IF;

        SET p_payment_id = v_existing_payment_id;
        COMMIT;
        LEAVE proc;
    END IF;

    SET v_not_found = FALSE;
    SELECT user_id, order_status, total_amount, expires_at
      INTO v_order_user_id, v_order_status, v_total_amount, v_expires_at
      FROM ticket_order
     WHERE order_id = p_order_id
     FOR UPDATE;

    IF v_not_found THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_ORDER_NOT_FOUND';
    END IF;

    IF v_order_user_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_ORDER_NOT_OWNED';
    END IF;

    IF v_order_status <> 'PENDING_PAYMENT' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_ORDER_STATE_INVALID';
    END IF;

    IF v_expires_at IS NULL OR v_expires_at <= NOW(6) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_ORDER_EXPIRED';
    END IF;

    IF p_amount <> v_total_amount THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_AMOUNT_MISMATCH';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM seat_allocation AS sa
        JOIN order_item AS oi
          ON oi.order_item_id = sa.order_item_id
        WHERE oi.order_id = p_order_id
          AND (sa.allocation_status <> 'HOLD' OR sa.held_until <= NOW(6))
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PAYMENT_HOLD_STATE_INVALID';
    END IF;

    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));

    INSERT INTO payment (
        order_id, payment_request_no, channel_trade_no,
        payment_status, amount, requested_at, paid_at
    ) VALUES (
        p_order_id, p_payment_request_no, p_channel_trade_no,
        'SUCCESS', p_amount, NOW(6), NOW(6)
    );

    SET p_payment_id = LAST_INSERT_ID();

    INSERT INTO inventory_event (
        run_id, seat_id, allocation_id, order_item_id, event_type,
        segment_mask, mask_before, mask_after, trace_id, reason_code
    )
    SELECT
        sa.run_id, sa.seat_id, sa.allocation_id, sa.order_item_id, 'CONFIRM',
        sa.segment_mask, trs.occupied_mask, trs.occupied_mask,
        v_trace_id, 'PAYMENT_SUCCESS'
    FROM seat_allocation AS sa
    JOIN order_item AS oi
      ON oi.order_item_id = sa.order_item_id
    JOIN train_run_seat AS trs
      ON trs.run_id = sa.run_id
     AND trs.seat_id = sa.seat_id
    WHERE oi.order_id = p_order_id
      AND sa.allocation_status = 'HOLD';

    UPDATE seat_allocation AS sa
    JOIN order_item AS oi
      ON oi.order_item_id = sa.order_item_id
       SET sa.allocation_status = 'CONFIRMED',
           sa.held_until = NULL,
           sa.version = sa.version + 1
     WHERE oi.order_id = p_order_id
       AND sa.allocation_status = 'HOLD';

    UPDATE order_item
       SET item_status = 'CONFIRMED'
     WHERE order_id = p_order_id
       AND item_status = 'HELD';

    UPDATE ticket_order
       SET order_status = 'PAID',
           version = version + 1
     WHERE order_id = p_order_id;

    INSERT INTO order_event (
        order_id, event_type, from_status, to_status,
        actor_type, actor_id, trace_id, reason_code
    ) VALUES (
        p_order_id, 'PAYMENT_CONFIRMED', 'PENDING_PAYMENT', 'PAID',
        'PAYMENT', p_channel_trade_no, v_trace_id, 'PAYMENT_SUCCESS'
    );

    COMMIT;
END$$

-- ============================================================
-- 5. 用户取消未支付订单并释放原区间
-- 已支付订单必须走后续退款过程，不能调用本过程。
-- ============================================================

CREATE PROCEDURE sp_cancel_unpaid_order(
    IN p_user_id  BIGINT UNSIGNED,
    IN p_order_id BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_order_user_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_order_status VARCHAR(24) DEFAULT NULL;
    DECLARE v_allocation_id BIGINT UNSIGNED;
    DECLARE v_order_item_id BIGINT UNSIGNED;
    DECLARE v_run_id BIGINT UNSIGNED;
    DECLARE v_seat_id BIGINT UNSIGNED;
    DECLARE v_segment_mask BIGINT UNSIGNED;
    DECLARE v_mask_before BIGINT UNSIGNED;
    DECLARE v_mask_after BIGINT UNSIGNED;
    DECLARE v_trace_id VARCHAR(80);

    DECLARE cur_allocation CURSOR FOR
        SELECT
            sa.allocation_id,
            sa.order_item_id,
            sa.run_id,
            sa.seat_id,
            sa.segment_mask
        FROM seat_allocation AS sa
        JOIN order_item AS oi
          ON oi.order_item_id = sa.order_item_id
        WHERE oi.order_id = p_order_id
          AND sa.allocation_status = 'HOLD'
        ORDER BY sa.run_id, sa.seat_id
        FOR UPDATE;

    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    SET v_done = FALSE;
    SELECT user_id, order_status
      INTO v_order_user_id, v_order_status
      FROM ticket_order
     WHERE order_id = p_order_id
     FOR UPDATE;

    IF v_done THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'CANCEL_ORDER_NOT_FOUND';
    END IF;

    IF v_order_user_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'CANCEL_ORDER_NOT_OWNED';
    END IF;

    IF v_order_status = 'CANCELLED' THEN
        COMMIT;
        LEAVE proc;
    END IF;

    IF v_order_status <> 'PENDING_PAYMENT' THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'CANCEL_ORDER_STATE_INVALID';
    END IF;

    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
    SET v_done = FALSE;
    OPEN cur_allocation;

    release_loop: LOOP
        FETCH cur_allocation
         INTO v_allocation_id, v_order_item_id, v_run_id, v_seat_id, v_segment_mask;

        IF v_done THEN
            LEAVE release_loop;
        END IF;

        SELECT occupied_mask
          INTO v_mask_before
          FROM train_run_seat
         WHERE run_id = v_run_id
           AND seat_id = v_seat_id
         FOR UPDATE;

        IF (v_mask_before & v_segment_mask) <> v_segment_mask THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'CANCEL_INVENTORY_RECONCILIATION_FAILED';
        END IF;

        SET v_mask_after = v_mask_before & ~v_segment_mask;

        UPDATE train_run_seat
           SET occupied_mask = v_mask_after,
               version = version + 1
         WHERE run_id = v_run_id
           AND seat_id = v_seat_id;

        UPDATE seat_allocation
           SET allocation_status = 'RELEASED',
               held_until = NULL,
               released_at = NOW(6),
               release_reason = 'USER_CANCELLED',
               version = version + 1
         WHERE allocation_id = v_allocation_id
           AND allocation_status = 'HOLD';

        INSERT INTO inventory_event (
            run_id, seat_id, allocation_id, order_item_id, event_type,
            segment_mask, mask_before, mask_after, trace_id, reason_code
        ) VALUES (
            v_run_id, v_seat_id, v_allocation_id, v_order_item_id, 'RELEASE',
            v_segment_mask, v_mask_before, v_mask_after,
            v_trace_id, 'USER_CANCELLED'
        );
    END LOOP;

    CLOSE cur_allocation;

    UPDATE order_item
       SET item_status = 'CANCELLED'
     WHERE order_id = p_order_id
       AND item_status = 'HELD';

    UPDATE ticket_order
       SET order_status = 'CANCELLED',
           version = version + 1
     WHERE order_id = p_order_id;

    INSERT INTO order_event (
        order_id, event_type, from_status, to_status,
        actor_type, actor_id, trace_id, reason_code
    ) VALUES (
        p_order_id, 'ORDER_CANCELLED', 'PENDING_PAYMENT', 'CANCELLED',
        'USER', CAST(p_user_id AS CHAR), v_trace_id, 'USER_CANCELLED'
    );

    COMMIT;
END$$

DELIMITER ;

-- ============================================================
-- 6. 当前位图与有效分配记录对账
-- is_consistent 必须始终为 1。
-- ============================================================

CREATE VIEW v_inventory_reconciliation AS
SELECT
    trs.run_id,
    trs.seat_id,
    trs.occupied_mask AS stored_mask,
    BIT_OR(
        CASE
            WHEN sa.allocation_status IN ('HOLD', 'CONFIRMED')
                THEN sa.segment_mask
            ELSE 0
        END
    ) AS allocation_mask,
    trs.occupied_mask = BIT_OR(
        CASE
            WHEN sa.allocation_status IN ('HOLD', 'CONFIRMED')
                THEN sa.segment_mask
            ELSE 0
        END
    ) AS is_consistent
FROM train_run_seat AS trs
LEFT JOIN seat_allocation AS sa
  ON sa.run_id = trs.run_id
 AND sa.seat_id = trs.seat_id
GROUP BY
    trs.run_id,
    trs.seat_id,
    trs.occupied_mask;

CREATE VIEW v_order_amount_reconciliation AS
SELECT
    o.order_id,
    o.order_no,
    o.total_amount AS stored_total,
    COALESCE(SUM(oi.price_snapshot), 0) AS item_total,
    o.total_amount = COALESCE(SUM(oi.price_snapshot), 0) AS is_consistent
FROM ticket_order AS o
LEFT JOIN order_item AS oi
  ON oi.order_id = o.order_id
GROUP BY
    o.order_id,
    o.order_no,
    o.total_amount;
