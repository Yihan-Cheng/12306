-- CR12306 V019: move the fixed demo operating day without resetting inventory.
SET NAMES utf8mb4;
USE CR12306;

START TRANSACTION;

-- Shift absolute wait deadlines by each run's date change, once only.
UPDATE wait_request wr
JOIN train_run tr ON tr.run_id = wr.run_id
SET wr.cutoff_at = DATE_ADD(wr.cutoff_at, INTERVAL DATEDIFF('2026-10-14', tr.service_date) DAY)
WHERE tr.service_date <> '2026-10-14';

UPDATE train_run
SET service_date = '2026-10-14',
    run_status = 'ON_SALE',
    sale_start_at = '2026-09-29 00:00:00',
    sale_end_at = '2026-10-16 00:00:00'
WHERE service_date <> '2026-10-14'
   OR run_status <> 'ON_SALE'
   OR sale_start_at <> '2026-09-29 00:00:00'
   OR sale_end_at <> '2026-10-16 00:00:00';

COMMIT;

SELECT service_date, COUNT(*) AS run_count FROM train_run GROUP BY service_date;
