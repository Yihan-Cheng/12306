SET NAMES utf8mb4;
USE CR12306;

CREATE TABLE IF NOT EXISTS wait_payment (
    wait_payment_id   BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    wait_request_id   BIGINT UNSIGNED NOT NULL,
    user_id           BIGINT UNSIGNED NOT NULL,
    payment_request_no VARCHAR(64) NOT NULL,
    amount            DECIMAL(12,2) NOT NULL,
    payment_status    VARCHAR(20) NOT NULL DEFAULT 'PAID',
    applied_order_id  BIGINT UNSIGNED NULL,
    paid_at           DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    refunded_at       DATETIME(6) NULL,
    refund_reason     VARCHAR(80) NULL,
    created_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at        TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (wait_payment_id),
    UNIQUE KEY uk_wait_payment_request (wait_request_id),
    UNIQUE KEY uk_wait_payment_no (payment_request_no),
    KEY idx_wait_payment_user_status (user_id, payment_status, created_at),
    CONSTRAINT fk_wait_payment_wait FOREIGN KEY (wait_request_id)
        REFERENCES wait_request(wait_request_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_wait_payment_user FOREIGN KEY (user_id)
        REFERENCES app_user(user_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_wait_payment_order FOREIGN KEY (applied_order_id)
        REFERENCES ticket_order(order_id) ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT chk_wait_payment_amount CHECK (amount >= 0),
    CONSTRAINT chk_wait_payment_status CHECK (
        payment_status IN ('PAID','APPLIED','REFUNDED')
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='候补预付款及自动退款状态';

DROP TRIGGER IF EXISTS trg_wait_request_sync_payment;
DELIMITER $$
CREATE TRIGGER trg_wait_request_sync_payment
AFTER UPDATE ON wait_request
FOR EACH ROW
BEGIN
    IF NEW.wait_status = 'FULFILLED' AND OLD.wait_status <> 'FULFILLED' THEN
        UPDATE wait_payment
           SET payment_status = 'APPLIED', applied_order_id = NEW.matched_order_id,
               refund_reason = NULL, refunded_at = NULL
         WHERE wait_request_id = NEW.wait_request_id AND payment_status = 'PAID';
    ELSEIF NEW.wait_status IN ('EXPIRED','CANCELLED')
       AND OLD.wait_status NOT IN ('EXPIRED','CANCELLED') THEN
        UPDATE wait_payment
           SET payment_status = 'REFUNDED', refunded_at = NOW(6),
               refund_reason = CASE
                   WHEN NEW.wait_status = 'EXPIRED' THEN 'WAITLIST_EXPIRED'
                   ELSE 'WAITLIST_CANCELLED'
               END
         WHERE wait_request_id = NEW.wait_request_id AND payment_status = 'PAID';
    END IF;
END$$
DELIMITER ;

