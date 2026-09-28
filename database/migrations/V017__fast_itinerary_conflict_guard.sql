-- Keep the conflict check anchored on the passenger's indexed order items.
-- Expanding v_train_run_stop twice before that filter can scan the entire
-- timetable and hold seat locks long enough to time out concurrent bookings.
SET NAMES utf8mb4;
USE CR12306;

DROP TRIGGER IF EXISTS trg_order_item_passenger_itinerary_guard;
DELIMITER $$
CREATE TRIGGER trg_order_item_passenger_itinerary_guard
BEFORE INSERT ON order_item
FOR EACH ROW
guard: BEGIN
    DECLARE v_passenger_lock BIGINT UNSIGNED DEFAULT NULL;
    DECLARE v_departure_at DATETIME(6) DEFAULT NULL;
    DECLARE v_arrival_at DATETIME(6) DEFAULT NULL;
    DECLARE v_conflict_count INT UNSIGNED DEFAULT 0;

    IF NEW.item_status NOT IN ('HELD', 'CONFIRMED') THEN
        LEAVE guard;
    END IF;

    SELECT passenger_id INTO v_passenger_lock
      FROM passenger
     WHERE passenger_id = NEW.passenger_id
     FOR UPDATE;

    SELECT TIMESTAMP(tr.service_date, origin.departure_time)
               + INTERVAL origin.departure_day_offset DAY,
           TIMESTAMP(tr.service_date, destination.arrival_time)
               + INTERVAL destination.arrival_day_offset DAY
      INTO v_departure_at, v_arrival_at
      FROM train_run AS tr
      JOIN train_station AS origin
        ON origin.train_no = tr.train_no
       AND origin.station_order = NEW.from_order
      JOIN train_station AS destination
        ON destination.train_no = tr.train_no
       AND destination.station_order = NEW.to_order
     WHERE tr.run_id = NEW.run_id;

    IF v_departure_at IS NULL OR v_arrival_at IS NULL
       OR v_arrival_at <= v_departure_at THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PASSENGER_ITINERARY_TIME_INVALID';
    END IF;

    SELECT COUNT(*) INTO v_conflict_count
      FROM order_item AS oi
      STRAIGHT_JOIN train_run AS existing_run
        ON existing_run.run_id = oi.run_id
      STRAIGHT_JOIN train_station AS existing_origin
        ON existing_origin.train_no = existing_run.train_no
       AND existing_origin.station_order = oi.from_order
      STRAIGHT_JOIN train_station AS existing_destination
        ON existing_destination.train_no = existing_run.train_no
       AND existing_destination.station_order = oi.to_order
     WHERE oi.passenger_id = NEW.passenger_id
       AND oi.item_status IN ('HELD', 'CONFIRMED')
       AND TIMESTAMP(existing_run.service_date, existing_origin.departure_time)
               + INTERVAL existing_origin.departure_day_offset DAY < v_arrival_at
       AND TIMESTAMP(existing_run.service_date, existing_destination.arrival_time)
               + INTERVAL existing_destination.arrival_day_offset DAY > v_departure_at;

    IF v_conflict_count > 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'PASSENGER_ITINERARY_CONFLICT';
    END IF;
END$$
DELIMITER ;
