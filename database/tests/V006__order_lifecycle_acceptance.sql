-- 仅用于隔离测试库；会创建最小编组与交易数据，不得对 CR12306 正式库执行。
USE CR12306_v006_check;

INSERT INTO seat_type (seat_type_code, seat_type_name, display_order)
VALUES ('V006_TEST', 'V006测试席', 999);
SET @seat_type_id = LAST_INSERT_ID();

INSERT INTO formation_template (
    formation_code, formation_name, applicable_train_type, description
) VALUES ('V006_TEST', 'V006隔离测试编组', 'TEST', '仅验收脚本使用');
SET @formation_id = LAST_INSERT_ID();

INSERT INTO carriage_template (
    formation_id, carriage_no, carriage_code, carriage_name
) VALUES (@formation_id, 1, 'C01', '测试车厢');
SET @carriage_id = LAST_INSERT_ID();

INSERT INTO seat (carriage_id, seat_type_id, seat_no, row_no, position_code)
VALUES
    (@carriage_id, @seat_type_id, '01A', 1, 'A'),
    (@carriage_id, @seat_type_id, '01B', 1, 'B'),
    (@carriage_id, @seat_type_id, '01C', 1, 'C');

UPDATE train_run
   SET formation_id = @formation_id,
       run_status = 'ON_SALE',
       sale_start_at = TIMESTAMP(service_date, '00:00:00'),
       sale_end_at = TIMESTAMPADD(DAY, 2, TIMESTAMP(service_date, '00:00:00'))
 WHERE run_id = 1;

INSERT INTO train_run_seat (run_id, seat_id)
SELECT 1, seat_id FROM seat WHERE carriage_id = @carriage_id;

INSERT INTO run_fare (run_id, from_order, to_order, seat_type_id, amount)
VALUES
    (1, 1, 3, @seat_type_id, 100.00),
    (1, 2, 4, @seat_type_id, 100.00),
    (1, 3, 4, @seat_type_id, 40.00);

INSERT INTO app_user (username, password_hash)
VALUES ('v006_test_user', 'not-a-real-password-hash');
SET @user_id = LAST_INSERT_ID();

INSERT INTO passenger (
    owner_user_id, passenger_name, document_type, document_hash
) VALUES (
    @user_id, 'V006测试乘车人', 'SIMULATED', UNHEX(SHA2('v006-passenger', 256))
);
SET @passenger_id = LAST_INSERT_ID();

DELIMITER $$

DROP PROCEDURE IF EXISTS run_v006_acceptance$$
CREATE PROCEDURE run_v006_acceptance()
BEGIN
    DECLARE v_order_paid BIGINT UNSIGNED;
    DECLARE v_order_timeout BIGINT UNSIGNED;
    DECLARE v_conflict_order BIGINT UNSIGNED;
    DECLARE v_payment_id BIGINT UNSIGNED;
    DECLARE v_refund_id_1 BIGINT UNSIGNED;
    DECLARE v_refund_id_2 BIGINT UNSIGNED;
    DECLARE v_expired_count INT UNSIGNED;
    DECLARE v_conflict_seen BOOLEAN DEFAULT FALSE;
    DECLARE v_count INT DEFAULT 0;

    CALL sp_create_order_hold(
        @user_id, 1, 1, 3, @seat_type_id,
        'A', TRUE, JSON_ARRAY(@passenger_id),
        'v006-paid-order', 300, v_order_paid
    );
    CALL sp_confirm_order_payment(
        @user_id, v_order_paid, 'v006-payment', 'v006-channel',
        100.00, v_payment_id
    );

    BEGIN
        DECLARE CONTINUE HANDLER FOR SQLEXCEPTION SET v_conflict_seen = TRUE;
        CALL sp_create_order_hold(
            @user_id, 1, 2, 4, @seat_type_id,
            NULL, TRUE, JSON_ARRAY(@passenger_id),
            'v006-conflict-order', 300, v_conflict_order
        );
    END;
    IF NOT v_conflict_seen THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_EXPECTED_CONFLICT_NOT_RAISED';
    END IF;
    SELECT COUNT(*) INTO v_count FROM ticket_order
     WHERE idempotency_key = 'v006-conflict-order';
    IF v_count <> 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_CONFLICT_ORDER_NOT_ROLLED_BACK';
    END IF;

    CALL sp_refund_paid_order(
        @user_id, v_order_paid, 'v006-refund', 'TEST_REFUND', v_refund_id_1
    );
    CALL sp_refund_paid_order(
        @user_id, v_order_paid, 'v006-refund', 'TEST_REFUND', v_refund_id_2
    );
    IF v_refund_id_1 <> v_refund_id_2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_REFUND_NOT_IDEMPOTENT';
    END IF;

    CALL sp_create_order_hold(
        @user_id, 1, 3, 4, @seat_type_id,
        'F', TRUE, JSON_ARRAY(@passenger_id),
        'v006-timeout-order', 300, v_order_timeout
    );
    UPDATE ticket_order SET expires_at = TIMESTAMPADD(SECOND, -1, NOW(6))
     WHERE order_id = v_order_timeout;
    UPDATE seat_allocation AS sa
    JOIN order_item AS oi ON oi.order_item_id = sa.order_item_id
       SET sa.held_until = TIMESTAMPADD(SECOND, -1, NOW(6))
     WHERE oi.order_id = v_order_timeout;

    CALL sp_expire_order_holds(10, v_expired_count);
    IF v_expired_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_TIMEOUT_COUNT_INVALID';
    END IF;
    CALL sp_expire_order_holds(10, v_expired_count);
    IF v_expired_count <> 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_TIMEOUT_NOT_IDEMPOTENT';
    END IF;

    SELECT COUNT(*) INTO v_count
      FROM v_inventory_reconciliation WHERE is_consistent = 0;
    IF v_count <> 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_INVENTORY_RECONCILIATION_FAILED';
    END IF;
    SELECT COUNT(*) INTO v_count
      FROM ticket_order
     WHERE (order_id = v_order_paid AND order_status = 'REFUNDED')
        OR (order_id = v_order_timeout AND order_status = 'TIMEOUT');
    IF v_count <> 2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_ORDER_FINAL_STATE_INVALID';
    END IF;
    SELECT COUNT(*) INTO v_count FROM train_run_seat
     WHERE run_id = 1 AND occupied_mask <> 0;
    IF v_count <> 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'TEST_INVENTORY_NOT_FULLY_RELEASED';
    END IF;

    SELECT 'V006_ACCEPTANCE_OK' AS result,
           v_order_paid AS refunded_order_id,
           v_order_timeout AS timeout_order_id,
           v_refund_id_1 AS refund_id;
END$$

DELIMITER ;

CALL run_v006_acceptance();
DROP PROCEDURE run_v006_acceptance;

