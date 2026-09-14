-- 长三角 12306 客票综合销售系统
-- V010: 直达查询与 Neo4j 候选的 MySQL 权威复核
-- 文件编码: UTF-8（无 BOM）；导入时指定 --default-character-set=utf8mb4
-- 前置迁移: V002 ... V009

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

DELIMITER $$

CREATE PROCEDURE sp_search_direct_trains(
    IN p_from_station_id INT,
    IN p_to_station_id INT,
    IN p_service_date DATE,
    IN p_departure_after DATETIME(6),
    IN p_departure_before DATETIME(6),
    IN p_passenger_count SMALLINT UNSIGNED,
    IN p_position_code VARCHAR(1),
    IN p_allow_position_fallback BOOLEAN
)
proc: BEGIN
    DECLARE v_position VARCHAR(1);
    DECLARE v_fallback BOOLEAN;

    SET v_position = NULLIF(UPPER(TRIM(p_position_code)), '');
    SET v_fallback = COALESCE(p_allow_position_fallback, TRUE);
    IF p_from_station_id = p_to_station_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_SAME_ORIGIN_DESTINATION';
    END IF;
    IF p_service_date IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_SERVICE_DATE_REQUIRED';
    END IF;
    IF p_passenger_count IS NULL OR p_passenger_count < 1 OR p_passenger_count > 5 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_PASSENGER_COUNT_INVALID';
    END IF;
    IF v_position IS NOT NULL AND v_position NOT IN ('A','B','C','D','F') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_POSITION_CODE_INVALID';
    END IF;

    SELECT
        tr.run_id,
        tr.train_no,
        t.train_type,
        p_from_station_id AS from_station_id,
        origin.station_order AS from_order,
        origin.departure_at,
        p_to_station_id AS to_station_id,
        destination.station_order AS to_order,
        destination.arrival_at,
        TIMESTAMPDIFF(MINUTE, origin.departure_at, destination.arrival_at)
            AS duration_minutes,
        st.seat_type_id,
        st.seat_type_code,
        st.seat_type_name,
        rf.journey_distance_km,
        rf.amount,
        COUNT(*) AS total_seats,
        SUM((trs.occupied_mask & fn_segment_mask(
            origin.station_order, destination.station_order
        )) = 0) AS available_seats,
        SUM(
            s.position_code = v_position
            AND (trs.occupied_mask & fn_segment_mask(
                origin.station_order, destination.station_order
            )) = 0
        ) AS preferred_position_available,
        CASE
            WHEN v_position IS NULL OR v_fallback = TRUE THEN
                SUM((trs.occupied_mask & fn_segment_mask(
                    origin.station_order, destination.station_order
                )) = 0) >= p_passenger_count
            ELSE
                SUM(
                    s.position_code = v_position
                    AND (trs.occupied_mask & fn_segment_mask(
                        origin.station_order, destination.station_order
                    )) = 0
                ) >= p_passenger_count
        END AS can_fulfill
    FROM train_run AS tr
    JOIN train AS t ON t.train_no = tr.train_no
    JOIN v_train_run_stop AS origin
      ON origin.run_id = tr.run_id AND origin.station_id = p_from_station_id
    JOIN v_train_run_stop AS destination
      ON destination.run_id = tr.run_id AND destination.station_id = p_to_station_id
     AND destination.station_order > origin.station_order
    JOIN run_fare AS rf
      ON rf.run_id = tr.run_id
     AND rf.from_order = origin.station_order
     AND rf.to_order = destination.station_order
     AND rf.sale_status = 'OPEN'
    JOIN seat_type AS st ON st.seat_type_id = rf.seat_type_id AND st.active = TRUE
    JOIN train_run_seat AS trs ON trs.run_id = tr.run_id
    JOIN seat AS s
      ON s.seat_id = trs.seat_id
     AND s.seat_type_id = rf.seat_type_id
     AND s.active = TRUE
    JOIN carriage_template AS ct
      ON ct.carriage_id = s.carriage_id
     AND ct.formation_id = tr.formation_id
     AND ct.active = TRUE
    WHERE tr.service_date = p_service_date
      AND tr.run_status = 'ON_SALE'
      AND origin.departure_at IS NOT NULL
      AND destination.arrival_at IS NOT NULL
      AND (p_departure_after IS NULL OR origin.departure_at >= p_departure_after)
      AND (p_departure_before IS NULL OR origin.departure_at < p_departure_before)
    GROUP BY
        tr.run_id, tr.train_no, t.train_type,
        origin.station_order, origin.departure_at,
        destination.station_order, destination.arrival_at,
        st.seat_type_id, st.seat_type_code, st.seat_type_name,
        rf.journey_distance_km, rf.amount
    ORDER BY origin.departure_at, tr.train_no, st.display_order;
