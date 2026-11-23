import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ai_booking as booking


TARGET = dict(run_id=25, train_no="G8359", service_date="2026-10-14", origin="盐城", destination="义乌",
              from_order=1, to_order=14, seat_type_id=3, seat_type_name="二等座", available_seats=28)


def plan(**changes):
    return dict(intent="targeted", train_no="G8359", origin="盐城", destination="义乌", seat_type="二等座",
                users=None, reserve_seats=None, pay_rate=None, concurrency=None, waitlist=None, clarify="") | changes


class BookingPreviewTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"CR12306_AI_API_KEY": "test-only"})
        env.start()
        self.addCleanup(env.stop)

    def test_reserve_plan_reads_one_exact_product_and_preserves_zero(self):
        read = Mock(return_value=[TARGET])
        with patch.object(booking, "call_tool", return_value=plan(reserve_seats=0)) as model:
            result = booking.booking_preview("2026-10-14 G8359 盐城到义乌二等座预留0张", "2026-10-15", read)
        self.assertIn("v_ops_ai_products", model.call_args.args[2])
        read.assert_called_once_with(booking.FIND_TARGET, ["2026-10-14", "G8359", "盐城", "义乌", "二等座"])
        self.assertEqual(result["task"], dict(mode="targeted", users=28, reserveSeats=0, concurrency=2,
                                            payRate=100, waitlist=False, runId=25, fromOrder=1, toOrder=14, seatTypeId=3))

    def test_inventory_only_has_no_start_payload(self):
        with patch.object(booking, "call_tool", return_value=plan(intent="availability")):
            result = booking.booking_preview("查G8359盐城到义乌二等座", "2026-10-14", Mock(return_value=[TARGET]))
        self.assertIsNone(result["task"])
        self.assertEqual(result["target"]["available_seats"], 28)

    def test_random_preserves_explicit_zero_payment_and_false_waitlist(self):
        read = Mock(return_value=[{"has_products": 1}])
        reply = plan(intent="random", train_no="", origin="", destination="", seat_type="",
                     users=20, concurrency=4, pay_rate=0, waitlist=False)
        with patch.object(booking, "call_tool", return_value=reply):
            result = booking.booking_preview("让20名乘客随机抢票", "2026-10-14", read)
            with self.assertRaises(booking.BookingPreviewError):
                booking.booking_preview("G8359让20名乘客随机抢票", "2026-10-14", read)
        read.assert_called_once_with(booking.RANDOM_SQL, [])
        self.assertEqual(result["task"], dict(mode="random", users=20, concurrency=4, payRate=0, waitlist=False))

    def test_invalid_plan_never_queries_inventory(self):
        read = Mock()
        for reply in (plan(users=501), plan(users=True), plan(sql="UPDATE x"),
                      plan(users=1, reserve_seats=10), plan(reserve_seats=10, waitlist=True),
                      plan(users=1, train_no="G1234")):
            with self.subTest(reply=reply), patch.object(booking, "call_tool", return_value=reply):
                with self.assertRaises(booking.BookingPreviewError):
                    booking.booking_preview("G8359 盐城到义乌二等座模拟压测", "2026-10-14", read)
        read.assert_not_called()

    def test_database_ambiguity_and_reserve_drift_stop_preparation(self):
        with patch.object(booking, "call_tool", return_value=plan(users=10)):
            with self.assertRaisesRegex(booking.BookingPreviewError, "没有唯一匹配"):
                booking.booking_preview("G8359 盐城到义乌二等座模拟压测", "2026-10-14", Mock(return_value=[TARGET, TARGET]))
        read = Mock(return_value=[TARGET])
        booking.check_reserved_seats(read, 25, 1, 14, 3, 18, 10)
        read.assert_called_once_with(booking.CHECK_TARGET, [25, 1, 14, 3])
        with self.assertRaisesRegex(booking.BookingPreviewError, "重新生成预览"):
            booking.check_reserved_seats(read, 25, 1, 14, 3, 20, 10)
