-- 长三角 12306 客票综合销售系统
-- V006: 乘车人行程冲突、支付超时释放、已支付退款
-- 前置迁移: V002, V003, V004, V005
-- 目标版本: MySQL 8.4+
-- 本迁移不插入编组、席位或运载量数据。

USE CR12306;

CREATE TABLE refund (
    refund_id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id           BIGINT UNSIGNED NOT NULL,
    refund_request_no  VARCHAR(64) NOT NULL,
    refund_status      VARCHAR(20) NOT NULL,
    amount             DECIMAL(12, 2) NOT NULL,
    reason_code        VARCHAR(40) NOT NULL,
    refunded_at        DATETIME(6) NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (refund_id),
    UNIQUE KEY uk_refund_request_no (refund_request_no),
    UNIQUE KEY uk_refund_order (order_id),
    KEY idx_refund_status_time (refund_status, created_at, refund_id),
    CONSTRAINT fk_refund_order
        FOREIGN KEY (order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_refund_amount CHECK (amount >= 0),
    CONSTRAINT chk_refund_status
        CHECK (refund_status IN ('REQUESTED', 'SUCCESS', 'FAILED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='订单退款请求及结果；请求号和订单均幂等';

DELIMITER $$

CREATE TRIGGER trg_order_item_passenger_itinerary_guard
BEFORE INSERT ON order_item
FOR EACH ROW
guard: BEGIN
    DECLARE v_passenger_lock BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_departure_at DATETIME(6) DEFAULT NULL;
    DECLARE v_arrival_at DATETIME(6) DEFAULT NULL;
    DECLARE v_conflict_count INT UNSIGNED DEFAULT 0;

    IF NEW.item_status NOT IN ('HELD', 'CONFIRMED') THEN
        LEAVE guard;
    END IF;

    SELECT passenger_id INTO v_passenger_lock
      FROM passenger
     WHERE passenger_id = NEW.passenger_id
     FOR UPDATE;

    SELECT origin.departure_at, destination.arrival_at
      INTO v_departure_at, v_arrival_at
      FROM v_train_run_stop AS origin
      JOIN v_train_run_stop AS destination
        ON destination.run_id = origin.run_id
     WHERE origin.run_id = NEW.run_id
       AND origin.station_order = NEW.from_order
       AND destination.station_order = NEW.to_order;

    IF v_departure_at IS NULL OR v_arrival_at IS NULL
       OR v_arrival_at <= v_departure_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PASSENGER_ITINERARY_TIME_INVALID';
    END IF;

    SELECT COUNT(*) INTO v_conflict_count
      FROM order_item AS oi
      JOIN v_train_run_stop AS existing_origin
        ON existing_origin.run_id = oi.run_id
       AND existing_origin.station_order = oi.from_order
      JOIN v_train_run_stop AS existing_destination
        ON existing_destination.run_id = oi.run_id
       AND existing_destination.station_order = oi.to_order
     WHERE oi.passenger_id = NEW.passenger_id
       AND oi.item_status IN ('HELD', 'CONFIRMED')
       AND existing_origin.departure_at < v_arrival_at
       AND existing_destination.arrival_at > v_departure_at;

    IF v_conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PASSENGER_ITINERARY_CONFLICT';
    END IF;
END$$

CREATE PROCEDURE sp_expire_order_holds(
    IN  p_batch_size    INT UNSIGNED,
    OUT p_expired_count INT UNSIGNED
)
proc: BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_id BIGINT UNSIGNED;
    DECLARE v_allocation_id BIGINT UNSIGNED;
    DECLARE v_order_item_id BIGINT UNSIGNED;
    DECLARE v_run_id BIGINT UNSIGNED;
    DECLARE v_seat_id BIGINT UNSIGNED;
    DECLARE v_segment_mask BIGINT UNSIGNED;
    DECLARE v_mask_before BIGINT UNSIGNED;
    DECLARE v_mask_after BIGINT UNSIGNED;
    DECLARE v_trace_id VARCHAR(80);

    DECLARE cur_order CURSOR FOR
        SELECT order_id FROM tmp_expired_order ORDER BY order_id;
    DECLARE cur_allocation CURSOR FOR
        SELECT sa.allocation_id, sa.order_item_id, sa.run_id,
               sa.seat_id, sa.segment_mask
          FROM seat_allocation AS sa
          JOIN order_item AS oi ON oi.order_item_id = sa.order_item_id
          JOIN tmp_expired_order AS teo ON teo.order_id = oi.order_id
         WHERE sa.allocation_status = 'HOLD'
         ORDER BY sa.run_id, sa.seat_id, sa.allocation_id
         FOR UPDATE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_expired_order;
        RESIGNAL;
    END;

    IF p_batch_size IS NULL OR p_batch_size < 1 OR p_batch_size > 1000 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'EXPIRE_BATCH_SIZE_INVALID';
    END IF;

    SET p_expired_count = 0;
    DROP TEMPORARY TABLE IF EXISTS tmp_expired_order;
    CREATE TEMPORARY TABLE tmp_expired_order (
        order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
    ) ENGINE=MEMORY;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    INSERT INTO tmp_expired_order (order_id)
    SELECT order_id
      FROM ticket_order
     WHERE order_status = 'PENDING_PAYMENT'
       AND expires_at <= NOW(6)
     ORDER BY expires_at, order_id
     LIMIT p_batch_size
     FOR UPDATE SKIP LOCKED;

    SELECT COUNT(*) INTO p_expired_count FROM tmp_expired_order;
    IF p_expired_count = 0 THEN
        COMMIT;
        DROP TEMPORARY TABLE IF EXISTS tmp_expired_order;
        LEAVE proc;
    END IF;

    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));
    SET v_done = FALSE;
    OPEN cur_allocation;
    allocation_loop: LOOP
        FETCH cur_allocation INTO v_allocation_id, v_order_item_id,
                                  v_run_id, v_seat_id, v_segment_mask;
        IF v_done THEN LEAVE allocation_loop; END IF;

        SELECT occupied_mask INTO v_mask_before
          FROM train_run_seat
         WHERE run_id = v_run_id AND seat_id = v_seat_id
         FOR UPDATE;
        IF (v_mask_before & v_segment_mask) <> v_segment_mask THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'EXPIRE_INVENTORY_RECONCILIATION_FAILED';
        END IF;

        SET v_mask_after = v_mask_before & ~v_segment_mask;
        UPDATE train_run_seat
           SET occupied_mask = v_mask_after, version = version + 1
         WHERE run_id = v_run_id AND seat_id = v_seat_id;
        UPDATE seat_allocation
           SET allocation_status = 'RELEASED', held_until = NULL,
               released_at = NOW(6), release_reason = 'PAYMENT_TIMEOUT',
               version = version + 1
         WHERE allocation_id = v_allocation_id
           AND allocation_status = 'HOLD';
        INSERT INTO inventory_event (
            run_id, seat_id, allocation_id, order_item_id, event_type,
            segment_mask, mask_before, mask_after, trace_id, reason_code
        ) VALUES (
            v_run_id, v_seat_id, v_allocation_id, v_order_item_id, 'RELEASE',
            v_segment_mask, v_mask_before, v_mask_after,
            v_trace_id, 'PAYMENT_TIMEOUT'
        );
    END LOOP;
    CLOSE cur_allocation;

    UPDATE order_item AS oi
    JOIN tmp_expired_order AS teo ON teo.order_id = oi.order_id
       SET oi.item_status = 'TIMEOUT'
     WHERE oi.item_status = 'HELD';

    UPDATE ticket_order AS o
    JOIN tmp_expired_order AS teo ON teo.order_id = o.order_id
       SET o.order_status = 'TIMEOUT', o.version = o.version + 1
     WHERE o.order_status = 'PENDING_PAYMENT';

    SET v_done = FALSE;
    OPEN cur_order;
    order_loop: LOOP
        FETCH cur_order INTO v_order_id;
        IF v_done THEN LEAVE order_loop; END IF;
        INSERT INTO order_event (
            order_id, event_type, from_status, to_status,
            actor_type, actor_id, trace_id, reason_code
        ) VALUES (
            v_order_id, 'ORDER_PAYMENT_TIMEOUT', 'PENDING_PAYMENT', 'TIMEOUT',
            'SYSTEM', 'hold-expirer', v_trace_id, 'PAYMENT_TIMEOUT'
        );
    END LOOP;
    CLOSE cur_order;

    COMMIT;
    DROP TEMPORARY TABLE IF EXISTS tmp_expired_order;
END$$

CREATE PROCEDURE sp_refund_paid_order(
    IN  p_user_id           BIGINT UNSIGNED,
    IN  p_order_id          BIGINT UNSIGNED,
    IN  p_refund_request_no VARCHAR(64),
    IN  p_reason_code       VARCHAR(40),
    OUT p_refund_id         BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_done BOOLEAN DEFAULT FALSE;
    DECLARE v_order_user_id BIGINT UNSIGNED;
    DECLARE v_order_status VARCHAR(24);
    DECLARE v_total_amount DECIMAL(12, 2);
    DECLARE v_existing_order_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_allocation_id BIGINT UNSIGNED;
    DECLARE v_order_item_id BIGINT UNSIGNED;
    DECLARE v_run_id BIGINT UNSIGNED;
    DECLARE v_seat_id BIGINT UNSIGNED;
    DECLARE v_segment_mask BIGINT UNSIGNED;
    DECLARE v_mask_before BIGINT UNSIGNED;
    DECLARE v_mask_after BIGINT UNSIGNED;
    DECLARE v_trace_id VARCHAR(80);

    DECLARE cur_allocation CURSOR FOR
        SELECT sa.allocation_id, sa.order_item_id, sa.run_id,
               sa.seat_id, sa.segment_mask
          FROM seat_allocation AS sa
          JOIN order_item AS oi ON oi.order_item_id = sa.order_item_id
         WHERE oi.order_id = p_order_id
           AND sa.allocation_status = 'CONFIRMED'
         ORDER BY sa.run_id, sa.seat_id, sa.allocation_id
         FOR UPDATE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND SET v_done = TRUE;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    IF p_refund_request_no IS NULL OR CHAR_LENGTH(TRIM(p_refund_request_no)) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_REQUEST_NO_REQUIRED';
    END IF;
    IF p_reason_code IS NULL OR CHAR_LENGTH(TRIM(p_reason_code)) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_REASON_REQUIRED';
    END IF;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    SET v_done = FALSE;
    SELECT refund_id, order_id INTO p_refund_id, v_existing_order_id
      FROM refund WHERE refund_request_no = p_refund_request_no
      FOR UPDATE;
    IF NOT v_done THEN
        IF v_existing_order_id <> p_order_id THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_IDEMPOTENCY_CONFLICT';
        END IF;
        COMMIT;
        LEAVE proc;
    END IF;

    SET v_done = FALSE;
    SELECT user_id, order_status, total_amount
      INTO v_order_user_id, v_order_status, v_total_amount
      FROM ticket_order WHERE order_id = p_order_id FOR UPDATE;
    IF v_done THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_ORDER_NOT_FOUND';
    END IF;
    IF v_order_user_id <> p_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_ORDER_NOT_OWNED';
    END IF;
    IF v_order_status <> 'PAID' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'REFUND_ORDER_STATE_INVALID';
    END IF;

    INSERT INTO refund (
        order_id, refund_request_no, refund_status,
        amount, reason_code, refunded_at
    ) VALUES (
        p_order_id, p_refund_request_no, 'SUCCESS',
        v_total_amount, p_reason_code, NOW(6)
    );
    SET p_refund_id = LAST_INSERT_ID();
    SET v_trace_id = CONCAT('T', UPPER(REPLACE(UUID(), '-', '')));

    SET v_done = FALSE;
    OPEN cur_allocation;
    release_loop: LOOP
        FETCH cur_allocation INTO v_allocation_id, v_order_item_id,
                                  v_run_id, v_seat_id, v_segment_mask;
        IF v_done THEN LEAVE release_loop; END IF;

        SELECT occupied_mask INTO v_mask_before
          FROM train_run_seat
         WHERE run_id = v_run_id AND seat_id = v_seat_id
         FOR UPDATE;
        IF (v_mask_before & v_segment_mask) <> v_segment_mask THEN
            SIGNAL SQLSTATE '45000'
                SET MESSAGE_TEXT = 'REFUND_INVENTORY_RECONCILIATION_FAILED';
        END IF;
        SET v_mask_after = v_mask_before & ~v_segment_mask;
        UPDATE train_run_seat
           SET occupied_mask = v_mask_after, version = version + 1
         WHERE run_id = v_run_id AND seat_id = v_seat_id;
        UPDATE seat_allocation
           SET allocation_status = 'RELEASED', held_until = NULL,
               released_at = NOW(6), release_reason = 'USER_REFUND',
               version = version + 1
         WHERE allocation_id = v_allocation_id
           AND allocation_status = 'CONFIRMED';
        INSERT INTO inventory_event (
            run_id, seat_id, allocation_id, order_item_id, event_type,
            segment_mask, mask_before, mask_after, trace_id, reason_code
        ) VALUES (
            v_run_id, v_seat_id, v_allocation_id, v_order_item_id, 'RELEASE',
            v_segment_mask, v_mask_before, v_mask_after,
            v_trace_id, 'USER_REFUND'
        );
    END LOOP;
    CLOSE cur_allocation;

    UPDATE order_item SET item_status = 'REFUNDED'
     WHERE order_id = p_order_id AND item_status = 'CONFIRMED';
    UPDATE payment SET payment_status = 'REFUNDED'
     WHERE order_id = p_order_id AND payment_status = 'SUCCESS';
    UPDATE ticket_order
       SET order_status = 'REFUNDED', version = version + 1
     WHERE order_id = p_order_id AND order_status = 'PAID';
    INSERT INTO order_event (
        order_id, event_type, from_status, to_status,
        actor_type, actor_id, trace_id, reason_code,
        event_data
    ) VALUES (
        p_order_id, 'ORDER_REFUNDED', 'PAID', 'REFUNDED',
        'USER', CAST(p_user_id AS CHAR), v_trace_id, p_reason_code,
        JSON_OBJECT('refundId', p_refund_id, 'amount', v_total_amount)
    );

    COMMIT;
END$$

DELIMITER ;

