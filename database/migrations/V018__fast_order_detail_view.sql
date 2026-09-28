-- Anchor order details on orders and their indexed items. Expanding the
-- timetable view twice first makes even one user's order list very slow.
SET NAMES utf8mb4;
USE CR12306;

CREATE OR REPLACE ALGORITHM=MERGE VIEW v_order_detail AS
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
    TIMESTAMP(tr.service_date, origin.departure_time)
        + INTERVAL origin.departure_day_offset DAY AS departure_at,
    destination.station_id AS to_station_id,
    destination_station.station_name AS to_station_name,
    TIMESTAMP(tr.service_date, destination.arrival_time)
        + INTERVAL destination.arrival_day_offset DAY AS arrival_at,
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
STRAIGHT_JOIN order_item AS oi ON oi.order_id = o.order_id
STRAIGHT_JOIN passenger AS p ON p.passenger_id = oi.passenger_id
STRAIGHT_JOIN train_run AS tr ON tr.run_id = oi.run_id
STRAIGHT_JOIN train_station AS origin
  ON origin.train_no = tr.train_no AND origin.station_order = oi.from_order
STRAIGHT_JOIN station AS origin_station
  ON origin_station.station_id = origin.station_id
STRAIGHT_JOIN train_station AS destination
  ON destination.train_no = tr.train_no AND destination.station_order = oi.to_order
STRAIGHT_JOIN station AS destination_station
  ON destination_station.station_id = destination.station_id
STRAIGHT_JOIN seat_type AS st ON st.seat_type_id = oi.seat_type_id
LEFT JOIN seat_allocation AS sa ON sa.order_item_id = oi.order_item_id
LEFT JOIN seat AS s ON s.seat_id = sa.seat_id
LEFT JOIN carriage_template AS ct ON ct.carriage_id = s.carriage_id;