END$$

CREATE PROCEDURE sp_validate_transfer_candidates(
    IN p_candidates JSON,
    IN p_from_station_id INT,
    IN p_to_station_id INT,
    IN p_service_date DATE,
    IN p_min_transfer_minutes SMALLINT UNSIGNED,
    IN p_max_transfer_minutes SMALLINT UNSIGNED,
    IN p_passenger_count SMALLINT UNSIGNED,
    IN p_position_code VARCHAR(1),
    IN p_allow_position_fallback BOOLEAN
)
proc: BEGIN
    DECLARE v_position VARCHAR(1);
    DECLARE v_fallback BOOLEAN;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        DROP TEMPORARY TABLE IF EXISTS tmp_query_candidate;
        DROP TEMPORARY TABLE IF EXISTS tmp_query_leg1;
        DROP TEMPORARY TABLE IF EXISTS tmp_query_leg2;
        RESIGNAL;
    END;

    SET v_position = NULLIF(UPPER(TRIM(p_position_code)), '');
    SET v_fallback = COALESCE(p_allow_position_fallback, TRUE);
    IF p_candidates IS NULL OR JSON_TYPE(p_candidates) <> 'ARRAY' THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TRANSFER_CANDIDATES_MUST_BE_ARRAY';
    END IF;
    IF JSON_LENGTH(p_candidates) > 100 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TRANSFER_TOO_MANY_CANDIDATES';
    END IF;
    IF p_from_station_id = p_to_station_id THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_SAME_ORIGIN_DESTINATION';
    END IF;
    IF p_service_date IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_SERVICE_DATE_REQUIRED';
    END IF;
    IF p_min_transfer_minutes IS NULL OR p_max_transfer_minutes IS NULL
       OR p_min_transfer_minutes < 5
       OR p_max_transfer_minutes <= p_min_transfer_minutes
       OR p_max_transfer_minutes > 720 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='TRANSFER_WINDOW_INVALID';
    END IF;
    IF p_passenger_count IS NULL OR p_passenger_count < 1 OR p_passenger_count > 5 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_PASSENGER_COUNT_INVALID';
    END IF;
    IF v_position IS NOT NULL AND v_position NOT IN ('A','B','C','D','F') THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='QUERY_POSITION_CODE_INVALID';
    END IF;

    DROP TEMPORARY TABLE IF EXISTS tmp_query_candidate;
    CREATE TEMPORARY TABLE tmp_query_candidate (
        candidate_id INT UNSIGNED NOT NULL,
        first_run_id BIGINT UNSIGNED NOT NULL,
        second_run_id BIGINT UNSIGNED NOT NULL,
        transfer_station_id INT NOT NULL,
        PRIMARY KEY (candidate_id),
        UNIQUE KEY uk_tmp_transfer (
            first_run_id, second_run_id, transfer_station_id
        )
    ) ENGINE=MEMORY;

    INSERT IGNORE INTO tmp_query_candidate (
        candidate_id, first_run_id, second_run_id, transfer_station_id
    )
    SELECT ordinal, first_run_id, second_run_id, transfer_station_id
      FROM JSON_TABLE(
        p_candidates,
        '$[*]' COLUMNS (
            ordinal FOR ORDINALITY,
            first_run_id BIGINT UNSIGNED PATH '$.firstRunId' ERROR ON ERROR,
            second_run_id BIGINT UNSIGNED PATH '$.secondRunId' ERROR ON ERROR,
            transfer_station_id INT PATH '$.transferStationId' ERROR ON ERROR
        )
    ) AS jt
     WHERE first_run_id <> second_run_id;

    DROP TEMPORARY TABLE IF EXISTS tmp_query_leg1;
    DROP TEMPORARY TABLE IF EXISTS tmp_query_leg2;
    CREATE TEMPORARY TABLE tmp_query_leg1 (
        candidate_id INT UNSIGNED NOT NULL,
        run_id BIGINT UNSIGNED NOT NULL,
        train_no VARCHAR(20) NOT NULL,
        train_type VARCHAR(20) NOT NULL,
        from_order SMALLINT UNSIGNED NOT NULL,
        to_order SMALLINT UNSIGNED NOT NULL,
        departure_at DATETIME(6) NOT NULL,
        arrival_at DATETIME(6) NOT NULL,
        seat_type_id SMALLINT UNSIGNED NOT NULL,
        seat_type_code VARCHAR(20) NOT NULL,
        seat_type_name VARCHAR(40) NOT NULL,
        journey_distance_km DECIMAL(8,1) NOT NULL,
        amount DECIMAL(10,2) NOT NULL,
        available_seats INT UNSIGNED NOT NULL,
        preferred_available INT UNSIGNED NOT NULL,
        PRIMARY KEY (candidate_id, seat_type_id)
    ) ENGINE=InnoDB;
    CREATE TEMPORARY TABLE tmp_query_leg2 LIKE tmp_query_leg1;

    -- 第一程：起点 -> 换乘站。候选 run/order 必须由 MySQL 重新验证。
    INSERT INTO tmp_query_leg1
    SELECT
        c.candidate_id, tr.run_id, tr.train_no, t.train_type,
        origin.station_order, transfer_stop.station_order,
        origin.departure_at, transfer_stop.arrival_at,
        st.seat_type_id, st.seat_type_code, st.seat_type_name,
        rf.journey_distance_km, rf.amount,
        SUM((trs.occupied_mask & fn_segment_mask(
            origin.station_order, transfer_stop.station_order
        )) = 0),
        SUM(s.position_code = v_position AND
            (trs.occupied_mask & fn_segment_mask(
                origin.station_order, transfer_stop.station_order
            )) = 0)
    FROM tmp_query_candidate AS c
    JOIN train_run AS tr
      ON tr.run_id = c.first_run_id
     AND tr.service_date = p_service_date
     AND tr.run_status = 'ON_SALE'
    JOIN train AS t ON t.train_no = tr.train_no
    JOIN v_train_run_stop AS origin
      ON origin.run_id = tr.run_id AND origin.station_id = p_from_station_id
    JOIN v_train_run_stop AS transfer_stop
      ON transfer_stop.run_id = tr.run_id
     AND transfer_stop.station_id = c.transfer_station_id
     AND transfer_stop.station_order > origin.station_order
    JOIN run_fare AS rf
      ON rf.run_id = tr.run_id
     AND rf.from_order = origin.station_order
     AND rf.to_order = transfer_stop.station_order
     AND rf.sale_status = 'OPEN'
    JOIN seat_type AS st ON st.seat_type_id = rf.seat_type_id AND st.active = TRUE
    JOIN train_run_seat AS trs ON trs.run_id = tr.run_id
    JOIN seat AS s
      ON s.seat_id = trs.seat_id AND s.seat_type_id = rf.seat_type_id
     AND s.active = TRUE
    JOIN carriage_template AS ct
      ON ct.carriage_id = s.carriage_id
     AND ct.formation_id = tr.formation_id AND ct.active = TRUE
    GROUP BY c.candidate_id, tr.run_id, tr.train_no, t.train_type,
        origin.station_order, transfer_stop.station_order,
        origin.departure_at, transfer_stop.arrival_at,
        st.seat_type_id, st.seat_type_code, st.seat_type_name,
        rf.journey_distance_km, rf.amount;

    -- 第二程：换乘站 -> 终点。
    INSERT INTO tmp_query_leg2
    SELECT
        c.candidate_id, tr.run_id, tr.train_no, t.train_type,
        transfer_stop.station_order, destination.station_order,
        transfer_stop.departure_at, destination.arrival_at,
        st.seat_type_id, st.seat_type_code, st.seat_type_name,
        rf.journey_distance_km, rf.amount,
        SUM((trs.occupied_mask & fn_segment_mask(
            transfer_stop.station_order, destination.station_order
        )) = 0),
        SUM(s.position_code = v_position AND
            (trs.occupied_mask & fn_segment_mask(
                transfer_stop.station_order, destination.station_order
            )) = 0)
    FROM tmp_query_candidate AS c
    JOIN train_run AS tr
      ON tr.run_id = c.second_run_id
     AND tr.service_date = p_service_date
     AND tr.run_status = 'ON_SALE'
    JOIN train AS t ON t.train_no = tr.train_no
    JOIN v_train_run_stop AS transfer_stop
      ON transfer_stop.run_id = tr.run_id
     AND transfer_stop.station_id = c.transfer_station_id
    JOIN v_train_run_stop AS destination
      ON destination.run_id = tr.run_id AND destination.station_id = p_to_station_id
     AND destination.station_order > transfer_stop.station_order
    JOIN run_fare AS rf
      ON rf.run_id = tr.run_id
     AND rf.from_order = transfer_stop.station_order
     AND rf.to_order = destination.station_order
     AND rf.sale_status = 'OPEN'
    JOIN seat_type AS st ON st.seat_type_id = rf.seat_type_id AND st.active = TRUE
    JOIN train_run_seat AS trs ON trs.run_id = tr.run_id
    JOIN seat AS s
      ON s.seat_id = trs.seat_id AND s.seat_type_id = rf.seat_type_id
     AND s.active = TRUE
    JOIN carriage_template AS ct
      ON ct.carriage_id = s.carriage_id
     AND ct.formation_id = tr.formation_id AND ct.active = TRUE
    GROUP BY c.candidate_id, tr.run_id, tr.train_no, t.train_type,
        transfer_stop.station_order, destination.station_order,
        transfer_stop.departure_at, destination.arrival_at,
        st.seat_type_id, st.seat_type_code, st.seat_type_name,
        rf.journey_distance_km, rf.amount;

    SELECT
        c.candidate_id,
        c.transfer_station_id,
        transfer_station.station_name AS transfer_station_name,
        l1.run_id AS first_run_id,
        l1.train_no AS first_train_no,
        l1.train_type AS first_train_type,
        l1.from_order AS first_from_order,
        l1.to_order AS first_to_order,
        l1.departure_at AS first_departure_at,
        l1.arrival_at AS first_arrival_at,
        l1.seat_type_id AS first_seat_type_id,
        l1.seat_type_name AS first_seat_type_name,
        l1.journey_distance_km AS first_distance_km,
        l1.amount AS first_amount,
        l1.available_seats AS first_available_seats,
        l1.preferred_available AS first_preferred_available,
        l2.run_id AS second_run_id,
        l2.train_no AS second_train_no,
        l2.train_type AS second_train_type,
        l2.from_order AS second_from_order,
        l2.to_order AS second_to_order,
        l2.departure_at AS second_departure_at,
        l2.arrival_at AS second_arrival_at,
        l2.seat_type_id AS second_seat_type_id,
        l2.seat_type_name AS second_seat_type_name,
        l2.journey_distance_km AS second_distance_km,
        l2.amount AS second_amount,
        l2.available_seats AS second_available_seats,
        l2.preferred_available AS second_preferred_available,
        TIMESTAMPDIFF(MINUTE, l1.arrival_at, l2.departure_at)
            AS transfer_minutes,
        l1.amount + l2.amount AS total_amount,
        TIMESTAMPDIFF(MINUTE, l1.departure_at, l2.arrival_at)
            AS total_duration_minutes,
        (
            CASE WHEN v_position IS NULL OR v_fallback = TRUE
                 THEN l1.available_seats ELSE l1.preferred_available END
        ) >= p_passenger_count
        AND (
            CASE WHEN v_position IS NULL OR v_fallback = TRUE
                 THEN l2.available_seats ELSE l2.preferred_available END
        ) >= p_passenger_count AS can_fulfill
    FROM tmp_query_candidate AS c
    JOIN station AS transfer_station
      ON transfer_station.station_id = c.transfer_station_id
    JOIN tmp_query_leg1 AS l1 ON l1.candidate_id = c.candidate_id
    JOIN tmp_query_leg2 AS l2 ON l2.candidate_id = c.candidate_id
    WHERE l2.departure_at >= TIMESTAMPADD(MINUTE, p_min_transfer_minutes, l1.arrival_at)
      AND l2.departure_at <= TIMESTAMPADD(MINUTE, p_max_transfer_minutes, l1.arrival_at)
    ORDER BY can_fulfill DESC, l2.arrival_at, total_amount,
             c.candidate_id, l1.seat_type_id, l2.seat_type_id;

    DROP TEMPORARY TABLE tmp_query_candidate;
    DROP TEMPORARY TABLE tmp_query_leg1;
    DROP TEMPORARY TABLE tmp_query_leg2;
END$$

DELIMITER ;
