import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops_qa as ops


class OperationsQuestions(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"CR12306_AI_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.read = Mock(return_value=[])

    def ask(self, text):
        return ops.operations_answer(text, "2026-10-14", self.read)

    def test_waiting_count_and_inventory_are_distinct(self):
        self.read.return_value = [dict(train_no="G8359", origin="南通西", destination="上海虹桥",
                                       waiting_people=3, second_seats=0)]
        r = self.ask("G8359 哪个区间候补人数最多？这个区间的二等座还剩多少？")
        self.assertEqual(r["params"], ["2026-10-14", "G8359"])
        self.assertIn("3 人", r["answer"])
        self.assertIn("余 0 张", r["answer"])
        self.assertTrue(r["sql"].endswith("LIMIT 1"))
        self.read.return_value[0]["second_seats"] = None
        self.assertIn("没有在售", self.ask("g8359 候补区间排行前5名")["answer"])

    def test_no_waits_is_not_zero_inventory(self):
        r = self.ask("候补区间排行前 20 项")
        self.assertTrue(r["sql"].endswith("LIMIT 20"))
        self.assertIn("没有正在排队", r["answer"])
        self.assertNotIn("余 0", r["answer"])

    def test_distinct_orders_and_dates(self):
        self.read.return_value = [{"paid_orders": 0}]
        r = self.ask("2026-10-15 G8359 已支付订单有多少笔？")
        self.assertEqual(r["params"], ["2026-10-15", "G8359"])
        self.assertIn("COUNT(DISTINCT order_id)", r["sql"])
        self.assertIn("0 笔", r["answer"])

    def test_status_and_buffer(self):
        self.read.return_value = [{"request_status": "QUEUED", "request_count": 3}]
        self.assertIn("排队中 3 条", self.ask("缓冲请求状态分布")["answer"])
        self.read.return_value = [{"order_status": "PAID", "orders": 2}]
        self.assertIn("已支付 2 笔", self.ask("订单状态分布")["answer"])

    def test_ambiguous_and_unsupported_scopes_do_not_execute(self):
        for q in ("今天的订单状态分布", "候补区间排行前50名", "昨天上海退票率多少", "列出所有乘客姓名",
                  "G8359和G1304订单状态分布", "2026-02-31订单状态分布", "仅统计真实乘客的订单状态分布"):
            self.assertIn("clarify", self.ask(q), q)
        self.read.assert_not_called()

    def test_model_query_and_validation(self):
        good = ops.query_for(ops.REPORTS["orders"], None, 20)
        with patch.dict(os.environ, {"CR12306_AI_API_KEY": "test-only"}), patch.object(ops, "call_tool") as model:
            model.return_value = {"sql": good, "clarify": ""}
            self.assertEqual(self.ask("订单状态分布")["mode"], "模型 NL2SQL")
            self.assertIn("2026-10-14", model.call_args.args[2])
            model.return_value = {"sql": good + "; SELECT 1", "clarify": ""}
            r = self.ask("订单状态分布")
            self.assertIn("未通过校验", r["mode"])
            self.assertEqual(self.read.call_args.args, (good, ["2026-10-14"]))
            self.read.reset_mock()
            self.assertIn("clarify", self.ask("乘客明细"))
            self.read.assert_called_once()
            self.assertIn("information_schema.COLUMNS", self.read.call_args.args[0])
            model.side_effect = TimeoutError
            self.assertIn("暂不可用", self.ask("缓冲请求状态分布")["mode"])

    def test_template_model_clarification_preserves_long_complete_text(self):
        message = "该条件需要更明确的统计口径。" * 16 + "请确认要统计的指标。"
        self.assertGreater(len(message), 200)
        with patch.dict(os.environ, {"CR12306_AI_API_KEY": "test-only"}), patch.object(ops, "call_tool") as model:
            model.return_value = {"sql": "", "clarify": message}
            self.assertEqual(self.ask("订单状态分布")["clarify"], message)
        self.read.assert_not_called()
