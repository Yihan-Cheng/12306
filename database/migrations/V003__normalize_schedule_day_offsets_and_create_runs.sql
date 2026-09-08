-- 长三角 12306 客票综合销售系统
-- V003: 跨午夜时刻规范化与单日运行实例初始化
-- 前置迁移: V002__ticketing_domain_schema.sql
-- 目标版本: MySQL 8.4+
--
-- 当前仅供评审，尚未在 CR12306 执行。
-- 本迁移不创建编组、席位或库存容量。

USE CR12306;

SET @v003_service_date = DATE('2026-09-07');

-- ============================================================
-- 1. 构造午夜回绕事件
--
-- SEGMENT: 前站出发后，下一站到达的时钟值变小。
-- DWELL:   同一站到达后，出发的时钟值变小。
-- ============================================================

CREATE TEMPORARY TABLE tmp_v003_rollover_event (
    train_no       VARCHAR(20) NOT NULL,
    rollover_order INT NOT NULL,
    rollover_kind  VARCHAR(10) NOT NULL,
    PRIMARY KEY (train_no, rollover_order, rollover_kind)
) ENGINE=InnoDB;

INSERT INTO tmp_v003_rollover_event (train_no, rollover_order, rollover_kind)
SELECT
    curr.train_no,
    next_stop.station_order,
    'SEGMENT'
FROM train_station AS curr
JOIN train_station AS next_stop
  ON next_stop.train_no = curr.train_no
 AND next_stop.station_order = curr.station_order + 1
WHERE next_stop.arrival_time < curr.departure_time

UNION ALL

SELECT
    train_no,
    station_order,
    'DWELL'
FROM train_station
WHERE arrival_time IS NOT NULL
  AND departure_time IS NOT NULL
  AND departure_time < arrival_time;

-- ============================================================
-- 2. 在写入前执行硬校验
-- ============================================================

DELIMITER $$

CREATE PROCEDURE sp_v003_validate_schedule()
BEGIN
    IF EXISTS (
        SELECT 1
        FROM (
            SELECT
                ts.*,
                MIN(station_order) OVER (PARTITION BY train_no) AS min_order,
                MAX(station_order) OVER (PARTITION BY train_no) AS max_order
            FROM train_station AS ts
        ) AS x
        WHERE (station_order = min_order AND departure_time IS NULL)
           OR (station_order = max_order AND arrival_time IS NULL)
           OR (station_order > min_order AND arrival_time IS NULL)
           OR (station_order < max_order AND departure_time IS NULL)
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V003: train_station contains unexpected missing arrival/departure times';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM train_station AS curr
        JOIN train_station AS next_stop
          ON next_stop.train_no = curr.train_no
         AND next_stop.station_order = curr.station_order + 1
        WHERE MOD(
            TIME_TO_SEC(next_stop.arrival_time)
            - TIME_TO_SEC(curr.departure_time)
            + 86400,
            86400
        ) NOT BETWEEN 60 AND 36000
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V003: adjacent running time is non-positive or exceeds 10 hours';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM train_station
        WHERE arrival_time IS NOT NULL
          AND departure_time IS NOT NULL
          AND MOD(
              TIME_TO_SEC(departure_time)
              - TIME_TO_SEC(arrival_time)
              + 86400,
              86400
          ) > 3600
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V003: station dwell time exceeds 60 minutes';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM tmp_v003_rollover_event
        GROUP BY train_no
        HAVING COUNT(*) > 1
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V003: a regional train slice contains multiple midnight rollovers';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM train_station
        GROUP BY train_no
        HAVING COUNT(*) - 1 > 63
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V003: train has more than 63 segments and cannot use BIGINT mask';
    END IF;
END$$

DELIMITER ;

CALL sp_v003_validate_schedule();
DROP PROCEDURE sp_v003_validate_schedule;

-- ============================================================
-- 3. 回填 day_offset
--
-- 数据检查表明每个区域运行片段最多只有一次午夜回绕，
-- 因而 offset 只会是 0 或 1。时间为空时 offset 同样为空。
-- ============================================================

UPDATE train_station AS ts
LEFT JOIN tmp_v003_rollover_event AS re
  ON re.train_no = ts.train_no
SET
    ts.arrival_day_offset = CASE
        WHEN ts.arrival_time IS NULL THEN NULL
        WHEN re.train_no IS NULL THEN 0
        WHEN re.rollover_kind = 'SEGMENT'
             AND ts.station_order >= re.rollover_order THEN 1
        WHEN re.rollover_kind = 'DWELL'
             AND ts.station_order > re.rollover_order THEN 1
        ELSE 0
    END,
    ts.departure_day_offset = CASE
        WHEN ts.departure_time IS NULL THEN NULL
        WHEN re.train_no IS NULL THEN 0
        WHEN re.rollover_kind = 'SEGMENT'
             AND ts.station_order >= re.rollover_order THEN 1
        WHEN re.rollover_kind = 'DWELL'
             AND ts.station_order >= re.rollover_order THEN 1
        ELSE 0
    END;

-- 时间与 day_offset 必须同时为空或同时非空。
ALTER TABLE train_station
    ADD CONSTRAINT chk_train_station_arrival_offset CHECK (
        (arrival_time IS NULL AND arrival_day_offset IS NULL)
        OR
        (arrival_time IS NOT NULL AND arrival_day_offset IS NOT NULL)
    ),
    ADD CONSTRAINT chk_train_station_departure_offset CHECK (
        (departure_time IS NULL AND departure_day_offset IS NULL)
        OR
        (departure_time IS NOT NULL AND departure_day_offset IS NOT NULL)
    );

-- ============================================================
-- 4. 为模拟服务日生成运行实例
--
-- formation_id 保持 NULL，run_status 保持 PLANNED；
-- 运载量配置完成前不开放销售。
-- ============================================================

INSERT INTO train_run (
    train_no,
    service_date,
    formation_id,
    stop_count,
    segment_count,
    run_status,
    sale_start_at,
    sale_end_at
)
SELECT
    ts.train_no,
    @v003_service_date,
    NULL,
    COUNT(*) AS stop_count,
    COUNT(*) - 1 AS segment_count,
    'PLANNED',
    NULL,
    NULL
FROM train_station AS ts
GROUP BY ts.train_no;

-- ============================================================
-- 5. 迁移后校验输出
-- 预期：1798 个运行实例，104 个区间回绕，4 个站内回绕。
-- ============================================================

SELECT
    COUNT(*) AS created_train_runs,
    MIN(stop_count) AS min_stop_count,
    MAX(stop_count) AS max_stop_count,
    MAX(segment_count) AS max_segment_count
FROM train_run
WHERE service_date = @v003_service_date;

SELECT
    rollover_kind,
    COUNT(*) AS rollover_count
FROM tmp_v003_rollover_event
GROUP BY rollover_kind
ORDER BY rollover_kind;

SELECT
    SUM(arrival_time IS NOT NULL AND arrival_day_offset IS NULL)
        AS arrival_offset_missing,
    SUM(departure_time IS NOT NULL AND departure_day_offset IS NULL)
        AS departure_offset_missing,
    SUM(arrival_time IS NULL AND arrival_day_offset IS NOT NULL)
        AS orphan_arrival_offset,
    SUM(departure_time IS NULL AND departure_day_offset IS NOT NULL)
        AS orphan_departure_offset
FROM train_station;

DROP TEMPORARY TABLE tmp_v003_rollover_event;
