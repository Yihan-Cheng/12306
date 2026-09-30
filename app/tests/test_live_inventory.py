"""Pure snapshot semantics: no database writes or external services required."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_inventory import inventory_snapshot


class InventorySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.data = {
            'run': [{'run_id': 1, 'stop_count': 5}],
            'stop': [{'station_order': n, 'station_name': f'S{n}'} for n in range(1, 6)],
            'seat': [
                dict(seat_id=1, seat_type_id=6, seat_type_name='一等座',
                     carriage_no=2, row_no=1, seat_no='01A', occupied_mask='9'),
                dict(seat_id=2, seat_type_id=6, seat_type_name='一等座',
                     carriage_no=3, row_no=1, seat_no='01A', occupied_mask='0'),
                dict(seat_id=3, seat_type_id=7, seat_type_name='二等座',
                     carriage_no=4, row_no=1, seat_no='01A', occupied_mask='0'),
            ],
            'allocation': [
                dict(seat_id=1, from_order=1, to_order=2, passenger_name='同学甲',
                     allocation_status='CONFIRMED', order_source='DIRECT'),
                dict(seat_id=1, from_order=4, to_order=5, passenger_name='同学乙',
                     allocation_status='CONFIRMED', order_source='WAITLIST'),
            ],
            'wait': [],
        }

    def snapshot(self, **kwargs):
        def rows(_sql):
            return [{'kind': kind, 'payload': json.dumps(item)}
                    for kind, items in self.data.items() for item in items]
        return inventory_snapshot(rows, 1, **kwargs)

    def wait(self, number, start=1, end=5, skip=0, status='WAITING', order_status=None):
        return dict(wait_request_id=number, seat_type_id=6, from_order=start,
                    to_order=end, skip_count=skip, wait_status=status,
                    matched_order_status=order_status, passenger_count=1,
                    created_at=f'2026-09-28 12:00:{number:02d}')

    def test_non_overlapping_intervals_reuse_seat(self):
        result = self.snapshot(from_order=2, to_order=4, seat_type_id=6)
        self.assertEqual(result['summary']['free'], 2)
        seat = result['seats'][0]
        self.assertEqual(len(seat['occupants']), 2)
        self.assertTrue(all(not a['in_interval'] for a in seat['occupants']))

    def test_overlapping_allocations_count_one_seat(self):
        result = self.snapshot(seat_type_id=6, carriage_no=2)
        self.assertEqual(result['summary']['paid'], 1)
        self.assertEqual(result['summary']['total'], 1)
        self.assertEqual(result['seats'][0]['status'], 'WAITLIST')
        self.assertEqual(len(result['seats'][0]['occupants']), 2)

    def test_hold_is_separate_from_paid(self):
        self.data['allocation'][0]['allocation_status'] = 'HOLD'
        result = self.snapshot(from_order=1, to_order=2, seat_type_id=6)
        self.assertEqual(result['summary']['held'], 1)
        self.assertEqual(result['summary']['paid'], 0)

    def test_wait_queue_uses_fairness_and_keeps_rank_after_interval_filter(self):
        self.data['wait'] = [self.wait(1), self.wait(2, 4, 5, skip=3), self.wait(3)]
        result = self.snapshot(from_order=1, to_order=2, seat_type_id=6, carriage_no=3)
        self.assertEqual([w['wait_request_id'] for w in result['waits']], [1, 3])
        self.assertEqual([w['queue_position'] for w in result['waits']], [2, 3])
        self.assertEqual(result['summary']['waiting_people'], 2)
        self.assertEqual(result['summary']['total'], 1)

    def test_refunded_fulfilments_do_not_count_as_current_tickets(self):
        self.data['wait'] = [self.wait(1, status='FULFILLED', order_status='PAID'),
                             self.wait(2, status='FULFILLED', order_status='REFUNDED')]
        result = self.snapshot()
        self.assertEqual(result['summary']['fulfilled_people'], 1)
        self.assertEqual(len(result['waits']), 2)

    def test_invalid_scope_is_rejected(self):
        for args in [dict(from_order=3, to_order=3), dict(to_order=6),
                     dict(seat_type_id=99), dict(seat_type_id=6, carriage_no=4)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.snapshot(**args)


if __name__ == '__main__':
    unittest.main()
