-- 仅用于 CR12306_v009_check 隔离库。
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306_v009_check;

SET @run_id = 1;
SELECT MIN(s.seat_type_id) INTO @seat_type_id
  FROM train_run AS tr
  JOIN carriage_template AS ct ON ct.formation_id = tr.formation_id
  JOIN seat AS s ON s.carriage_id = ct.carriage_id
 WHERE tr.run_id = @run_id;

INSERT INTO app_user (username, password_hash)
VALUES ('v009_test_user', 'not-a-real-password-hash');
SET @user_id = LAST_INSERT_ID();

INSERT INTO passenger (
    owner_user_id, passenger_name, document_type, document_hash
) VALUES
(@user_id, '候补测试乘车人一', 'SIMULATED', UNHEX(SHA2('v009-p1', 256))),
(@user_id, '候补测试乘车人二', 'SIMULATED', UNHEX(SHA2('v009-p2', 256))),
(@user_id, '候补测试乘车人三', 'SIMULATED', UNHEX(SHA2('v009-p3', 256))),
(@user_id, '候补测试乘车人四', 'SIMULATED', UNHEX(SHA2('v009-p4', 256)));
SELECT passenger_id INTO @p1 FROM passenger WHERE document_hash=UNHEX(SHA2('v009-p1',256));
SELECT passenger_id INTO @p2 FROM passenger WHERE document_hash=UNHEX(SHA2('v009-p2',256));
SELECT passenger_id INTO @p3 FROM passenger WHERE document_hash=UNHEX(SHA2('v009-p3',256));
SELECT passenger_id INTO @p4 FROM passenger WHERE document_hash=UNHEX(SHA2('v009-p4',256));

DELIMITER $$

