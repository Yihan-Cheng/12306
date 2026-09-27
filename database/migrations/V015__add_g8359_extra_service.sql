-- CR12306 V015
-- Add G8359 as an ordinary, fully bookable service on the fixed demo day.
-- Upserts make the migration safe to resume without deleting orders or inventory.

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

DROP PROCEDURE IF EXISTS sp_v015_add_g8359;
DELIMITER $$
CREATE PROCEDURE sp_v015_add_g8359()
BEGIN
    DECLARE v_next_station INT DEFAULT 0;
    DECLARE v_yancheng INT; DECLARE v_yanchengdafeng INT;
    DECLARE v_haian INT; DECLARE v_rugaonan INT; DECLARE v_nantongxi INT;
    DECLARE v_zhangjiagang INT; DECLARE v_changshu INT; DECLARE v_taicang INT;
    DECLARE v_shanghaihongqiao INT; DECLARE v_liantang INT; DECLARE v_suzhounan INT;
    DECLARE v_huzhoudong INT; DECLARE v_hangzhouxi INT; DECLARE v_yiwu INT;
    DECLARE v_formation_id BIGINT UNSIGNED; DECLARE v_run_id BIGINT UNSIGNED;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    START TRANSACTION;
    SELECT COALESCE(MAX(station_id),1000) INTO v_next_station FROM station;

    SELECT station_id INTO v_yancheng FROM station WHERE station_name='盐城' LIMIT 1;
    IF v_yancheng IS NULL THEN SET v_next_station=v_next_station+1; SET v_yancheng=v_next_station;
      INSERT INTO station VALUES(v_yancheng,NULL,'盐城','盐城'); ELSE UPDATE station SET city='盐城' WHERE station_id=v_yancheng; END IF;
    SELECT station_id INTO v_yanchengdafeng FROM station WHERE station_name='盐城大丰' LIMIT 1;
    IF v_yanchengdafeng IS NULL THEN SET v_next_station=v_next_station+1; SET v_yanchengdafeng=v_next_station;
      INSERT INTO station VALUES(v_yanchengdafeng,NULL,'盐城大丰','盐城'); ELSE UPDATE station SET city='盐城' WHERE station_id=v_yanchengdafeng; END IF;
    SELECT station_id INTO v_haian FROM station WHERE station_name='海安' LIMIT 1;
    IF v_haian IS NULL THEN SET v_next_station=v_next_station+1; SET v_haian=v_next_station;
      INSERT INTO station VALUES(v_haian,NULL,'海安','南通'); ELSE UPDATE station SET city='南通' WHERE station_id=v_haian; END IF;
    SELECT station_id INTO v_rugaonan FROM station WHERE station_name='如皋南' LIMIT 1;
    IF v_rugaonan IS NULL THEN SET v_next_station=v_next_station+1; SET v_rugaonan=v_next_station;
      INSERT INTO station VALUES(v_rugaonan,NULL,'如皋南','南通'); ELSE UPDATE station SET city='南通' WHERE station_id=v_rugaonan; END IF;
    SELECT station_id INTO v_nantongxi FROM station WHERE station_name='南通西' LIMIT 1;
    IF v_nantongxi IS NULL THEN SET v_next_station=v_next_station+1; SET v_nantongxi=v_next_station;
      INSERT INTO station VALUES(v_nantongxi,NULL,'南通西','南通'); ELSE UPDATE station SET city='南通' WHERE station_id=v_nantongxi; END IF;
    SELECT station_id INTO v_zhangjiagang FROM station WHERE station_name='张家港' LIMIT 1;
    IF v_zhangjiagang IS NULL THEN SET v_next_station=v_next_station+1; SET v_zhangjiagang=v_next_station;
      INSERT INTO station VALUES(v_zhangjiagang,NULL,'张家港','苏州'); ELSE UPDATE station SET city='苏州' WHERE station_id=v_zhangjiagang; END IF;
    SELECT station_id INTO v_changshu FROM station WHERE station_name='常熟' LIMIT 1;
    IF v_changshu IS NULL THEN SET v_next_station=v_next_station+1; SET v_changshu=v_next_station;
      INSERT INTO station VALUES(v_changshu,NULL,'常熟','苏州'); ELSE UPDATE station SET city='苏州' WHERE station_id=v_changshu; END IF;
    SELECT station_id INTO v_taicang FROM station WHERE station_name='太仓' LIMIT 1;
    IF v_taicang IS NULL THEN SET v_next_station=v_next_station+1; SET v_taicang=v_next_station;
      INSERT INTO station VALUES(v_taicang,NULL,'太仓','苏州'); ELSE UPDATE station SET city='苏州' WHERE station_id=v_taicang; END IF;
    SELECT station_id INTO v_shanghaihongqiao FROM station WHERE station_name='上海虹桥' LIMIT 1;
    IF v_shanghaihongqiao IS NULL THEN SET v_next_station=v_next_station+1; SET v_shanghaihongqiao=v_next_station;
      INSERT INTO station VALUES(v_shanghaihongqiao,NULL,'上海虹桥','上海'); ELSE UPDATE station SET city='上海' WHERE station_id=v_shanghaihongqiao; END IF;
    SELECT station_id INTO v_liantang FROM station WHERE station_name='练塘' LIMIT 1;
    IF v_liantang IS NULL THEN SET v_next_station=v_next_station+1; SET v_liantang=v_next_station;
      INSERT INTO station VALUES(v_liantang,NULL,'练塘','上海'); ELSE UPDATE station SET city='上海' WHERE station_id=v_liantang; END IF;
    SELECT station_id INTO v_suzhounan FROM station WHERE station_name='苏州南' LIMIT 1;
    IF v_suzhounan IS NULL THEN SET v_next_station=v_next_station+1; SET v_suzhounan=v_next_station;
      INSERT INTO station VALUES(v_suzhounan,NULL,'苏州南','苏州'); ELSE UPDATE station SET city='苏州' WHERE station_id=v_suzhounan; END IF;
    SELECT station_id INTO v_huzhoudong FROM station WHERE station_name='湖州东' LIMIT 1;
    IF v_huzhoudong IS NULL THEN SET v_next_station=v_next_station+1; SET v_huzhoudong=v_next_station;
      INSERT INTO station VALUES(v_huzhoudong,NULL,'湖州东','湖州'); ELSE UPDATE station SET city='湖州' WHERE station_id=v_huzhoudong; END IF;
    SELECT station_id INTO v_hangzhouxi FROM station WHERE station_name='杭州西' LIMIT 1;
    IF v_hangzhouxi IS NULL THEN SET v_next_station=v_next_station+1; SET v_hangzhouxi=v_next_station;
      INSERT INTO station VALUES(v_hangzhouxi,NULL,'杭州西','杭州'); ELSE UPDATE station SET city='杭州' WHERE station_id=v_hangzhouxi; END IF;
    SELECT station_id INTO v_yiwu FROM station WHERE station_name='义乌' LIMIT 1;
    IF v_yiwu IS NULL THEN SET v_next_station=v_next_station+1; SET v_yiwu=v_next_station;
      INSERT INTO station VALUES(v_yiwu,NULL,'义乌','金华'); ELSE UPDATE station SET city='金华' WHERE station_id=v_yiwu; END IF;

    INSERT INTO train(train_no,train_type) VALUES('G8359','高速动车')
    ON DUPLICATE KEY UPDATE train_type=VALUES(train_type);

    INSERT INTO train_station(train_no,station_order,station_id,arrival_time,arrival_day_offset,departure_time,departure_day_offset) VALUES
      ('G8359',1,v_yancheng,NULL,NULL,'12:03:00',0),
      ('G8359',2,v_yanchengdafeng,'12:13:00',0,'12:15:00',0),
      ('G8359',3,v_haian,'12:36:00',0,'12:38:00',0),
      ('G8359',4,v_rugaonan,'12:48:00',0,'12:50:00',0),
      ('G8359',5,v_nantongxi,'13:03:00',0,'13:05:00',0),
      ('G8359',6,v_zhangjiagang,'13:21:00',0,'13:23:00',0),
      ('G8359',7,v_changshu,'13:32:00',0,'13:34:00',0),
      ('G8359',8,v_taicang,'13:53:00',0,'13:55:00',0),
      ('G8359',9,v_shanghaihongqiao,'14:30:00',0,'14:35:00',0),
      ('G8359',10,v_liantang,'14:54:00',0,'14:56:00',0),
      ('G8359',11,v_suzhounan,'15:06:00',0,'15:08:00',0),
      ('G8359',12,v_huzhoudong,'15:28:00',0,'15:30:00',0),
      ('G8359',13,v_hangzhouxi,'15:58:00',0,'16:01:00',0),
      ('G8359',14,v_yiwu,'16:38:00',0,NULL,NULL)
    ON DUPLICATE KEY UPDATE station_id=VALUES(station_id),arrival_time=VALUES(arrival_time),
      arrival_day_offset=VALUES(arrival_day_offset),departure_time=VALUES(departure_time),
      departure_day_offset=VALUES(departure_day_offset);

    INSERT INTO train_segment(train_no,from_station_id,to_station_id,from_order,to_order,departure_time,arrival_time) VALUES
      ('G8359',v_yancheng,v_yanchengdafeng,1,2,'12:03:00','12:13:00'),
      ('G8359',v_yanchengdafeng,v_haian,2,3,'12:15:00','12:36:00'),
      ('G8359',v_haian,v_rugaonan,3,4,'12:38:00','12:48:00'),
      ('G8359',v_rugaonan,v_nantongxi,4,5,'12:50:00','13:03:00'),
      ('G8359',v_nantongxi,v_zhangjiagang,5,6,'13:05:00','13:21:00'),
      ('G8359',v_zhangjiagang,v_changshu,6,7,'13:23:00','13:32:00'),
      ('G8359',v_changshu,v_taicang,7,8,'13:34:00','13:53:00'),
      ('G8359',v_taicang,v_shanghaihongqiao,8,9,'13:55:00','14:30:00'),
      ('G8359',v_shanghaihongqiao,v_liantang,9,10,'14:35:00','14:54:00'),
      ('G8359',v_liantang,v_suzhounan,10,11,'14:56:00','15:06:00'),
      ('G8359',v_suzhounan,v_huzhoudong,11,12,'15:08:00','15:28:00'),
      ('G8359',v_huzhoudong,v_hangzhouxi,12,13,'15:30:00','15:58:00'),
      ('G8359',v_hangzhouxi,v_yiwu,13,14,'16:01:00','16:38:00')
    ON DUPLICATE KEY UPDATE from_station_id=VALUES(from_station_id),to_station_id=VALUES(to_station_id),
      departure_time=VALUES(departure_time),arrival_time=VALUES(arrival_time);

    SELECT formation_id INTO v_formation_id FROM formation_template WHERE formation_code='EMU_GC_4' AND active=TRUE LIMIT 1;
    IF v_formation_id IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='V015_GC_FORMATION_MISSING'; END IF;
    INSERT INTO train_run(train_no,service_date,formation_id,stop_count,segment_count,run_status,sale_start_at,sale_end_at)
    VALUES('G8359','2026-10-07',v_formation_id,14,13,'ON_SALE','2026-09-22 00:00:00','2026-10-09 00:00:00')
    ON DUPLICATE KEY UPDATE formation_id=VALUES(formation_id),stop_count=14,segment_count=13,run_status='ON_SALE',sale_start_at=VALUES(sale_start_at),sale_end_at=VALUES(sale_end_at),version=version+1;
    SELECT run_id INTO v_run_id FROM train_run WHERE train_no='G8359' AND service_date='2026-10-07';
    INSERT IGNORE INTO train_run_seat(run_id,seat_id,occupied_mask,version)
      SELECT v_run_id,s.seat_id,0,0 FROM carriage_template ct JOIN seat s ON s.carriage_id=ct.carriage_id AND s.active=TRUE
      WHERE ct.formation_id=v_formation_id AND ct.active=TRUE;

    INSERT INTO station_pair_distance(station_a_id,station_b_id,distance_km,estimate_method,observation_count,confidence_level,source_note) VALUES
      (LEAST(v_yancheng,v_yanchengdafeng),GREATEST(v_yancheng,v_yanchengdafeng),36.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_yanchengdafeng,v_haian),GREATEST(v_yanchengdafeng,v_haian),77.0,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_haian,v_rugaonan),GREATEST(v_haian,v_rugaonan),36.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_rugaonan,v_nantongxi),GREATEST(v_rugaonan,v_nantongxi),47.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_nantongxi,v_zhangjiagang),GREATEST(v_nantongxi,v_zhangjiagang),58.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_zhangjiagang,v_changshu),GREATEST(v_zhangjiagang,v_changshu),33.0,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_changshu,v_taicang),GREATEST(v_changshu,v_taicang),69.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_taicang,v_shanghaihongqiao),GREATEST(v_taicang,v_shanghaihongqiao),128.3,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_shanghaihongqiao,v_liantang),GREATEST(v_shanghaihongqiao,v_liantang),69.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_liantang,v_suzhounan),GREATEST(v_liantang,v_suzhounan),36.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_suzhounan,v_huzhoudong),GREATEST(v_suzhounan,v_huzhoudong),73.3,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_huzhoudong,v_hangzhouxi),GREATEST(v_huzhoudong,v_hangzhouxi),102.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算'),
      (LEAST(v_hangzhouxi,v_yiwu),GREATEST(v_hangzhouxi,v_yiwu),135.7,'TIMETABLE_RUNTIME',1,'LOW','G8359时刻估算')
    ON DUPLICATE KEY UPDATE distance_km=VALUES(distance_km),estimate_method=VALUES(estimate_method),observation_count=VALUES(observation_count),confidence_level=VALUES(confidence_level),source_note=VALUES(source_note);

    INSERT INTO run_fare(run_id,from_order,to_order,seat_type_id,journey_distance_km,fare_rule_id,amount,currency,sale_status)
    SELECT v_run_id,o.station_order,d.station_order,fr.seat_type_id,SUM(seg.distance_km),fr.fare_rule_id,
      GREATEST(fr.minimum_fare,ROUND((fr.base_fare+SUM(seg.distance_km)*fr.per_km_rate)/fr.rounding_unit,0)*fr.rounding_unit),'CNY','OPEN'
    FROM train_station o JOIN train_station d ON d.train_no=o.train_no AND d.station_order>o.station_order
    JOIN (SELECT 1 from_order,36.7 distance_km UNION ALL SELECT 2,77.0 UNION ALL SELECT 3,36.7 UNION ALL SELECT 4,47.7 UNION ALL SELECT 5,58.7 UNION ALL SELECT 6,33.0 UNION ALL SELECT 7,69.7 UNION ALL SELECT 8,128.3 UNION ALL SELECT 9,69.7 UNION ALL SELECT 10,36.7 UNION ALL SELECT 11,73.3 UNION ALL SELECT 12,102.7 UNION ALL SELECT 13,135.7) seg
      ON seg.from_order>=o.station_order AND seg.from_order<d.station_order
    JOIN fare_rule fr ON fr.train_category='GC_EMU' AND fr.active=TRUE
    JOIN (SELECT DISTINCT s.seat_type_id FROM carriage_template ct JOIN seat s ON s.carriage_id=ct.carriage_id AND s.active=TRUE WHERE ct.formation_id=v_formation_id AND ct.active=TRUE) available ON available.seat_type_id=fr.seat_type_id
    WHERE o.train_no='G8359'
    GROUP BY o.station_order,d.station_order,fr.seat_type_id,fr.fare_rule_id,fr.minimum_fare,fr.base_fare,fr.per_km_rate,fr.rounding_unit
    ON DUPLICATE KEY UPDATE journey_distance_km=VALUES(journey_distance_km),fare_rule_id=VALUES(fare_rule_id),
      amount=VALUES(amount),currency='CNY',sale_status='OPEN';
    COMMIT;
END$$
DELIMITER ;

CALL sp_v015_add_g8359();
DROP PROCEDURE sp_v015_add_g8359;

SELECT tr.run_id,tr.train_no,tr.service_date,tr.stop_count,tr.segment_count,tr.run_status,
       COUNT(DISTINCT trs.seat_id) seats,COUNT(DISTINCT rf.run_fare_id) fares
FROM train_run tr LEFT JOIN train_run_seat trs ON trs.run_id=tr.run_id LEFT JOIN run_fare rf ON rf.run_id=tr.run_id
WHERE tr.train_no='G8359' AND tr.service_date='2026-10-07'
GROUP BY tr.run_id,tr.train_no,tr.service_date,tr.stop_count,tr.segment_count,tr.run_status;
