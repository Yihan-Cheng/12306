-- 长三角 12306 客票综合销售系统
-- V008: 相邻区间估算里程、数据驱动票价规则、全 OD 票价与模拟开售
-- 文件编码: UTF-8（无 BOM）；导入时必须指定 --default-character-set=utf8mb4
-- 前置迁移: V002 ... V007
-- 目标版本: MySQL 8.4+

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

CREATE TABLE station_pair_distance (
    station_a_id       INT NOT NULL,
    station_b_id       INT NOT NULL,
    distance_km        DECIMAL(8, 1) NOT NULL,
    estimate_method    VARCHAR(40) NOT NULL,
    observation_count INT UNSIGNED NOT NULL,
    confidence_level   VARCHAR(12) NOT NULL,
    source_note        VARCHAR(300) NOT NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (station_a_id, station_b_id),
    CONSTRAINT fk_pair_distance_station_a
        FOREIGN KEY (station_a_id) REFERENCES station (station_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT fk_pair_distance_station_b
        FOREIGN KEY (station_b_id) REFERENCES station (station_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_pair_distance_order CHECK (station_a_id < station_b_id),
    CONSTRAINT chk_pair_distance_value CHECK (distance_km BETWEEN 1 AND 500),
    CONSTRAINT chk_pair_distance_confidence
        CHECK (confidence_level IN ('LOW', 'MEDIUM', 'HIGH'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='相邻站无向估算里程；课程数据，不冒充官方营业里程';

CREATE TABLE fare_rule (
    fare_rule_id       BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    train_category     VARCHAR(20) NOT NULL,
    seat_type_id       SMALLINT UNSIGNED NOT NULL,
    base_fare          DECIMAL(8, 2) NOT NULL DEFAULT 0,
    per_km_rate        DECIMAL(8, 4) NOT NULL,
    minimum_fare       DECIMAL(8, 2) NOT NULL,
    rounding_unit      DECIMAL(4, 2) NOT NULL DEFAULT 0.50,
    active             BOOLEAN NOT NULL DEFAULT TRUE,
    description        VARCHAR(300) NULL,
    created_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at         TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                                      ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (fare_rule_id),
    UNIQUE KEY uk_fare_rule_product (train_category, seat_type_id),
    CONSTRAINT fk_fare_rule_seat_type
        FOREIGN KEY (seat_type_id) REFERENCES seat_type (seat_type_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT chk_fare_rule_category
        CHECK (train_category IN ('GC_EMU', 'D_EMU', 'CONVENTIONAL')),
    CONSTRAINT chk_fare_rule_amounts CHECK (
        base_fare >= 0 AND per_km_rate > 0
        AND minimum_fare >= 0 AND rounding_unit > 0
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='车型类别与席别共同决定的课程票价参数';

ALTER TABLE run_fare
    ADD COLUMN journey_distance_km DECIMAL(8, 1) NULL
        COMMENT '该 OD 累计估算里程' AFTER seat_type_id,
    ADD COLUMN fare_rule_id BIGINT UNSIGNED NULL
        COMMENT '生成票价所用规则' AFTER journey_distance_km,
    ADD KEY idx_run_fare_rule (fare_rule_id),
    ADD CONSTRAINT fk_run_fare_rule
        FOREIGN KEY (fare_rule_id) REFERENCES fare_rule (fare_rule_id)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    ADD CONSTRAINT chk_run_fare_distance
        CHECK (journey_distance_km IS NULL OR journey_distance_km > 0);

DELIMITER $$

CREATE PROCEDURE sp_v008_generate_fares()
main: BEGIN
    DECLARE v_existing_rows BIGINT UNSIGNED;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        DROP TEMPORARY TABLE IF EXISTS tmp_v008_segment;
        DROP TEMPORARY TABLE IF EXISTS tmp_v008_od;
        RESIGNAL;
    END;

    SELECT
        (SELECT COUNT(*) FROM station_pair_distance)
        + (SELECT COUNT(*) FROM fare_rule)
        + (SELECT COUNT(*) FROM run_fare)
      INTO v_existing_rows;
    IF v_existing_rows <> 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V008_REQUIRES_EMPTY_DISTANCE_AND_FARE_TABLES';
    END IF;

    START TRANSACTION;

    -- 相邻站运行时长乘以车型参考速度；同一物理站对取所有观测中的最短估算，
    -- 减少临时限速和时刻冗余的影响。结果限制在 5～350 km。
    INSERT INTO station_pair_distance (
        station_a_id, station_b_id, distance_km,
        estimate_method, observation_count, confidence_level, source_note
    )
    SELECT
        LEAST(origin.station_id, destination.station_id),
        GREATEST(origin.station_id, destination.station_id),
        LEAST(350.0, GREATEST(5.0, ROUND(MIN(
            TIMESTAMPDIFF(SECOND, origin.departure_at, destination.arrival_at)
            / 3600.0
            * CASE
                WHEN t.train_type IN ('高速动车', '城际动车') THEN 220.0
                WHEN t.train_type = '动车组' THEN 180.0
                ELSE 100.0
              END
        ), 1))) AS distance_km,
        'TIMETABLE_MIN_RUNTIME',
        COUNT(*) AS observation_count,
        CASE WHEN COUNT(*) >= 5 THEN 'HIGH'
             WHEN COUNT(*) >= 2 THEN 'MEDIUM'
             ELSE 'LOW' END,
        '按相邻站最短运行时间与车型参考速度估算；非中国铁路官方营业里程'
    FROM v_train_run_stop AS origin
    JOIN v_train_run_stop AS destination
      ON destination.run_id = origin.run_id
     AND destination.station_order = origin.station_order + 1
    JOIN train_run AS tr ON tr.run_id = origin.run_id
    JOIN train AS t ON t.train_no = tr.train_no
    WHERE origin.departure_at IS NOT NULL
      AND destination.arrival_at IS NOT NULL
      AND destination.arrival_at > origin.departure_at
    GROUP BY
        LEAST(origin.station_id, destination.station_id),
        GREATEST(origin.station_id, destination.station_id);

    INSERT INTO fare_rule (
        train_category, seat_type_id, base_fare, per_km_rate,
        minimum_fare, rounding_unit, description
    )
    SELECT 'GC_EMU', seat_type_id, 0, rate, minimum_fare, 0.50, description
      FROM (
        SELECT 'BUSINESS' code, 1.4400 rate, 15.00 minimum_fare,
               'G/C 商务座，约为二等座每公里费率的 3 倍' description
        UNION ALL SELECT 'FIRST', 0.7700, 10.00,
               'G/C 一等座，约为二等座每公里费率的 1.6 倍'
        UNION ALL SELECT 'SECOND', 0.4800, 8.00,
               'G/C 二等座课程基准费率'
      ) AS x
      JOIN seat_type AS st ON st.seat_type_code = x.code;

    INSERT INTO fare_rule (
        train_category, seat_type_id, base_fare, per_km_rate,
        minimum_fare, rounding_unit, description
    )
    SELECT 'D_EMU', seat_type_id, 0, rate, minimum_fare, 0.50, description
      FROM (
        SELECT 'FIRST' code, 0.6400 rate, 9.00 minimum_fare,
               'D 一等座，约为二等座每公里费率的 1.6 倍' description
        UNION ALL SELECT 'SECOND', 0.4000, 7.00,
               'D 二等座课程基准费率'
      ) AS x
      JOIN seat_type AS st ON st.seat_type_code = x.code;

    INSERT INTO fare_rule (
        train_category, seat_type_id, base_fare, per_km_rate,
        minimum_fare, rounding_unit, description
    )
    SELECT 'CONVENTIONAL', seat_type_id, 0, 0.1800, 5.00, 0.50,
           '普速硬座课程基准费率'
      FROM seat_type WHERE seat_type_code = 'HARD_SEAT';

    DROP TEMPORARY TABLE IF EXISTS tmp_v008_segment;
    CREATE TEMPORARY TABLE tmp_v008_segment (
        run_id BIGINT UNSIGNED NOT NULL,
        from_order SMALLINT UNSIGNED NOT NULL,
        distance_km DECIMAL(8, 1) NOT NULL,
        PRIMARY KEY (run_id, from_order)
    ) ENGINE=InnoDB;

    INSERT INTO tmp_v008_segment (run_id, from_order, distance_km)
    SELECT
        origin.run_id,
        origin.station_order,
        spd.distance_km
    FROM v_train_run_stop AS origin
    JOIN v_train_run_stop AS destination
      ON destination.run_id = origin.run_id
     AND destination.station_order = origin.station_order + 1
    JOIN station_pair_distance AS spd
      ON spd.station_a_id = LEAST(origin.station_id, destination.station_id)
     AND spd.station_b_id = GREATEST(origin.station_id, destination.station_id);

    DROP TEMPORARY TABLE IF EXISTS tmp_v008_od;
    CREATE TEMPORARY TABLE tmp_v008_od (
        run_id BIGINT UNSIGNED NOT NULL,
        from_order SMALLINT UNSIGNED NOT NULL,
        to_order SMALLINT UNSIGNED NOT NULL,
        journey_distance_km DECIMAL(8, 1) NOT NULL,
        PRIMARY KEY (run_id, from_order, to_order)
    ) ENGINE=InnoDB;

    INSERT INTO tmp_v008_od (
        run_id, from_order, to_order, journey_distance_km
    )
    SELECT
        tr.run_id,
        origin.station_order,
        destination.station_order,
        SUM(segment.distance_km)
    FROM train_run AS tr
    JOIN v_train_run_stop AS origin ON origin.run_id = tr.run_id
    JOIN v_train_run_stop AS destination
      ON destination.run_id = tr.run_id
     AND destination.station_order > origin.station_order
    JOIN tmp_v008_segment AS segment
      ON segment.run_id = tr.run_id
     AND segment.from_order >= origin.station_order
     AND segment.from_order < destination.station_order
    GROUP BY tr.run_id, origin.station_order, destination.station_order;

    INSERT INTO run_fare (
        run_id, from_order, to_order, seat_type_id,
        journey_distance_km, fare_rule_id,
        amount, currency, sale_status
    )
    SELECT
        od.run_id,
        od.from_order,
        od.to_order,
        fr.seat_type_id,
        od.journey_distance_km,
        fr.fare_rule_id,
        GREATEST(
            fr.minimum_fare,
            ROUND(
                (fr.base_fare + od.journey_distance_km * fr.per_km_rate)
                / fr.rounding_unit,
                0
            ) * fr.rounding_unit
        ),
        'CNY',
        'OPEN'
    FROM tmp_v008_od AS od
    JOIN train_run AS tr ON tr.run_id = od.run_id
    JOIN train AS t ON t.train_no = tr.train_no
    JOIN fare_rule AS fr
      ON fr.train_category = CASE
            WHEN t.train_type IN ('高速动车', '城际动车') THEN 'GC_EMU'
            WHEN t.train_type = '动车组' THEN 'D_EMU'
            ELSE 'CONVENTIONAL'
         END
     AND fr.active = TRUE
    JOIN (
        SELECT DISTINCT ct.formation_id, s.seat_type_id
          FROM carriage_template AS ct
          JOIN seat AS s ON s.carriage_id = ct.carriage_id AND s.active = TRUE
         WHERE ct.active = TRUE
    ) AS available_type
      ON available_type.formation_id = tr.formation_id
     AND available_type.seat_type_id = fr.seat_type_id;

    -- 单日课程系统使用固定模拟运营日；开售状态不依赖现实机器日期。
    UPDATE train_run
       SET run_status = 'ON_SALE',
           sale_start_at = TIMESTAMPADD(DAY, -15, TIMESTAMP(service_date, '00:00:00')),
           sale_end_at = TIMESTAMPADD(DAY, 2, TIMESTAMP(service_date, '00:00:00')),
           version = version + 1
     WHERE run_status = 'PLANNED';

    DROP TEMPORARY TABLE tmp_v008_segment;
    DROP TEMPORARY TABLE tmp_v008_od;
    COMMIT;
END$$

DELIMITER ;

CALL sp_v008_generate_fares();
DROP PROCEDURE sp_v008_generate_fares;

