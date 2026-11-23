USE CR12306;

-- Report views expose dimensions and measure inputs without passenger details.
-- Order rows are at ticket-item grain. Order counts must deduplicate order_id.
CREATE OR REPLACE VIEW v_ops_analysis_orders AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, o.order_status, o.order_id, i.order_item_id
FROM order_item i
JOIN ticket_order o ON o.order_id = i.order_id
JOIN train_run tr ON tr.run_id = i.run_id
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = i.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = i.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = i.seat_type_id;

CREATE OR REPLACE VIEW v_ops_analysis_waitlist AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, w.wait_status, w.passenger_count
FROM wait_request w
JOIN train_run tr ON tr.run_id = w.run_id
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = w.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = w.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = w.seat_type_id;

CREATE OR REPLACE VIEW v_ops_analysis_buffer AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       st.seat_type_name AS seat_type, r.request_status,
       TIMESTAMPDIFF(MICROSECOND, r.created_at, r.completed_at) / 1000 AS elapsed_ms
FROM booking_request_buffer r
JOIN train_run tr ON tr.run_id = r.run_id
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = r.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = r.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = r.seat_type_id;

GRANT SELECT ON CR12306.v_ops_analysis_orders TO 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_analysis_waitlist TO 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_analysis_buffer TO 'railflow_ops_reports';
