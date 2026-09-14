-- 长三角 12306 客票综合销售系统
-- V009: 候补请求、整单兑现、有界跳过与租约恢复
-- 文件编码: UTF-8（无 BOM）；导入时指定 --default-character-set=utf8mb4
-- 前置迁移: V002 ... V008

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

ALTER TABLE wait_request
    DROP CHECK chk_wait_request_status,
    ADD COLUMN requested_position_code VARCHAR(1) NULL
        COMMENT '候补座位位置偏好 A/B/C/D/F' AFTER seat_type_id,
    ADD COLUMN allow_position_fallback BOOLEAN NOT NULL DEFAULT TRUE
        COMMENT '偏好位置无票时是否允许其他位置' AFTER requested_position_code,
    ADD COLUMN matching_started_at DATETIME(6) NULL
        COMMENT 'MATCHING 租约开始时间' AFTER retry_count,
    ADD COLUMN last_error_code VARCHAR(80) NULL
        COMMENT '最近一次匹配失败原因' AFTER matching_started_at,
    ADD CONSTRAINT chk_wait_request_position CHECK (
        requested_position_code IS NULL
        OR requested_position_code IN ('A', 'B', 'C', 'D', 'F')
    ),
    ADD CONSTRAINT chk_wait_request_status CHECK (
        wait_status IN (
            'WAITING', 'MATCHING', 'MATCHED_HOLD',
            'FULFILLED', 'CANCELLED', 'EXPIRED'
        )
    );

ALTER TABLE wait_passenger
    ADD COLUMN passenger_order SMALLINT UNSIGNED NOT NULL
        COMMENT '候补请求内乘车人顺序' AFTER passenger_id,
    ADD UNIQUE KEY uk_wait_passenger_order (wait_request_id, passenger_order);

