import io
import sys
import unittest
from http.client import HTTPMessage
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class AdminRefundTests(unittest.TestCase):
    def test_refund_with_body_consumes_only_current_request(self):
        handler = server.Handler.__new__(server.Handler)
        handler.path = "/api/admin/ai/orders/42/refund"
        handler.headers = HTTPMessage()
        handler.headers["Content-Length"] = "2"
        handler.rfile = io.BytesIO(b"{}GET /api/admin/ai/orders HTTP/1.1\r\n")
        handler.send_json = Mock()
        result = {"order_id": 42, "action": "REFUNDED"}
        with patch.object(server, "current_admin", return_value={"admin_user_id": 1}), \
                patch.object(server, "ai_order_action", return_value=result) as action:
            handler.do_POST()
        action.assert_called_once_with(42)
        handler.send_json.assert_called_once_with(result)
        self.assertTrue(handler.rfile.read().startswith(b"GET "))

    def test_refund_and_cancel_keep_success_if_matching_fails(self):
        for status, action, procedure in (("PAID", "REFUNDED", "sp_refund_paid_order"),
                                          ("PENDING_PAYMENT", "CANCELLED", "sp_cancel_unpaid_order")):
            with self.subTest(status=status), \
                    patch.object(server, "mysql_rows", side_effect=[[{"user_id": 5, "order_status": status}],
                                                                     [{"refund_id": 9}]]) as execute, \
                    patch.object(server, "match_after_release", side_effect=server.DatabaseError("match unavailable")):
                result = server.ai_order_action(42)
                self.assertEqual(result["action"], action)
                self.assertTrue(result["waitlist_pending"])
                self.assertIn(procedure, execute.call_args.args[0])

    def test_repeated_actions_skip_order_writes(self):
        for status in ("REFUNDED", "CANCELLED"):
            with self.subTest(status=status), \
                    patch.object(server, "mysql_rows", return_value=[{"user_id": 5, "order_status": status}]) as execute:
                self.assertEqual(server.ai_order_action(42), {"order_id": 42, "action": status, "already_processed": True})
                execute.assert_called_once()
