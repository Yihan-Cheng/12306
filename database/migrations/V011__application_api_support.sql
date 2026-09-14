-- 长三角 12306 客票综合销售系统
-- V011: 演示应用账户注册过程与订单详情视图
-- 文件编码: UTF-8（无 BOM）；导入时指定 --default-character-set=utf8mb4
-- 前置迁移: V002 ... V010

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

DELIMITER $$

CREATE PROCEDURE sp_register_demo_account(
    IN p_username VARCHAR(64),
    IN p_password_hash VARCHAR(255),
    IN p_passenger_name VARCHAR(80),
    IN p_document_token VARCHAR(200),
    OUT p_user_id BIGINT UNSIGNED,
    OUT p_passenger_id BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_document_hash BINARY(32);
    DECLARE v_existing_owner BIGINT UNSIGNED;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;

    IF p_username IS NULL OR CHAR_LENGTH(TRIM(p_username)) < 3 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='REGISTER_USERNAME_INVALID';
    END IF;
    IF p_password_hash IS NULL OR CHAR_LENGTH(TRIM(p_password_hash)) < 32 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='REGISTER_PASSWORD_HASH_INVALID';
    END IF;
    IF p_passenger_name IS NULL OR CHAR_LENGTH(TRIM(p_passenger_name)) < 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='REGISTER_PASSENGER_NAME_INVALID';
    END IF;
    IF p_document_token IS NULL OR CHAR_LENGTH(TRIM(p_document_token)) < 4 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='REGISTER_DOCUMENT_TOKEN_INVALID';
    END IF;

    SET v_document_hash = UNHEX(SHA2(p_document_token, 256));
    START TRANSACTION;
    INSERT INTO app_user (username, password_hash, user_status)
    VALUES (TRIM(p_username), p_password_hash, 'ACTIVE')
    ON DUPLICATE KEY UPDATE user_id=LAST_INSERT_ID(user_id);
    SET p_user_id = LAST_INSERT_ID();

    SELECT MAX(owner_user_id) INTO v_existing_owner
      FROM passenger
     WHERE document_type='SIMULATED' AND document_hash=v_document_hash;
    IF v_existing_owner IS NOT NULL AND v_existing_owner<>p_user_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='REGISTER_DOCUMENT_ALREADY_BOUND';
    END IF;

    INSERT INTO passenger (
        owner_user_id, passenger_name, document_type,
        document_hash, passenger_status
    ) VALUES (
        p_user_id, TRIM(p_passenger_name), 'SIMULATED',
        v_document_hash, 'ACTIVE'
    )
    ON DUPLICATE KEY UPDATE
        passenger_id=LAST_INSERT_ID(passenger_id),
        passenger_name=VALUES(passenger_name),
        passenger_status='ACTIVE';
    SET p_passenger_id = LAST_INSERT_ID();
    COMMIT;
END$$

DELIMITER ;

CREATE VIEW v_order_detail AS
SELECT
    o.order_id,
    o.order_no,
    o.user_id,
    o.order_status,
    o.total_amount,
    o.expires_at,
    o.order_source,
    o.created_at,
    oi.order_item_id,
    oi.passenger_id,
    p.passenger_name,
    tr.train_no,
    oi.run_id,
    origin.station_id AS from_station_id,
    origin_station.station_name AS from_station_name,
    origin.departure_at,
    destination.station_id AS to_station_id,
    destination_station.station_name AS to_station_name,
    destination.arrival_at,
    st.seat_type_name,
    oi.requested_position_code,
    sa.allocated_position_code,
    sa.allocation_strategy,
    ct.carriage_no,
    s.seat_no,
    oi.price_snapshot,
    oi.item_status,
    sa.allocation_status
FROM ticket_order AS o
JOIN order_item AS oi ON oi.order_id=o.order_id
JOIN passenger AS p ON p.passenger_id=oi.passenger_id
JOIN train_run AS tr ON tr.run_id=oi.run_id
JOIN v_train_run_stop AS origin
  ON origin.run_id=oi.run_id AND origin.station_order=oi.from_order
JOIN station AS origin_station ON origin_station.station_id=origin.station_id
JOIN v_train_run_stop AS destination
  ON destination.run_id=oi.run_id AND destination.station_order=oi.to_order
JOIN station AS destination_station
  ON destination_station.station_id=destination.station_id
JOIN seat_type AS st ON st.seat_type_id=oi.seat_type_id
LEFT JOIN seat_allocation AS sa ON sa.order_item_id=oi.order_item_id
LEFT JOIN seat AS s ON s.seat_id=sa.seat_id
LEFT JOIN carriage_template AS ct ON ct.carriage_id=s.carriage_id;

