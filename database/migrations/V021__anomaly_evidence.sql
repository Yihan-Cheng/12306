USE CR12306;

CREATE OR REPLACE VIEW v_anomaly_seats AS
SELECT tr.service_date,tr.train_no,rs.run_id,rs.seat_id,c.carriage_no,s.seat_no,
       tr.stop_count,rs.occupied_mask,
       COALESCE(a.expected_mask,0) AS expected_mask,
       COALESCE(a.allocated_segments,0) AS allocated_segments
FROM train_run_seat rs
JOIN train_run tr ON tr.run_id=rs.run_id
JOIN seat s ON s.seat_id=rs.seat_id
JOIN carriage_template c ON c.carriage_id=s.carriage_id
LEFT JOIN (
    SELECT run_id,seat_id,
           BIT_OR(fn_segment_mask(from_order,to_order)) AS expected_mask,
           SUM(to_order-from_order) AS allocated_segments
    FROM seat_allocation WHERE allocation_status IN ('HOLD','CONFIRMED')
    GROUP BY run_id,seat_id
) a ON a.run_id=rs.run_id AND a.seat_id=rs.seat_id;

GRANT SELECT ON CR12306.v_anomaly_seats TO 'railflow_ops_reports';
