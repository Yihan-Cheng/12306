USE CR12306;

-- One request belongs to exactly one ordered station pair. Aggregate before
-- looking up seats so neither passenger nor seat counts multiply on joins.
CREATE OR REPLACE VIEW v_ops_wait_segments AS
SELECT tr.service_date, tr.train_no, a.station_name AS origin, b.station_name AS destination,
       q.waiting_people,
       (SELECT SUM((rs.occupied_mask & fn_segment_mask(q.from_order,q.to_order)) = 0)
          FROM run_fare f JOIN seat_type st ON st.seat_type_id=f.seat_type_id
          JOIN carriage_template c ON c.formation_id=tr.formation_id AND c.active=1
          JOIN seat s ON s.carriage_id=c.carriage_id AND s.seat_type_id=st.seat_type_id AND s.active=1
          JOIN train_run_seat rs ON rs.run_id=f.run_id AND rs.seat_id=s.seat_id
         WHERE f.run_id=q.run_id AND f.from_order=q.from_order AND f.to_order=q.to_order
           AND f.sale_status='OPEN' AND tr.run_status='ON_SALE'
           AND st.active=1 AND st.seat_type_code='SECOND') AS second_seats
FROM (SELECT run_id,from_order,to_order,SUM(passenger_count) AS waiting_people
        FROM wait_request WHERE wait_status IN ('WAITING','MATCHING')
       GROUP BY run_id,from_order,to_order) q
JOIN train_run tr ON tr.run_id=q.run_id
JOIN train_station ts1 ON ts1.train_no=tr.train_no AND ts1.station_order=q.from_order
JOIN station a ON a.station_id=ts1.station_id
JOIN train_station ts2 ON ts2.train_no=tr.train_no AND ts2.station_order=q.to_order
JOIN station b ON b.station_id=ts2.station_id;

CREATE OR REPLACE VIEW v_ops_orders AS
SELECT DISTINCT tr.service_date,tr.train_no,o.order_id,o.order_status
FROM ticket_order o JOIN order_item i ON i.order_id=o.order_id
JOIN train_run tr ON tr.run_id=i.run_id;

CREATE OR REPLACE VIEW v_ops_buffer AS
SELECT tr.service_date,tr.train_no,b.request_status,COUNT(*) AS requests
FROM booking_request_buffer b JOIN train_run tr ON tr.run_id=b.run_id
GROUP BY tr.service_date,tr.train_no,b.request_status;

CREATE ROLE IF NOT EXISTS 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_wait_segments TO 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_orders TO 'railflow_ops_reports';
GRANT SELECT ON CR12306.v_ops_buffer TO 'railflow_ops_reports';
