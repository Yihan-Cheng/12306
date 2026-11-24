USE CR12306;

CREATE OR REPLACE VIEW v_ops_analysis_orders AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, o.order_status, o.order_id, i.order_item_id,
       a.city AS origin_city, b.city AS destination_city, t.train_type,
       o.order_source, CASE WHEN LEFT(u.username, 3) = 'ai_' THEN 'SIMULATED' ELSE 'OTHER' END AS customer_kind,
       i.price_snapshot
FROM order_item i
JOIN ticket_order o ON o.order_id = i.order_id
JOIN app_user u ON u.user_id = o.user_id
JOIN train_run tr ON tr.run_id = i.run_id
JOIN train t ON t.train_no = tr.train_no
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = i.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = i.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = i.seat_type_id;

CREATE OR REPLACE VIEW v_ops_analysis_waitlist AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, w.wait_status, w.passenger_count,
       a.city AS origin_city, b.city AS destination_city, t.train_type,
       w.retry_count, w.skip_count,
       CASE WHEN w.skip_count >= 3 AND w.wait_status IN ('WAITING', 'MATCHING')
            THEN 'PROTECTED' ELSE 'UNPROTECTED' END AS fairness_status
FROM wait_request w
JOIN train_run tr ON tr.run_id = w.run_id
JOIN train t ON t.train_no = tr.train_no
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = w.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = w.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = w.seat_type_id;

CREATE OR REPLACE VIEW v_ops_analysis_buffer AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, r.request_status,
       TIMESTAMPDIFF(MICROSECOND, r.created_at, r.completed_at) / 1000 AS elapsed_ms,
       a.city AS origin_city, b.city AS destination_city, t.train_type,
       CASE WHEN r.attempt_count = 0 THEN 'UNCLAIMED' WHEN r.attempt_count = 1 THEN 'ONCE' ELSE 'RETRIED' END AS attempt_band,
       CASE WHEN r.request_status <> 'FAILED' THEN 'NONE'
            WHEN INSTR(r.error_code, 'ORDER_INSUFFICIENT_INVENTORY') > 0 THEN 'INVENTORY'
            WHEN INSTR(r.error_code, 'ORDER_INVENTORY_CONCURRENT_CONFLICT') > 0 THEN 'CONFLICT'
            ELSE 'OTHER' END AS failure_category
FROM booking_request_buffer r
JOIN train_run tr ON tr.run_id = r.run_id
JOIN train t ON t.train_no = tr.train_no
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = r.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = r.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = r.seat_type_id;

CREATE OR REPLACE VIEW v_ops_analysis_inventory AS
SELECT tr.service_date, tr.train_no, st.seat_type_name AS seat_type, t.train_type,
       tr.run_status, c.carriage_no, (rs.occupied_mask = 0) AS full_route_free
FROM train_run_seat rs
JOIN train_run tr ON tr.run_id = rs.run_id
JOIN train t ON t.train_no = tr.train_no
JOIN seat s ON s.seat_id = rs.seat_id AND s.active = 1
JOIN seat_type st ON st.seat_type_id = s.seat_type_id AND st.active = 1
JOIN carriage_template c ON c.carriage_id = s.carriage_id AND c.active = 1 AND c.formation_id = tr.formation_id;

GRANT SELECT ON CR12306.v_ops_analysis_inventory TO 'railflow_ops_reports';
