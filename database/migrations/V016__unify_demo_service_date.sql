-- CR12306 V016
-- Use one fixed operating day for every train in the classroom demonstration.
SET NAMES utf8mb4;
USE CR12306;

START TRANSACTION;

UPDATE train_run
SET service_date = '2026-10-07',
    run_status = 'ON_SALE',
    sale_start_at = '2026-09-22 00:00:00',
    sale_end_at = '2026-10-09 00:00:00'
WHERE service_date <> '2026-10-07'
   OR run_status <> 'ON_SALE'
   OR sale_start_at <> '2026-09-22 00:00:00'
   OR sale_end_at <> '2026-10-09 00:00:00';

-- Existing wait requests store an absolute cutoff timestamp. Keep it aligned
-- if a developer applies this migration before clearing earlier test data.
UPDATE wait_request
SET cutoff_at = DATE_ADD(cutoff_at, INTERVAL 30 DAY)
WHERE DATE(cutoff_at) BETWEEN '2026-09-07' AND '2026-09-09';

COMMIT;

SELECT service_date, COUNT(*) AS run_count,
       SUM(train_no = 'G8359') AS g8359_count
FROM train_run
GROUP BY service_date;
