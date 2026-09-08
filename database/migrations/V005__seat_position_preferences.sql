-- 长三角 12306 客票综合销售系统
-- V005: A/B/C/D/F 座位位置偏好与库存感知兜底分配
-- 前置迁移: V002, V003, V004
-- 目标版本: MySQL 8.4+
--
-- 本迁移不插入席位或运载量数据。

USE CR12306;

ALTER TABLE order_item
    ADD COLUMN requested_position_code VARCHAR(1) NULL
        COMMENT '订单请求的座位位置 A/B/C/D/F' AFTER seat_type_id,
    ADD COLUMN allow_position_fallback BOOLEAN NOT NULL DEFAULT TRUE
        COMMENT '所选位置无票时是否允许按余票兜底' AFTER requested_position_code,
    ADD CONSTRAINT chk_order_item_position_code CHECK (
        requested_position_code IS NULL
        OR requested_position_code IN ('A', 'B', 'C', 'D', 'F')
    );

ALTER TABLE seat_allocation
    ADD COLUMN allocated_position_code VARCHAR(1) NULL
        COMMENT '分配时的座位位置快照' AFTER seat_id,
    ADD COLUMN allocation_strategy VARCHAR(24) NOT NULL DEFAULT 'AUTO_INVENTORY'
        COMMENT 'PREFERRED/FALLBACK_INVENTORY/AUTO_INVENTORY' AFTER allocated_position_code,
    ADD CONSTRAINT chk_allocation_position_code CHECK (
        allocated_position_code IS NULL
        OR allocated_position_code IN ('A', 'B', 'C', 'D', 'F')
    ),
    ADD CONSTRAINT chk_allocation_strategy CHECK (
        allocation_strategy IN ('PREFERRED', 'FALLBACK_INVENTORY', 'AUTO_INVENTORY')
    );

DELIMITER $$

