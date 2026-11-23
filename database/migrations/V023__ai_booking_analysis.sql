USE CR12306;

CREATE OR REPLACE VIEW v_ops_ai_products AS
SELECT tr.run_id, tr.train_no, tr.service_date, a.station_name AS origin,
       b.station_name AS destination, f.from_order, f.to_order,
       st.seat_type_id, st.seat_type_name
FROM run_fare f
JOIN train_run tr ON tr.run_id = f.run_id
JOIN train_station x ON x.train_no = tr.train_no AND x.station_order = f.from_order
JOIN train_station y ON y.train_no = tr.train_no AND y.station_order = f.to_order
JOIN station a ON a.station_id = x.station_id
JOIN station b ON b.station_id = y.station_id
JOIN seat_type st ON st.seat_type_id = f.seat_type_id
WHERE tr.run_status = 'ON_SALE' AND f.sale_status = 'OPEN' AND st.active = 1
  AND f.to_order <= tr.segment_count + 1;

-- Same active-seat and formation rules as sp_query_availability.
CREATE OR REPLACE VIEW v_ops_ai_seats AS
SELECT rs.run_id, s.seat_type_id, rs.occupied_mask
FROM train_run_seat rs
JOIN train_run tr ON tr.run_id = rs.run_id
JOIN seat s ON s.seat_id = rs.seat_id AND s.active = 1
JOIN carriage_template ct ON ct.carriage_id = s.carriage_id AND ct.active = 1
                         AND ct.formation_id = tr.formation_id;

GRANT SELECT ON CR12306.v_ops_ai_products TO 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_ai_seats TO 'railflow_ops_reports';