CREATE TABLE wait_request_event (
    wait_event_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    wait_request_id    BIGINT UNSIGNED NOT NULL,
    event_type         VARCHAR(40) NOT NULL,
    from_status        VARCHAR(24) NULL,
    to_status          VARCHAR(24) NOT NULL,
    trace_id           VARCHAR(80) NOT NULL,
    reason_code        VARCHAR(80) NULL,
    event_data         JSON NULL,
    occurred_at        DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (wait_event_id),
    KEY idx_wait_event_request (wait_request_id, wait_event_id),
    KEY idx_wait_event_trace (trace_id),
    CONSTRAINT fk_wait_event_request
        FOREIGN KEY (wait_request_id) REFERENCES wait_request (wait_request_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='只追加的候补状态与公平性审计日志';

DELIMITER $$

CREATE PROCEDURE sp_create_wait_request(
    IN  p_user_id                 BIGINT UNSIGNED,
    IN  p_run_id                  BIGINT UNSIGNED,
    IN  p_from_order              SMALLINT UNSIGNED,
    IN  p_to_order                SMALLINT UNSIGNED,
    IN  p_seat_type_id            SMALLINT UNSIGNED,
    IN  p_position_code           VARCHAR(1),
    IN  p_allow_position_fallback BOOLEAN,
    IN  p_passenger_ids           JSON,
    IN  p_idempotency_key         VARCHAR(80),
    IN  p_cutoff_at               DATETIME(6),
    OUT p_wait_request_id         BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_position_code VARCHAR(1);
    DECLARE v_allow_fallback BOOLEAN;
    DECLARE v_passenger_count INT UNSIGNED;
    DECLARE v_valid_count INT UNSIGNED;
    DECLARE v_available_count INT UNSIGNED;
    DECLARE v_segment_count SMALLINT UNSIGNED;
    DECLARE v_request_mask BIGINT UNSIGNED;
    DECLARE v_existing_id BIGINT UNSIGNED;
    DECLARE v_existing_match_count INT UNSIGNED;
    DECLARE v_wait_no VARCHAR(40);
    DECLARE v_trace_id VARCHAR(80);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_wait_passenger;
        RESIGNAL;
    END;

    SET v_position_code = NULLIF(UPPER(TRIM(p_position_code)), '');
    SET v_allow_fallback = COALESCE(p_allow_position_fallback, TRUE);
    IF v_position_code IS NOT NULL
       AND v_position_code NOT IN ('A', 'B', 'C', 'D', 'F') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_POSITION_CODE_INVALID';
    END IF;
    IF p_idempotency_key IS NULL OR CHAR_LENGTH(TRIM(p_idempotency_key)) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_IDEMPOTENCY_KEY_REQUIRED';
    END IF;
    IF p_cutoff_at IS NULL OR p_cutoff_at <= NOW(6) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_CUTOFF_INVALID';
    END IF;
    IF p_passenger_ids IS NULL OR JSON_TYPE(p_passenger_ids) <> 'ARRAY' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_PASSENGERS_MUST_BE_JSON_ARRAY';
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_wait_passenger;
    CREATE TEMPORARY TABLE tmp_wait_passenger (
        passenger_order SMALLINT UNSIGNED NOT NULL,
        passenger_id BIGINT UNSIGNED NOT NULL,
        PRIMARY KEY (passenger_order),
        UNIQUE KEY uk_tmp_wait_passenger (passenger_id)
    ) ENGINE=MEMORY;
    INSERT INTO tmp_wait_passenger (passenger_order, passenger_id)
    SELECT ordinal, passenger_id
      FROM JSON_TABLE(
        p_passenger_ids,
        '$[*]' COLUMNS (
            ordinal FOR ORDINALITY,
            passenger_id BIGINT UNSIGNED PATH '$' ERROR ON EMPTY ERROR ON ERROR
        )
    ) AS jt;

    SELECT COUNT(*) INTO v_passenger_count FROM tmp_wait_passenger;
    IF v_passenger_count < 1 OR v_passenger_count > 5
       OR v_passenger_count <> JSON_LENGTH(p_passenger_ids) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WAIT_PASSENGER_COUNT_INVALID_OR_DUPLICATED';
    END IF;

    SELECT COUNT(*) INTO v_valid_count
      FROM tmp_wait_passenger AS twp
      JOIN passenger AS p
        ON p.passenger_id = twp.passenger_id
       AND p.owner_user_id = p_user_id
       AND p.passenger_status = 'ACTIVE';
    IF v_valid_count <> v_passenger_count THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'WAIT_PASSENGER_NOT_OWNED_OR_DISABLED';
    END IF;

    SELECT MAX(segment_count) INTO v_segment_count
      FROM train_run
     WHERE run_id = p_run_id AND run_status = 'ON_SALE';
    SET v_request_mask = fn_segment_mask(p_from_order, p_to_order);
    IF v_segment_count IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_RUN_NOT_ON_SALE';
    END IF;
    IF v_request_mask IS NULL OR p_to_order > v_segment_count + 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_INVALID_ROUTE';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM run_fare
         WHERE run_id = p_run_id AND from_order = p_from_order
           AND to_order = p_to_order AND seat_type_id = p_seat_type_id
           AND sale_status = 'OPEN'
    ) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_FARE_NOT_FOUND_OR_CLOSED';
    END IF;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    -- 幂等重放必须先于实时余票判断：首次请求后即使库存发生变化，
    -- 同一业务请求也应返回原候补记录。
    SELECT MAX(wait_request_id) INTO v_existing_id
      FROM wait_request
     WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key;
    IF v_existing_id IS NOT NULL THEN
        SELECT COUNT(*) INTO v_existing_match_count
          FROM wait_request AS wr
          JOIN wait_passenger AS wp ON wp.wait_request_id = wr.wait_request_id
          JOIN tmp_wait_passenger AS twp ON twp.passenger_id = wp.passenger_id
         WHERE wr.wait_request_id = v_existing_id
           AND wr.run_id = p_run_id AND wr.from_order = p_from_order
           AND wr.to_order = p_to_order AND wr.seat_type_id = p_seat_type_id
           AND (wr.requested_position_code <=> v_position_code)
           AND wr.allow_position_fallback = v_allow_fallback;
        IF v_existing_match_count <> v_passenger_count THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_IDEMPOTENCY_CONFLICT';
        END IF;
        SET p_wait_request_id = v_existing_id;
        COMMIT;
        DROP TEMPORARY TABLE tmp_wait_passenger;
        LEAVE proc;
    END IF;

    SELECT COUNT(*) INTO v_available_count
      FROM train_run_seat AS trs
      JOIN seat AS s ON s.seat_id = trs.seat_id
      JOIN train_run AS tr ON tr.run_id = trs.run_id
      JOIN carriage_template AS ct
        ON ct.carriage_id = s.carriage_id
       AND ct.formation_id = tr.formation_id
     WHERE trs.run_id = p_run_id
       AND s.seat_type_id = p_seat_type_id
       AND s.active = TRUE AND ct.active = TRUE
       AND (trs.occupied_mask & v_request_mask) = 0
       AND (
            v_position_code IS NULL OR v_allow_fallback = TRUE
            OR s.position_code = v_position_code
       );
    IF v_available_count >= v_passenger_count THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_DIRECT_INVENTORY_AVAILABLE';
    END IF;

    SET v_wait_no = CONCAT('W', UPPER(REPLACE(UUID(), '-', '')));
    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
    INSERT INTO wait_request (
        wait_request_no, user_id, run_id, from_order, to_order,
        seat_type_id, requested_position_code, allow_position_fallback,
        passenger_count, wait_status, idempotency_key, cutoff_at
    ) VALUES (
        v_wait_no, p_user_id, p_run_id, p_from_order, p_to_order,
        p_seat_type_id, v_position_code, v_allow_fallback,
        v_passenger_count, 'WAITING', p_idempotency_key, p_cutoff_at
    );
    SET p_wait_request_id = LAST_INSERT_ID();

    INSERT INTO wait_passenger (
        wait_request_id, passenger_id, passenger_order
    )
    SELECT p_wait_request_id, passenger_id, passenger_order
      FROM tmp_wait_passenger;
    INSERT INTO wait_request_event (
        wait_request_id, event_type, from_status, to_status,
        trace_id, reason_code, event_data
    ) VALUES (
        p_wait_request_id, 'WAIT_CREATED', NULL, 'WAITING',
        v_trace_id, 'INVENTORY_INSUFFICIENT',
        JSON_OBJECT(
            'passengerCount', v_passenger_count,
            'requestedPosition', v_position_code,
            'allowFallback', v_allow_fallback
        )
    );
    COMMIT;
    DROP TEMPORARY TABLE tmp_wait_passenger;
END$$

CREATE PROCEDURE sp_cancel_wait_request(
    IN p_user_id BIGINT UNSIGNED,
    IN p_wait_request_id BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_owner BIGINT UNSIGNED;
    DECLARE v_status VARCHAR(24);
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_trace_id VARCHAR(80);
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    START TRANSACTION;
    SELECT user_id, wait_status INTO v_owner, v_status
      FROM wait_request WHERE wait_request_id = p_wait_request_id FOR UPDATE;
    IF v_not_found THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_REQUEST_NOT_FOUND';
    END IF;
    IF v_owner <> p_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_REQUEST_NOT_OWNED';
    END IF;
    IF v_status = 'CANCELLED' THEN COMMIT; LEAVE proc; END IF;
    IF v_status <> 'WAITING' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_CANCEL_STATE_INVALID';
    END IF;
    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
    UPDATE wait_request
       SET wait_status = 'CANCELLED', version = version + 1
     WHERE wait_request_id = p_wait_request_id;
    INSERT INTO wait_request_event (
        wait_request_id, event_type, from_status, to_status,
        trace_id, reason_code
    ) VALUES (
        p_wait_request_id, 'WAIT_CANCELLED', 'WAITING', 'CANCELLED',
        v_trace_id, 'USER_CANCELLED'
    );
    COMMIT;
END$$

CREATE PROCEDURE sp_match_wait_requests(
    IN  p_run_id BIGINT UNSIGNED,
    IN  p_seat_type_id SMALLINT UNSIGNED,
    IN  p_batch_size INT UNSIGNED,
    OUT p_matched_count INT UNSIGNED,
    OUT p_skipped_count INT UNSIGNED
)
main: BEGIN
    DECLARE v_iteration INT UNSIGNED DEFAULT 0;
    DECLARE v_not_found BOOLEAN DEFAULT FALSE;
    DECLARE v_stop_for_fairness BOOLEAN DEFAULT FALSE;
    DECLARE v_wait_id BIGINT UNSIGNED;
    DECLARE v_user_id BIGINT UNSIGNED;
    DECLARE v_from_order SMALLINT UNSIGNED;
    DECLARE v_to_order SMALLINT UNSIGNED;
    DECLARE v_position VARCHAR(1);
    DECLARE v_fallback BOOLEAN;
    DECLARE v_skip_count INT UNSIGNED;
    DECLARE v_passengers JSON;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_match_ok BOOLEAN;
    DECLARE v_error_code VARCHAR(128);
    DECLARE v_trace_id VARCHAR(80);
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_wait_processed;
        RESIGNAL;
    END;

    IF p_batch_size IS NULL OR p_batch_size < 1 OR p_batch_size > 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'WAIT_MATCH_BATCH_SIZE_INVALID';
    END IF;
    SET p_matched_count = 0;
    SET p_skipped_count = 0;

    DROP TEMPORARY TABLE IF EXISTS tmp_wait_processed;
    CREATE TEMPORARY TABLE tmp_wait_processed (
        wait_request_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
    ) ENGINE=MEMORY;

    -- 过截止时间的请求先进入终态；崩溃遗留的 MATCHING 五分钟后可重新领取。
    UPDATE wait_request
       SET wait_status = 'EXPIRED', matching_started_at = NULL,
           last_error_code = 'WAIT_CUTOFF_REACHED', version = version + 1
     WHERE run_id = p_run_id AND seat_type_id = p_seat_type_id
       AND wait_status IN ('WAITING', 'MATCHING') AND cutoff_at <= NOW(6);

    match_loop: WHILE v_iteration < p_batch_size
                      AND NOT v_stop_for_fairness DO
        SET v_not_found = FALSE;
        START TRANSACTION;
        BEGIN
            DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_not_found = TRUE;
            SELECT wr.wait_request_id, wr.user_id, wr.from_order, wr.to_order,
                   wr.requested_position_code, wr.allow_position_fallback,
                   wr.skip_count
              INTO v_wait_id, v_user_id, v_from_order, v_to_order,
                   v_position, v_fallback, v_skip_count
              FROM wait_request AS wr
             WHERE wr.run_id = p_run_id
               AND wr.seat_type_id = p_seat_type_id
               AND wr.cutoff_at > NOW(6)
               AND (
                    wr.wait_status = 'WAITING'
                    OR (wr.wait_status = 'MATCHING'
                        AND wr.matching_started_at < TIMESTAMPADD(MINUTE, -5, NOW(6)))
               )
               AND NOT EXISTS (
                    SELECT 1 FROM tmp_wait_processed AS twp
                     WHERE twp.wait_request_id = wr.wait_request_id
               )
             ORDER BY
               CASE WHEN wr.skip_count >= 3 THEN 0 ELSE 1 END,
               wr.created_at, wr.wait_request_id
             LIMIT 1 FOR UPDATE SKIP LOCKED;
        END;
        IF v_not_found THEN
            COMMIT;
            LEAVE match_loop;
        END IF;

        UPDATE wait_request
           SET wait_status = 'MATCHING', matching_started_at = NOW(6),
               retry_count = retry_count + 1, version = version + 1
         WHERE wait_request_id = v_wait_id;
        INSERT INTO tmp_wait_processed VALUES (v_wait_id);
        COMMIT;

        SELECT JSON_ARRAYAGG(passenger_id) INTO v_passengers
          FROM wait_passenger WHERE wait_request_id = v_wait_id;
        SET v_match_ok = TRUE;
        SET v_error_code = NULL;
        BEGIN
            DECLARE CONTINUE HANDLER FOR SQLEXCEPTION
            BEGIN
                GET DIAGNOSTICS CONDITION 1 v_error_code = MESSAGE_TEXT;
                SET v_match_ok = FALSE;
            END;
            CALL sp_create_order_hold(
                v_user_id, p_run_id, v_from_order, v_to_order,
                p_seat_type_id, v_position, v_fallback, v_passengers,
                CONCAT('WAIT-', v_wait_id), 600, v_order_id
            );
        END;

        START TRANSACTION;
        SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
        IF v_match_ok THEN
            UPDATE ticket_order
               SET order_source = 'WAITLIST'
             WHERE order_id = v_order_id;
            UPDATE wait_request
               SET wait_status = 'MATCHED_HOLD', matched_order_id = v_order_id,
                   matching_started_at = NULL, last_error_code = NULL,
                   version = version + 1
             WHERE wait_request_id = v_wait_id AND wait_status = 'MATCHING';
            INSERT INTO wait_request_event (
                wait_request_id, event_type, from_status, to_status,
                trace_id, reason_code, event_data
            ) VALUES (
                v_wait_id, 'WAIT_MATCHED', 'MATCHING', 'MATCHED_HOLD',
                v_trace_id, 'WHOLE_ORDER_MATCHED',
                JSON_OBJECT('orderId', v_order_id)
            );
            SET p_matched_count = p_matched_count + 1;
        ELSEIF v_error_code IN (
            'ORDER_INSUFFICIENT_INVENTORY',
            'ORDER_PREFERRED_POSITION_UNAVAILABLE'
        ) THEN
            UPDATE wait_request
               SET wait_status = 'WAITING', skip_count = skip_count + 1,
                   matching_started_at = NULL, last_error_code = v_error_code,
                   version = version + 1
             WHERE wait_request_id = v_wait_id AND wait_status = 'MATCHING';
            INSERT INTO wait_request_event (
                wait_request_id, event_type, from_status, to_status,
                trace_id, reason_code,
                event_data
            ) VALUES (
                v_wait_id, 'WAIT_SKIPPED', 'MATCHING', 'WAITING',
                v_trace_id, v_error_code,
                JSON_OBJECT('skipCount', v_skip_count + 1)
            );
            SET p_skipped_count = p_skipped_count + 1;
            IF v_skip_count + 1 >= 3 THEN
                SET v_stop_for_fairness = TRUE;
            END IF;
        ELSE
            UPDATE wait_request
               SET wait_status = 'CANCELLED', matching_started_at = NULL,
                   last_error_code = v_error_code, version = version + 1
             WHERE wait_request_id = v_wait_id AND wait_status = 'MATCHING';
            INSERT INTO wait_request_event (
                wait_request_id, event_type, from_status, to_status,
                trace_id, reason_code
            ) VALUES (
                v_wait_id, 'WAIT_MATCH_FAILED', 'MATCHING', 'CANCELLED',
                v_trace_id, v_error_code
            );
        END IF;
        COMMIT;
        SET v_iteration = v_iteration + 1;
    END WHILE;

    DROP TEMPORARY TABLE tmp_wait_processed;
END$$

CREATE TRIGGER trg_ticket_order_sync_wait_status
AFTER UPDATE ON ticket_order
FOR EACH ROW
BEGIN
    IF NEW.order_status <> OLD.order_status THEN
        IF NEW.order_status = 'PAID' THEN
            UPDATE wait_request
               SET wait_status = 'FULFILLED', version = version + 1
             WHERE matched_order_id = NEW.order_id
               AND wait_status = 'MATCHED_HOLD';
        ELSEIF NEW.order_status IN ('CANCELLED', 'TIMEOUT') THEN
            UPDATE wait_request
               SET wait_status = 'EXPIRED', version = version + 1,
                   last_error_code = CONCAT('MATCHED_ORDER_', NEW.order_status)
             WHERE matched_order_id = NEW.order_id
               AND wait_status = 'MATCHED_HOLD';
        END IF;
    END IF;
END$$

DELIMITER ;

CREATE VIEW v_wait_queue AS
SELECT
    wr.wait_request_id,
    wr.wait_request_no,
    wr.run_id,
    wr.seat_type_id,
    wr.from_order,
    wr.to_order,
    wr.requested_position_code,
    wr.allow_position_fallback,
    wr.passenger_count,
    wr.wait_status,
    wr.skip_count,
    wr.retry_count,
    wr.cutoff_at,
    wr.matched_order_id,
    CASE WHEN wr.skip_count >= 3 THEN TRUE ELSE FALSE END AS fairness_protected,
    ROW_NUMBER() OVER (
        PARTITION BY wr.run_id, wr.seat_type_id
        ORDER BY CASE WHEN wr.skip_count >= 3 THEN 0 ELSE 1 END,
                 wr.created_at, wr.wait_request_id
    ) AS queue_position
FROM wait_request AS wr
WHERE wr.wait_status IN ('WAITING', 'MATCHING');
