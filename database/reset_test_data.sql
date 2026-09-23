-- 清空用户、乘客、订单、候补和压测数据；保留管理员、车次、站点、票价与席位配置。
SET NAMES utf8mb4;
USE CR12306;

START TRANSACTION;
DELETE FROM admin_session;
DELETE FROM booking_request_buffer;
DELETE FROM refund;
DELETE FROM payment;
DELETE FROM wait_payment;
DELETE FROM wait_request_event;
DELETE FROM wait_passenger;
DELETE FROM wait_request;
DELETE FROM inventory_event;
DELETE FROM seat_allocation;
DELETE FROM order_event;
DELETE FROM order_item;
DELETE FROM ticket_order;
DELETE FROM passenger;
DELETE FROM app_user;
UPDATE train_run_seat SET occupied_mask = 0, version = version + 1 WHERE occupied_mask <> 0;
COMMIT;

ALTER TABLE booking_request_buffer AUTO_INCREMENT = 1;
ALTER TABLE admin_session AUTO_INCREMENT = 1;
ALTER TABLE refund AUTO_INCREMENT = 1;
ALTER TABLE payment AUTO_INCREMENT = 1;
ALTER TABLE wait_payment AUTO_INCREMENT = 1;
ALTER TABLE wait_request_event AUTO_INCREMENT = 1;
ALTER TABLE wait_request AUTO_INCREMENT = 1;
ALTER TABLE inventory_event AUTO_INCREMENT = 1;
ALTER TABLE seat_allocation AUTO_INCREMENT = 1;
ALTER TABLE order_event AUTO_INCREMENT = 1;
ALTER TABLE order_item AUTO_INCREMENT = 1;
ALTER TABLE ticket_order AUTO_INCREMENT = 1;
ALTER TABLE passenger AUTO_INCREMENT = 1;
ALTER TABLE app_user AUTO_INCREMENT = 1;
