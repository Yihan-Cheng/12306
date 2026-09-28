"""Read one consistent, administrator-only inventory snapshot for projection."""

import json


def inventory_snapshot(mysql_rows, run_id, from_order=1, to_order=None,
                       seat_type_id=None, carriage_no=None):
    # A single connection and read-only snapshot keep counters, seats and names
    # consistent even while bookings and refunds commit during this request.
    rows = mysql_rows(f"""
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY;
SELECT 'run' kind, JSON_OBJECT('run_id',run_id,'train_no',train_no,
 'service_date',service_date,'stop_count',stop_count,'run_status',run_status,
 'captured_at',NOW(6)) payload FROM train_run WHERE run_id={run_id}
UNION ALL
SELECT 'stop',JSON_OBJECT('station_order',ts.station_order,'station_name',s.station_name)
 FROM train_run tr JOIN train_station ts ON ts.train_no=tr.train_no
 JOIN station s ON s.station_id=ts.station_id WHERE tr.run_id={run_id}
UNION ALL
SELECT 'seat',JSON_OBJECT('seat_id',s.seat_id,'seat_no',s.seat_no,'row_no',s.row_no,
 'position_code',s.position_code,'seat_type_id',s.seat_type_id,
 'seat_type_name',st.seat_type_name,'carriage_no',ct.carriage_no,
 'occupied_mask',CAST(trs.occupied_mask AS CHAR))
 FROM train_run_seat trs JOIN seat s ON s.seat_id=trs.seat_id
 JOIN carriage_template ct ON ct.carriage_id=s.carriage_id
 JOIN seat_type st ON st.seat_type_id=s.seat_type_id WHERE trs.run_id={run_id}
UNION ALL
SELECT 'allocation',JSON_OBJECT('seat_id',sa.seat_id,'order_id',o.order_id,
 'passenger_name',p.passenger_name,'passenger_id',p.passenger_id,
 'from_order',sa.from_order,'to_order',sa.to_order,
 'allocation_status',sa.allocation_status,'order_status',o.order_status,
 'order_source',o.order_source,'is_ai',LEFT(u.username,3)='ai_',
 'allocated_at',sa.allocated_at)
 FROM seat_allocation sa JOIN order_item oi ON oi.order_item_id=sa.order_item_id
 JOIN ticket_order o ON o.order_id=oi.order_id
 JOIN passenger p ON p.passenger_id=oi.passenger_id JOIN app_user u ON u.user_id=o.user_id
 WHERE sa.run_id={run_id} AND sa.allocation_status IN ('HOLD','CONFIRMED')
UNION ALL
SELECT 'wait',JSON_OBJECT('wait_request_id',wr.wait_request_id,
 'seat_type_id',wr.seat_type_id,'seat_type_name',st.seat_type_name,
 'from_order',wr.from_order,'to_order',wr.to_order,'wait_status',wr.wait_status,
 'passenger_count',wr.passenger_count,'created_at',wr.created_at,
 'cutoff_at',wr.cutoff_at,'skip_count',wr.skip_count,
 'position_code',wr.requested_position_code,'allow_fallback',wr.allow_position_fallback,
 'payment_status',wp.payment_status,'matched_order_id',wr.matched_order_id,
 'matched_order_status',o.order_status,
 'passengers',(SELECT JSON_ARRAYAGG(JSON_OBJECT('passenger_id',p.passenger_id,
   'passenger_name',p.passenger_name)) FROM wait_passenger wps
   JOIN passenger p ON p.passenger_id=wps.passenger_id WHERE wps.wait_request_id=wr.wait_request_id))
 FROM wait_request wr JOIN seat_type st ON st.seat_type_id=wr.seat_type_id
 LEFT JOIN wait_payment wp ON wp.wait_request_id=wr.wait_request_id
 LEFT JOIN ticket_order o ON o.order_id=wr.matched_order_id WHERE wr.run_id={run_id};
COMMIT;
""")
    data = {kind: [] for kind in ('run', 'stop', 'seat', 'allocation', 'wait')}
    for row in rows:
        data[row['kind']].append(json.loads(row['payload']))
    if not data['run']:
        raise ValueError('车次不存在')
    run = data['run'][0]
    to_order = to_order or run['stop_count']
    if not 1 <= from_order < to_order <= run['stop_count']:
        raise ValueError('请选择有效的上下车站')
    mask = ((1 << (to_order - from_order)) - 1) << (from_order - 1)
    stops = sorted(data['stop'], key=lambda item: item['station_order'])
    names = {stop['station_order']: stop['station_name'] for stop in stops}

    def annotate(item):
        item['from_station_name'] = names[item['from_order']]
        item['to_station_name'] = names[item['to_order']]
        item['in_interval'] = item['from_order'] < to_order and item['to_order'] > from_order
        return item

    allocations = {}
    for item in data['allocation']:
        allocations.setdefault(item['seat_id'], []).append(annotate(item))
    types = {s['seat_type_id']: s['seat_type_name'] for s in data['seat']}
    if seat_type_id and seat_type_id not in types:
        raise ValueError('该车次没有这个席别')
    typed_seats = [s for s in data['seat'] if not seat_type_id or s['seat_type_id'] == seat_type_id]
    carriages = sorted({s['carriage_no'] for s in typed_seats})
    if carriage_no is not None and carriage_no not in carriages:
        raise ValueError('所选席别不在这节车厢中')
    seats = []
    for seat in typed_seats:
        if carriage_no is not None and seat['carriage_no'] != carriage_no:
            continue
        seat['occupants'] = sorted(allocations.get(seat['seat_id'], []), key=lambda x: x['from_order'])
        overlapping = [a for a in seat['occupants'] if a['in_interval']]
        seat['status'] = 'FREE'
        if int(seat['occupied_mask']) & mask:
            seat['status'] = ('HOLD' if any(a['allocation_status'] == 'HOLD' for a in overlapping)
                              else 'WAITLIST' if any(a['order_source'] == 'WAITLIST' for a in overlapping)
                              else 'PAID')
        seats.append(seat)
    seats.sort(key=lambda s: (s['carriage_no'], s['row_no'] or 0, s['seat_no']))
    pending_statuses = {'WAITING', 'MATCHING', 'MATCHED_HOLD'}
    waiting = sorted((w for w in data['wait'] if w['wait_status'] in pending_statuses),
                     key=lambda w: (0 if w['skip_count'] >= 3 else 1, w['created_at'], w['wait_request_id']))
    queue_counts = {}
    for wait in waiting:
        key = wait['seat_type_id']
        queue_counts[key] = queue_counts.get(key, 0) + 1
        wait['queue_position'] = queue_counts[key]
    waits = [annotate(w) for w in data['wait']
             if (not seat_type_id or w['seat_type_id'] == seat_type_id)
             and w['from_order'] < to_order and w['to_order'] > from_order]
    waits.sort(key=lambda w: (0 if w['wait_status'] in pending_statuses else 1,
                             w.get('queue_position', 0), w['created_at'], w['wait_request_id']))
    return {
        'run': run, 'stops': stops,
        'seat_types': [{'seat_type_id': key, 'seat_type_name': value} for key, value in sorted(types.items())],
        'carriages': carriages, 'from_order': from_order, 'to_order': to_order,
        'seat_type_id': seat_type_id, 'carriage_no': carriage_no,
        'seats': seats, 'waits': waits,
        'summary': {
            'total': len(seats), 'free': sum(s['status'] == 'FREE' for s in seats),
            'held': sum(s['status'] == 'HOLD' for s in seats),
            'paid': sum(s['status'] in {'PAID', 'WAITLIST'} for s in seats),
            'waiting_people': sum(w['passenger_count'] for w in waits if w['wait_status'] in pending_statuses),
            'fulfilled_people': sum(w['passenger_count'] for w in waits
                                    if w['wait_status'] == 'FULFILLED' and w['matched_order_status'] == 'PAID'),
        },
    }