DROP PROCEDURE IF EXISTS run_v009_acceptance$$
CREATE PROCEDURE run_v009_acceptance()
BEGIN
    DECLARE v_direct_rejected BOOLEAN DEFAULT FALSE;
    DECLARE v_wait_big BIGINT UNSIGNED;
    DECLARE v_wait_big_retry BIGINT UNSIGNED;
    DECLARE v_wait_small BIGINT UNSIGNED;
    DECLARE v_wait_timeout BIGINT UNSIGNED;
    DECLARE v_order_small BIGINT UNSIGNED;
    DECLARE v_order_big BIGINT UNSIGNED;
    DECLARE v_order_timeout BIGINT UNSIGNED;
    DECLARE v_payment_id BIGINT UNSIGNED;
    DECLARE v_refund_id BIGINT UNSIGNED;
    DECLARE v_amount DECIMAL(12,2);
    DECLARE v_matched INT UNSIGNED;
    DECLARE v_skipped INT UNSIGNED;
    DECLARE v_expired INT UNSIGNED;
    DECLARE v_count INT UNSIGNED;

    -- 尚有充足直达余票时，禁止创建候补。
    BEGIN
        DECLARE CONTINUE HANDLER FOR SQLEXCEPTION SET v_direct_rejected = TRUE;
        CALL sp_create_wait_request(
            @user_id, @run_id, 1, 2, @seat_type_id,
            NULL, TRUE, JSON_ARRAY(@p1), 'v009-direct-reject',
            TIMESTAMPADD(DAY,1,NOW(6)), @ignored_wait
        );
    END;
    IF NOT v_direct_rejected THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_DIRECT_INVENTORY_NOT_REJECTED';
    END IF;

    -- 测试夹具：占满第一个区间；这些模拟占位会在测试末尾清除。
    UPDATE train_run_seat SET occupied_mask = occupied_mask | 1
     WHERE run_id = @run_id;

    CALL sp_create_wait_request(
        @user_id, @run_id, 1, 2, @seat_type_id,
        NULL, TRUE, JSON_ARRAY(@p1,@p2), 'v009-big',
        TIMESTAMPADD(DAY,1,NOW(6)), v_wait_big
    );
    CALL sp_create_wait_request(
        @user_id, @run_id, 1, 2, @seat_type_id,
        NULL, TRUE, JSON_ARRAY(@p1,@p2), 'v009-big',
        TIMESTAMPADD(DAY,1,NOW(6)), v_wait_big_retry
    );
    IF v_wait_big <> v_wait_big_retry THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_WAIT_NOT_IDEMPOTENT';
    END IF;

    CALL sp_create_wait_request(
        @user_id, @run_id, 1, 2, @seat_type_id,
        NULL, TRUE, JSON_ARRAY(@p3), 'v009-small',
        TIMESTAMPADD(DAY,1,NOW(6)), v_wait_small
    );

    -- 只释放一席：两人请求整单失败并被越过，后一人请求兑现。
    UPDATE train_run_seat SET occupied_mask = occupied_mask & ~1
     WHERE run_id=@run_id ORDER BY seat_id LIMIT 1;
    CALL sp_match_wait_requests(@run_id,@seat_type_id,10,v_matched,v_skipped);
    IF v_matched<>1 OR v_skipped<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_BOUNDED_BYPASS_INVALID';
    END IF;
    SELECT matched_order_id INTO v_order_small FROM wait_request
     WHERE wait_request_id=v_wait_small;
    SELECT total_amount INTO v_amount FROM ticket_order WHERE order_id=v_order_small;
    CALL sp_confirm_order_payment(
        @user_id,v_order_small,'v009-pay-small','v009-trade-small',v_amount,v_payment_id
    );
    SELECT COUNT(*) INTO v_count FROM wait_request
     WHERE wait_request_id=v_wait_small AND wait_status='FULFILLED';
    IF v_count<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_PAID_WAIT_NOT_FULFILLED';
    END IF;

    -- 无新增余票，再失败两轮后 skip_count=3，进入公平保护。
    CALL sp_match_wait_requests(@run_id,@seat_type_id,10,v_matched,v_skipped);
    CALL sp_match_wait_requests(@run_id,@seat_type_id,10,v_matched,v_skipped);
    SELECT COUNT(*) INTO v_count FROM wait_request
     WHERE wait_request_id=v_wait_big AND wait_status='WAITING'
       AND skip_count=3;
    IF v_count<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_FAIRNESS_PROTECTION_INVALID';
    END IF;

    -- 释放两席后，受保护的两人请求整单兑现。
    UPDATE train_run_seat SET occupied_mask = occupied_mask & ~1
     WHERE run_id=@run_id AND (occupied_mask & 1)=1
       AND NOT EXISTS (
           SELECT 1 FROM seat_allocation sa
            WHERE sa.run_id=train_run_seat.run_id
              AND sa.seat_id=train_run_seat.seat_id
              AND sa.allocation_status IN ('HOLD','CONFIRMED')
       )
     ORDER BY seat_id LIMIT 2;
    CALL sp_match_wait_requests(@run_id,@seat_type_id,10,v_matched,v_skipped);
    IF v_matched<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_PROTECTED_WAIT_NOT_MATCHED';
    END IF;
    SELECT matched_order_id INTO v_order_big FROM wait_request
     WHERE wait_request_id=v_wait_big;
    SELECT total_amount INTO v_amount FROM ticket_order WHERE order_id=v_order_big;
    CALL sp_confirm_order_payment(
        @user_id,v_order_big,'v009-pay-big','v009-trade-big',v_amount,v_payment_id
    );

    -- 匹配订单支付超时后，候补请求同步进入 EXPIRED。
    CALL sp_create_wait_request(
        @user_id,@run_id,1,2,@seat_type_id,
        NULL,TRUE,JSON_ARRAY(@p4),'v009-timeout',
        TIMESTAMPADD(DAY,1,NOW(6)),v_wait_timeout
    );
    UPDATE train_run_seat SET occupied_mask=occupied_mask & ~1
     WHERE run_id=@run_id AND (occupied_mask & 1)=1
       AND NOT EXISTS (
           SELECT 1 FROM seat_allocation sa
            WHERE sa.run_id=train_run_seat.run_id
              AND sa.seat_id=train_run_seat.seat_id
              AND sa.allocation_status IN ('HOLD','CONFIRMED')
       )
     ORDER BY seat_id LIMIT 1;
    CALL sp_match_wait_requests(@run_id,@seat_type_id,10,v_matched,v_skipped);
    SELECT matched_order_id INTO v_order_timeout FROM wait_request
     WHERE wait_request_id=v_wait_timeout;
    UPDATE ticket_order SET expires_at=TIMESTAMPADD(SECOND,-1,NOW(6))
     WHERE order_id=v_order_timeout;
    UPDATE seat_allocation sa JOIN order_item oi ON oi.order_item_id=sa.order_item_id
       SET sa.held_until=TIMESTAMPADD(SECOND,-1,NOW(6))
     WHERE oi.order_id=v_order_timeout;
    CALL sp_expire_order_holds(10,v_expired);
    SELECT COUNT(*) INTO v_count FROM wait_request
     WHERE wait_request_id=v_wait_timeout AND wait_status='EXPIRED';
    IF v_count<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_TIMEOUT_WAIT_NOT_EXPIRED';
    END IF;

    -- 退款释放真实分配，再移除夹具占位，最终进行位图对账。
    CALL sp_refund_paid_order(@user_id,v_order_small,'v009-ref-small','TEST',v_refund_id);
    CALL sp_refund_paid_order(@user_id,v_order_big,'v009-ref-big','TEST',v_refund_id);
    UPDATE train_run_seat SET occupied_mask=0 WHERE run_id=@run_id;
    SELECT COUNT(*) INTO v_count FROM v_inventory_reconciliation
     WHERE is_consistent=0;
    IF v_count<>0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TEST_FINAL_RECONCILIATION_FAILED';
    END IF;

    SELECT 'V009_ACCEPTANCE_OK' result,
           v_wait_big big_wait_id,v_wait_small small_wait_id,
           v_wait_timeout timeout_wait_id;
END$$

DELIMITER ;

CALL run_v009_acceptance();
DROP PROCEDURE run_v009_acceptance;
