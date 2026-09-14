-- 长三角 12306 客票综合销售系统
-- V007: 课程规模编组、席别、具体座位与运行席位
-- 文件编码: UTF-8（无 BOM）；导入时必须指定 --default-character-set=utf8mb4
-- 前置迁移: V002 ... V006
-- 目标版本: MySQL 8.4+

SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE CR12306;

DELIMITER $$

CREATE PROCEDURE sp_v007_add_carriage(
    IN p_formation_id BIGINT UNSIGNED,
    IN p_carriage_no SMALLINT UNSIGNED,
    IN p_carriage_code VARCHAR(20),
    IN p_carriage_name VARCHAR(80),
    IN p_seat_type_code VARCHAR(20),
    IN p_row_count SMALLINT UNSIGNED,
    IN p_layout VARCHAR(5)
)
BEGIN
    DECLARE v_carriage_id BIGINT UNSIGNED;
    DECLARE v_seat_type_id SMALLINT UNSIGNED;
    DECLARE v_row SMALLINT UNSIGNED DEFAULT 1;
    DECLARE v_position_index SMALLINT UNSIGNED;
    DECLARE v_position VARCHAR(1);

    SELECT seat_type_id INTO v_seat_type_id
      FROM seat_type WHERE seat_type_code = p_seat_type_code;

    INSERT INTO carriage_template (
        formation_id, carriage_no, carriage_code, carriage_name
    ) VALUES (
        p_formation_id, p_carriage_no, p_carriage_code, p_carriage_name
    );
    SET v_carriage_id = LAST_INSERT_ID();

    WHILE v_row <= p_row_count DO
        SET v_position_index = 1;
        WHILE v_position_index <= CHAR_LENGTH(p_layout) DO
            SET v_position = SUBSTRING(p_layout, v_position_index, 1);
            INSERT INTO seat (
                carriage_id, seat_type_id, seat_no, row_no, position_code
            ) VALUES (
                v_carriage_id,
                v_seat_type_id,
                CONCAT(LPAD(v_row, 2, '0'), v_position),
                v_row,
                v_position
            );
            SET v_position_index = v_position_index + 1;
        END WHILE;
        SET v_row = v_row + 1;
    END WHILE;
END$$

CREATE PROCEDURE sp_v007_apply_capacity()
main: BEGIN
    DECLARE v_existing_capacity BIGINT UNSIGNED;
    DECLARE v_gc_formation BIGINT UNSIGNED;
    DECLARE v_d_formation BIGINT UNSIGNED;
    DECLARE v_conventional_formation BIGINT UNSIGNED;

    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    SELECT
        (SELECT COUNT(*) FROM formation_template)
        + (SELECT COUNT(*) FROM carriage_template)
        + (SELECT COUNT(*) FROM seat)
        + (SELECT COUNT(*) FROM train_run_seat)
      INTO v_existing_capacity;

    IF v_existing_capacity <> 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V007_REQUIRES_EMPTY_CAPACITY_TABLES';
    END IF;

    START TRANSACTION;

    INSERT INTO seat_type (
        seat_type_code, seat_type_name, active, display_order
    ) VALUES
        ('BUSINESS', '商务座', TRUE, 10),
        ('FIRST',    '一等座', TRUE, 20),
        ('SECOND',   '二等座', TRUE, 30),
        ('HARD_SEAT','硬座',   TRUE, 40);

    INSERT INTO formation_template (
        formation_code, formation_name, applicable_train_type,
        description
    ) VALUES (
        'EMU_GC_4', 'G/C 型四节课程缩编动车组', 'G/C',
        '商务座10席 + 一等座28席 + 二等座180席，共218席'
    );
    SET v_gc_formation = LAST_INSERT_ID();

    INSERT INTO formation_template (
        formation_code, formation_name, applicable_train_type,
        description
    ) VALUES (
        'EMU_D_4', 'D 型四节课程缩编动车组', 'D',
        '一等座28席 + 二等座270席，共298席'
    );
    SET v_d_formation = LAST_INSERT_ID();

    INSERT INTO formation_template (
        formation_code, formation_name, applicable_train_type,
        description
    ) VALUES (
        'CONVENTIONAL_3', '普速三节课程缩编座车', 'K/T/Z/数字',
        '三节硬座车，每节100席，共300席'
    );
    SET v_conventional_formation = LAST_INSERT_ID();

    -- G/C：商务座采用 AF，一等座采用 ACDF，二等座采用 ABCDF。
    CALL sp_v007_add_carriage(v_gc_formation, 1, 'C01', '商务座车', 'BUSINESS', 5, 'AF');
    CALL sp_v007_add_carriage(v_gc_formation, 2, 'C02', '一等座车', 'FIRST', 7, 'ACDF');
    CALL sp_v007_add_carriage(v_gc_formation, 3, 'C03', '二等座车', 'SECOND', 18, 'ABCDF');
    CALL sp_v007_add_carriage(v_gc_formation, 4, 'C04', '二等座车', 'SECOND', 18, 'ABCDF');

    -- D：一等座采用 ACDF，二等座采用 ABCDF。
    CALL sp_v007_add_carriage(v_d_formation, 1, 'C01', '一等座车', 'FIRST', 7, 'ACDF');
    CALL sp_v007_add_carriage(v_d_formation, 2, 'C02', '二等座车', 'SECOND', 18, 'ABCDF');
    CALL sp_v007_add_carriage(v_d_formation, 3, 'C03', '二等座车', 'SECOND', 18, 'ABCDF');
    CALL sp_v007_add_carriage(v_d_formation, 4, 'C04', '二等座车', 'SECOND', 18, 'ABCDF');

    -- 普速课程模型暂只研究硬座，统一采用 ABCDF。
    CALL sp_v007_add_carriage(v_conventional_formation, 1, 'C01', '硬座车', 'HARD_SEAT', 20, 'ABCDF');
    CALL sp_v007_add_carriage(v_conventional_formation, 2, 'C02', '硬座车', 'HARD_SEAT', 20, 'ABCDF');
    CALL sp_v007_add_carriage(v_conventional_formation, 3, 'C03', '硬座车', 'HARD_SEAT', 20, 'ABCDF');

    UPDATE train_run AS tr
    JOIN train AS t ON t.train_no = tr.train_no
    SET tr.formation_id = CASE
        WHEN t.train_type IN ('高速动车', '城际动车') THEN v_gc_formation
        WHEN t.train_type = '动车组' THEN v_d_formation
        WHEN t.train_type IN ('快速', '直达特快', '特快', '普快')
            THEN v_conventional_formation
        ELSE NULL
    END,
    tr.version = tr.version + 1;

    IF EXISTS (SELECT 1 FROM train_run WHERE formation_id IS NULL) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'V007_UNMAPPED_TRAIN_TYPE';
    END IF;

    INSERT INTO train_run_seat (run_id, seat_id, occupied_mask, version)
    SELECT tr.run_id, s.seat_id, 0, 0
      FROM train_run AS tr
      JOIN carriage_template AS ct
        ON ct.formation_id = tr.formation_id AND ct.active = TRUE
      JOIN seat AS s
        ON s.carriage_id = ct.carriage_id AND s.active = TRUE;

    COMMIT;
END$$

DELIMITER ;

CALL sp_v007_apply_capacity();

DROP PROCEDURE sp_v007_apply_capacity;
DROP PROCEDURE sp_v007_add_carriage;

