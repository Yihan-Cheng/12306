-- CR12306
-- V013: 管理员认证、数据库削峰缓冲队列与监控读模型
-- 前置迁移: V002 ... V012

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

CREATE TABLE admin_user (
    admin_user_id      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username           VARCHAR(64) NOT NULL,
    display_name       VARCHAR(80) NOT NULL,
    password_salt      BINARY(32) NOT NULL,
    password_hash      BINARY(32) NOT NULL,
    password_iterations INT UNSIGNED NOT NULL DEFAULT 200000,
    admin_status       VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    failed_login_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until       DATETIME(6) NULL,
    last_login_at      DATETIME(6) NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (admin_user_id),
    UNIQUE KEY uk_admin_user_username (username),
    CONSTRAINT chk_admin_user_status
        CHECK (admin_status IN ('ACTIVE', 'LOCKED', 'DISABLED')),
    CONSTRAINT chk_admin_password_iterations
        CHECK (password_iterations BETWEEN 100000 AND 1000000)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='独立于乘客账户的运营管理员；密码使用 PBKDF2-SHA256';

CREATE TABLE admin_session (
    admin_session_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    admin_user_id      BIGINT UNSIGNED NOT NULL,
    token_hash         BINARY(32) NOT NULL,
    expires_at         DATETIME(6) NOT NULL,
    revoked_at         DATETIME(6) NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    last_seen_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (admin_session_id),
    UNIQUE KEY uk_admin_session_token (token_hash),
    KEY idx_admin_session_expiry (expires_at, revoked_at),
    CONSTRAINT fk_admin_session_user
        FOREIGN KEY (admin_user_id) REFERENCES admin_user (admin_user_id)
        ON UPDATE RESTRICT ON DELETE CASCADE,
    CONSTRAINT chk_admin_session_expiry CHECK (expires_at > created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='可撤销的管理员服务端会话，只保存随机令牌的 SHA-256';

CREATE TABLE booking_request_buffer (
    booking_request_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    request_no         VARCHAR(40) NOT NULL,
    user_id            BIGINT UNSIGNED NOT NULL,
    passenger_id       BIGINT UNSIGNED NOT NULL,
    run_id             BIGINT UNSIGNED NOT NULL,
    from_order         SMALLINT UNSIGNED NOT NULL,
    to_order           SMALLINT UNSIGNED NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    requested_position_code VARCHAR(1) NULL,
    allow_position_fallback BOOLEAN NOT NULL DEFAULT TRUE,
    idempotency_key    VARCHAR(80) NOT NULL,
    request_status     VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
    priority_no        SMALLINT NOT NULL DEFAULT 0,
    attempt_count      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    available_at       DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    lease_owner        VARCHAR(80) NULL,
    lease_until        DATETIME(6) NULL,
    result_order_id    BIGINT UNSIGNED NULL,
    error_code         VARCHAR(160) NULL,
    created_at         DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    started_at         DATETIME(6) NULL,
    completed_at       DATETIME(6) NULL,
    PRIMARY KEY (booking_request_id),
    UNIQUE KEY uk_booking_request_no (request_no),
    UNIQUE KEY uk_booking_buffer_idempotency (user_id, idempotency_key),
    KEY idx_booking_buffer_claim
        (request_status, available_at, priority_no, booking_request_id),
    KEY idx_booking_buffer_lease (request_status, lease_until),
    KEY idx_booking_buffer_user (user_id, created_at),
    CONSTRAINT fk_booking_buffer_user
        FOREIGN KEY (user_id) REFERENCES app_user (user_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_booking_buffer_passenger
        FOREIGN KEY (passenger_id) REFERENCES passenger (passenger_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_booking_buffer_run
        FOREIGN KEY (run_id) REFERENCES train_run (run_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_booking_buffer_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_booking_buffer_order
        FOREIGN KEY (result_order_id) REFERENCES ticket_order (order_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_booking_buffer_route
        CHECK (from_order >= 1 AND to_order > from_order AND to_order <= 64),
    CONSTRAINT chk_booking_buffer_position
        CHECK (requested_position_code IS NULL
               OR requested_position_code IN ('A','B','C','D','F')),
    CONSTRAINT chk_booking_buffer_status
        CHECK (request_status IN ('QUEUED','PROCESSING','SUCCEEDED','FAILED','CANCELLED'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='数据库持久化削峰队列；请求可幂等重放、租约恢复和多工作者领取';

DELIMITER $$

CREATE PROCEDURE sp_enqueue_booking_request(
    IN p_user_id BIGINT UNSIGNED,
    IN p_passenger_id BIGINT UNSIGNED,
    IN p_run_id BIGINT UNSIGNED,
    IN p_from_order SMALLINT UNSIGNED,
    IN p_to_order SMALLINT UNSIGNED,
    IN p_seat_type_id SMALLINT UNSIGNED,
    IN p_position_code VARCHAR(1),
    IN p_allow_fallback BOOLEAN,
    IN p_idempotency_key VARCHAR(80),
    OUT p_booking_request_id BIGINT UNSIGNED
)
proc: BEGIN
    DECLARE v_position VARCHAR(1);
    DECLARE v_existing_id BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_existing_match INT DEFAULT 0;
    DECLARE v_valid_count INT DEFAULT 0;

    SET v_position = NULLIF(UPPER(TRIM(p_position_code)), '');
    IF v_position IS NOT NULL AND v_position NOT IN ('A','B','C','D','F') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_POSITION_INVALID';
    END IF;
    IF p_idempotency_key IS NULL OR CHAR_LENGTH(TRIM(p_idempotency_key)) = 0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_IDEMPOTENCY_KEY_REQUIRED';
    END IF;
    IF fn_segment_mask(p_from_order, p_to_order) IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_ROUTE_INVALID';
    END IF;

    SELECT COUNT(*) INTO v_valid_count
      FROM passenger p
      JOIN app_user u ON u.user_id=p.owner_user_id
      JOIN train_run tr ON tr.run_id=p_run_id AND tr.run_status='ON_SALE'
      JOIN run_fare rf ON rf.run_id=p_run_id
                      AND rf.from_order=p_from_order AND rf.to_order=p_to_order
                      AND rf.seat_type_id=p_seat_type_id AND rf.sale_status='OPEN'
     WHERE p.passenger_id=p_passenger_id AND p.owner_user_id=p_user_id
       AND p.passenger_status='ACTIVE' AND u.user_status='ACTIVE';
    IF v_valid_count <> 1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_REQUEST_INVALID';
    END IF;

    SELECT MAX(booking_request_id),COALESCE(SUM(
        passenger_id=p_passenger_id AND run_id=p_run_id
        AND from_order=p_from_order AND to_order=p_to_order
        AND seat_type_id=p_seat_type_id
        AND (requested_position_code <=> v_position)
        AND allow_position_fallback=COALESCE(p_allow_fallback,TRUE)
    ),0) INTO v_existing_id,v_existing_match
      FROM booking_request_buffer
     WHERE user_id=p_user_id AND idempotency_key=p_idempotency_key;
    IF v_existing_id IS NOT NULL THEN
        IF v_existing_match<>1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_IDEMPOTENCY_CONFLICT';
        END IF;
        SET p_booking_request_id=v_existing_id;
        LEAVE proc;
    END IF;

    INSERT IGNORE INTO booking_request_buffer (
        request_no,user_id,passenger_id,run_id,from_order,to_order,seat_type_id,
        requested_position_code,allow_position_fallback,idempotency_key
    ) VALUES (
        CONCAT('B',UPPER(REPLACE(UUID(),'-',''))),p_user_id,p_passenger_id,p_run_id,
        p_from_order,p_to_order,p_seat_type_id,v_position,
        COALESCE(p_allow_fallback,TRUE),p_idempotency_key
    );
    SET p_booking_request_id=LAST_INSERT_ID();
    IF p_booking_request_id=0 THEN
        SELECT MAX(booking_request_id),COALESCE(SUM(
            passenger_id=p_passenger_id AND run_id=p_run_id
            AND from_order=p_from_order AND to_order=p_to_order
            AND seat_type_id=p_seat_type_id
            AND (requested_position_code <=> v_position)
            AND allow_position_fallback=COALESCE(p_allow_fallback,TRUE)
        ),0) INTO p_booking_request_id,v_existing_match
          FROM booking_request_buffer
         WHERE user_id=p_user_id AND idempotency_key=p_idempotency_key;
        IF p_booking_request_id IS NULL OR v_existing_match<>1 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_IDEMPOTENCY_CONFLICT';
        END IF;
    END IF;
END$$

CREATE PROCEDURE sp_claim_booking_requests(
    IN p_worker_id VARCHAR(80),
    IN p_batch_size INT UNSIGNED,
    IN p_lease_seconds INT UNSIGNED
)
proc: BEGIN
    IF p_worker_id IS NULL OR CHAR_LENGTH(TRIM(p_worker_id))=0 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_WORKER_REQUIRED';
    END IF;
    IF p_batch_size IS NULL OR p_batch_size NOT BETWEEN 1 AND 50 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_BATCH_INVALID';
    END IF;
    IF p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 10 AND 600 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_LEASE_INVALID';
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_booking_claim;
    CREATE TEMPORARY TABLE tmp_booking_claim (
        booking_request_id BIGINT UNSIGNED NOT NULL PRIMARY KEY
    ) ENGINE=MEMORY;

    SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
    START TRANSACTION;

    UPDATE booking_request_buffer
       SET request_status='QUEUED',lease_owner=NULL,lease_until=NULL,
           available_at=NOW(6)
     WHERE request_status='PROCESSING' AND lease_until<NOW(6);

    INSERT INTO tmp_booking_claim (booking_request_id)
    SELECT booking_request_id
      FROM booking_request_buffer
     WHERE request_status='QUEUED' AND available_at<=NOW(6)
     ORDER BY priority_no DESC,booking_request_id
     LIMIT p_batch_size
     FOR UPDATE SKIP LOCKED;

    UPDATE booking_request_buffer b
    JOIN tmp_booking_claim c ON c.booking_request_id=b.booking_request_id
       SET b.request_status='PROCESSING',b.lease_owner=p_worker_id,
           b.lease_until=TIMESTAMPADD(SECOND,p_lease_seconds,NOW(6)),
           b.started_at=COALESCE(b.started_at,NOW(6)),
           b.attempt_count=b.attempt_count+1;

    COMMIT;

    SELECT b.* FROM booking_request_buffer b
    JOIN tmp_booking_claim c ON c.booking_request_id=b.booking_request_id
    ORDER BY b.booking_request_id;
    DROP TEMPORARY TABLE IF EXISTS tmp_booking_claim;
END$$

CREATE PROCEDURE sp_complete_booking_request(
    IN p_booking_request_id BIGINT UNSIGNED,
    IN p_worker_id VARCHAR(80),
    IN p_status VARCHAR(20),
    IN p_order_id BIGINT UNSIGNED,
    IN p_error_code VARCHAR(160)
)
BEGIN
    IF p_status NOT IN ('SUCCEEDED','FAILED') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_COMPLETION_STATUS_INVALID';
    END IF;
    UPDATE booking_request_buffer
       SET request_status=p_status,result_order_id=p_order_id,error_code=p_error_code,
           completed_at=NOW(6),lease_owner=NULL,lease_until=NULL
     WHERE booking_request_id=p_booking_request_id
       AND request_status='PROCESSING' AND lease_owner=p_worker_id;
    IF ROW_COUNT()<>1 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='BUFFER_LEASE_LOST';
    END IF;
END$$

DELIMITER ;

CREATE VIEW v_booking_buffer_monitor AS
SELECT
    b.booking_request_id,b.request_no,b.request_status,b.priority_no,
    b.attempt_count,b.available_at,b.lease_owner,b.lease_until,b.error_code,
    b.created_at,b.started_at,b.completed_at,b.result_order_id,
    u.username,p.passenger_name,tr.train_no,st.seat_type_name,
    origin_station.station_name AS from_station_name,
    destination_station.station_name AS to_station_name,
    TIMESTAMPDIFF(MICROSECOND,b.created_at,COALESCE(b.completed_at,NOW(6)))/1000
        AS elapsed_ms
FROM booking_request_buffer b
JOIN app_user u ON u.user_id=b.user_id
JOIN passenger p ON p.passenger_id=b.passenger_id
JOIN train_run tr ON tr.run_id=b.run_id
JOIN seat_type st ON st.seat_type_id=b.seat_type_id
JOIN v_train_run_stop origin
  ON origin.run_id=b.run_id AND origin.station_order=b.from_order
JOIN station origin_station ON origin_station.station_id=origin.station_id
JOIN v_train_run_stop destination
  ON destination.run_id=b.run_id AND destination.station_order=b.to_order
JOIN station destination_station ON destination_station.station_id=destination.station_id;
