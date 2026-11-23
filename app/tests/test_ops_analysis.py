import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ops_analysis as analysis
from ops_qa import operations_answer


def metadata(*, omit=()):
    return [dict(view_name=dataset.view, column_name=column, data_type="varchar")
            for key, dataset in analysis.DATASETS.items()
            for column in sorted(set(analysis.dimension_columns(dataset).values()) | {
                column for metric in analysis.METRICS.values() if metric.dataset == key for column in metric.columns})
            if column not in omit]


def plan(**changes):
    return {"metric": "paid_orders", "group_by": ["train_no", "seat_type"],
            "filters": {"origin": [], "destination": [], "seat_type": [], "status": []},
            "sort": "desc", "limit": 20, "clarify": "", **changes}


class SchemaOperations(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"CR12306_AI_API_KEY": "test-only"})
        env.start()
        self.addCleanup(env.stop)

    def ask(self, question, read):
        return operations_answer(question, "2026-10-14", read)

    def test_routing_group_query_dates_and_schema(self):
        schema = metadata() + [dict(view_name="v_ops_analysis_orders", column_name="private_column", data_type="varchar")]
        read = Mock(side_effect=[schema, [{"train_no": "G8359", "seat_type": "二等座", "metric_value": 2}]])
        with patch.object(analysis, "call_tool", return_value=plan()) as model:
            answer = self.ask("2026-10-14到2026-10-16比较G8359、G1304已支付订单，按车次和席别分组", read)
        self.assertIn("information_schema.COLUMNS", read.call_args_list[0].args[0])
        self.assertIn("数据库列", model.call_args.args[2])
        self.assertNotIn("private_column", model.call_args.args[2])
        sql, params = read.call_args.args
        self.assertIn("COUNT(DISTINCT order_id)", sql)
        self.assertIn("service_date BETWEEN %s AND %s", sql)
        self.assertIn("GROUP BY train_no, seat_type", sql)
        self.assertEqual(params, ["2026-10-14", "2026-10-16", "G8359", "G1304", "PAID"])
        self.assertIn("按车次、席别分组", answer["answer"])

    def test_value_is_bound_and_buffer_groups_are_limited(self):
        value = "测试站' --"
        filters = {**plan()["filters"], "origin": [value], "status": ["FAILED"]}
        read = Mock(side_effect=[metadata(), [{"origin": "A", "metric_value": 5}, {"origin": "B", "metric_value": 3}]])
        with patch.object(analysis, "call_tool", return_value=plan(metric="buffer_requests", group_by=["origin"],
                                                                  filters=filters, limit=1)):
            answer = self.ask("按上车站统计失败的缓冲请求，取第一名", read)
        self.assertIn("v_ops_analysis_buffer", answer["sql"])
        self.assertNotIn(value, answer["sql"])
        self.assertEqual(answer["params"], ["2026-10-14", value, "FAILED"])
        self.assertEqual(len(answer["rows"]), 1)
        self.assertIn("已按指标降序截取", answer["answer"])

    def test_plan_cannot_reference_unavailable_or_unapproved_fields(self):
        for reply in (plan(group_by=["passenger_id"]), plan(limit=True), plan(sql="SELECT 1"),
                      plan(metric="average_elapsed"), plan(filters={**plan()["filters"], "status": ["REFUNDED"]})):
            with self.subTest(reply=reply), patch.object(analysis, "call_tool", return_value=reply):
                read = Mock(return_value=metadata(omit=("elapsed_ms",)))
                answer = self.ask("运营数据分组", read)
                self.assertIn("clarify", answer)
                read.assert_called_once()

    def test_invalid_scope_and_unavailable_model_do_not_execute_reports(self):
        read = Mock(return_value=metadata())
        with patch.object(analysis, "call_tool", side_effect=TimeoutError) as model:
            self.assertIn("31 天", self.ask("2026-10-01至2026-12-01订单数", read)["clarify"])
            self.assertIn("运营日", self.ask("今天按席别统计订单数", read)["clarify"])
            read.assert_not_called()
            model.assert_not_called()
            self.assertIn("模型接口暂不可用", self.ask("按席别统计订单数", read)["clarify"])
            read.assert_called_once()


if __name__ == "__main__":
    unittest.main()