-- 按 A/B/C/D/F 返回总席位与精确可用席位。
CREATE PROCEDURE sp_query_position_availability(
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
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'POSITION_RUN_NOT_FOUND';
    END IF;
    IF v_request_mask IS NULL OR p_to_order > v_segment_count + 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'POSITION_INVALID_ROUTE';
    END IF;

    SELECT
        s.position_code,
        COUNT(*) AS total_seats,
        COALESCE(SUM((trs.occupied_mask & v_request_mask) = 0), 0) AS available_seats
    FROM train_run AS tr
    JOIN train_run_seat AS trs ON trs.run_id = tr.run_id
    JOIN seat AS s
      ON s.seat_id = trs.seat_id
     AND s.active = TRUE
     AND s.seat_type_id = p_seat_type_id
     AND s.position_code IN ('A', 'B', 'C', 'D', 'F')
    JOIN carriage_template AS ct
      ON ct.carriage_id = s.carriage_id
     AND ct.active = TRUE
     AND ct.formation_id = tr.formation_id
    WHERE tr.run_id = p_run_id
    GROUP BY s.position_code
    ORDER BY FIELD(s.position_code, 'A', 'B', 'C', 'D', 'F');
END$$

-- V004 尚无应用调用方，因此在 V005 中安全升级接口。
-- 新参数：p_position_code 可为 NULL/A/B/C/D/F；p_allow_position_fallback
-- 决定偏好位置无票时是否接受任意可用位置。
DROP PROCEDURE sp_create_order_hold$$

CREATE PROCEDURE sp_create_order_hold(
    IN  p_user_id                BIGINT UNSIGNED,
    IN  p_run_id                 BIGINT UNSIGNED,
    IN  p_from_order             SMALLINT UNSIGNED,
    IN  p_to_order               SMALLINT UNSIGNED,
    IN  p_seat_type_id           SMALLINT UNSIGNED,
    IN  p_position_code          VARCHAR(1),
    IN  p_allow_position_fallback BOOLEAN,
    IN  p_passenger_ids          JSON,
    IN  p_idempotency_key        VARCHAR(80),
    IN  p_hold_seconds           INT UNSIGNED,
    OUT p_order_id               BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_position_code VARCHAR(1) DEFAULT NULL;
    DECLARE v_allow_fallback BOOLEAN DEFAULT TRUE;
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
    DECLARE v_allocated_position VARCHAR(1) DEFAULT NULL;
    DECLARE v_allocation_strategy VARCHAR(24) DEFAULT NULL;
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

    SET v_position_code = NULLIF(UPPER(TRIM(p_position_code)), '');
    SET v_allow_fallback = COALESCE(p_allow_position_fallback, TRUE);

    IF v_position_code IS NOT NULL
       AND v_position_code NOT IN ('A', 'B', 'C', 'D', 'F') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_POSITION_CODE_INVALID';
    END IF;
    IF p_idempotency_key IS NULL OR CHAR_LENGTH(TRIM(p_idempotency_key)) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_KEY_REQUIRED';
    END IF;
    IF p_hold_seconds IS NULL OR p_hold_seconds < 30 OR p_hold_seconds > 1800 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_INVALID_HOLD_SECONDS';
    END IF;
    IF p_passenger_ids IS NULL OR JSON_TYPE(p_passenger_ids) <> 'ARRAY' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_PASSENGERS_MUST_BE_JSON_ARRAY';
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
    CREATE TEMPORARY TABLE tmp_hold_passenger (
        ordinal INT UNSIGNED NOT NULL,
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

    SELECT COUNT(*) INTO v_passenger_count FROM tmp_hold_passenger;
    IF v_passenger_count < 1 OR v_passenger_count > 5
       OR v_passenger_count <> JSON_LENGTH(p_passenger_ids) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'ORDER_PASSENGER_COUNT_INVALID_OR_DUPLICATED';
    END IF;

    SELECT COUNT(*) INTO v_valid_passenger_count
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

    SELECT MAX(order_id) INTO v_existing_order_id
    FROM ticket_order
    WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key;

    IF v_existing_order_id IS NOT NULL THEN
        SELECT COUNT(*), COALESCE(SUM(
            oi.run_id = p_run_id
            AND oi.from_order = p_from_order
            AND oi.to_order = p_to_order
            AND oi.seat_type_id = p_seat_type_id
            AND (oi.requested_position_code <=> v_position_code)
            AND oi.allow_position_fallback = v_allow_fallback
            AND tp.passenger_id IS NOT NULL
        ), 0)
        INTO v_existing_item_count, v_existing_match_count
        FROM order_item AS oi
        LEFT JOIN tmp_hold_passenger AS tp ON tp.passenger_id = oi.passenger_id
        WHERE oi.order_id = v_existing_order_id;

        IF v_existing_item_count <> v_passenger_count
           OR v_existing_match_count <> v_passenger_count THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_CONFLICT';
        END IF;
        SET p_order_id = v_existing_order_id;
        COMMIT;
        DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
        LEAVE proc;
    END IF;

    SET v_not_found = FALSE;
    SELECT formation_id, segment_count, run_status
      INTO v_formation_id, v_segment_count, v_run_status
      FROM train_run WHERE run_id = p_run_id FOR SHARE;
    IF v_not_found THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_RUN_NOT_FOUND';
    END IF;
    IF v_run_status <> 'ON_SALE' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_RUN_NOT_ON_SALE';
    END IF;
    IF v_formation_id IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_RUN_HAS_NO_FORMATION';
    END IF;

    SET v_request_mask = fn_segment_mask(p_from_order, p_to_order);
    IF v_request_mask IS NULL OR p_to_order > v_segment_count + 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_INVALID_ROUTE';
    END IF;

    SET v_not_found = FALSE;
    SELECT amount INTO v_fare
    FROM run_fare
    WHERE run_id = p_run_id
      AND from_order = p_from_order
      AND to_order = p_to_order
      AND seat_type_id = p_seat_type_id
      AND sale_status = 'OPEN'
    FOR SHARE;
    IF v_not_found OR v_fare IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_FARE_NOT_FOUND_OR_CLOSED';
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
        SELECT MAX(order_id) INTO v_existing_order_id
        FROM ticket_order
        WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key;

        IF v_existing_order_id IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_UNEXPECTED_UNIQUE_CONFLICT';
        END IF;

        SELECT COUNT(*), COALESCE(SUM(
            oi.run_id = p_run_id
            AND oi.from_order = p_from_order
            AND oi.to_order = p_to_order
            AND oi.seat_type_id = p_seat_type_id
            AND (oi.requested_position_code <=> v_position_code)
            AND oi.allow_position_fallback = v_allow_fallback
            AND tp.passenger_id IS NOT NULL
        ), 0)
        INTO v_existing_item_count, v_existing_match_count
        FROM order_item AS oi
        LEFT JOIN tmp_hold_passenger AS tp ON tp.passenger_id = oi.passenger_id
        WHERE oi.order_id = v_existing_order_id;

        IF v_existing_item_count <> v_passenger_count
           OR v_existing_match_count <> v_passenger_count THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ORDER_IDEMPOTENCY_CONFLICT';
        END IF;
        SET p_order_id = v_existing_order_id;
        COMMIT;
        DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
        LEAVE proc;
    END IF;

    SET p_order_id = LAST_INSERT_ID();

    WHILE v_i <= v_passenger_count DO
        SELECT passenger_id INTO v_passenger_id
        FROM tmp_hold_passenger WHERE ordinal = v_i;

        SET v_not_found = FALSE;
        SET v_seat_id = NULL;
        SET v_allocated_position = NULL;
        SET v_mask_before = 0;

        SELECT trs.seat_id, s.position_code, trs.occupied_mask
          INTO v_seat_id, v_allocated_position, v_mask_before
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
           AND (
               v_position_code IS NULL
               OR v_allow_fallback = TRUE
               OR s.position_code = v_position_code
           )
         ORDER BY
           CASE
               WHEN v_position_code IS NOT NULL
                    AND s.position_code = v_position_code THEN 0
               WHEN v_position_code IS NULL THEN 0
               ELSE 1
           END,
           CASE WHEN trs.occupied_mask <> 0 THEN 0 ELSE 1 END,
           BIT_COUNT(trs.occupied_mask) DESC,
           trs.seat_id
         LIMIT 1
         FOR UPDATE;

        IF v_not_found OR v_seat_id IS NULL THEN
            IF v_position_code IS NOT NULL AND v_allow_fallback = FALSE THEN
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'ORDER_PREFERRED_POSITION_UNAVAILABLE';
            ELSE
                SIGNAL SQLSTATE '45000'
                    SET MESSAGE_TEXT = 'ORDER_INSUFFICIENT_INVENTORY';
            END IF;
        END IF;

        IF v_position_code IS NULL THEN
            SET v_allocation_strategy = 'AUTO_INVENTORY';
        ELSEIF v_allocated_position = v_position_code THEN
            SET v_allocation_strategy = 'PREFERRED';
        ELSE
            SET v_allocation_strategy = 'FALLBACK_INVENTORY';
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
            seat_type_id, requested_position_code, allow_position_fallback,
            price_snapshot, item_status
        ) VALUES (
            p_order_id, v_passenger_id, p_run_id, p_from_order, p_to_order,
            p_seat_type_id, v_position_code, v_allow_fallback,
            v_fare, 'HELD'
        );
        SET v_order_item_id = LAST_INSERT_ID();

        INSERT INTO seat_allocation (
            order_item_id, run_id, seat_id, allocated_position_code,
            allocation_strategy, from_order, to_order, segment_mask,
            allocation_status, held_until
        ) VALUES (
            v_order_item_id, p_run_id, v_seat_id, v_allocated_position,
            v_allocation_strategy, p_from_order, p_to_order, v_request_mask,
            'HOLD', v_expires_at
        );
        SET v_allocation_id = LAST_INSERT_ID();

        INSERT INTO inventory_event (
            run_id, seat_id, allocation_id, order_item_id, event_type,
            segment_mask, mask_before, mask_after, trace_id, reason_code
        ) VALUES (
            p_run_id, v_seat_id, v_allocation_id, v_order_item_id, 'HOLD',
            v_request_mask, v_mask_before, v_mask_after,
            v_trace_id, v_allocation_strategy
        );

        SET v_i = v_i + 1;
    END WHILE;

    INSERT INTO order_event (
        order_id, event_type, from_status, to_status,
        actor_type, actor_id, trace_id, reason_code,
        event_data
    ) VALUES (
        p_order_id, 'ORDER_HOLD_CREATED', NULL, 'PENDING_PAYMENT',
        'USER', CAST(p_user_id AS CHAR), v_trace_id, 'ORDER_CREATED',
        JSON_OBJECT(
            'requestedPosition', v_position_code,
            'allowFallback', v_allow_fallback
        )
    );

    COMMIT;
    DROP TEMPORARY TABLE IF EXISTS tmp_hold_passenger;
END$$

DELIMITER ;

