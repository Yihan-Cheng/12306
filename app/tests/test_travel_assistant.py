import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import travel_assistant as travel
import model_api


STATIONS = [
    dict(station_id=1, station_name="南通西", city="南通"),
    dict(station_id=2, station_name="上海虹桥", city="上海"),
    dict(station_id=3, station_name="常熟", city="苏州"),
    dict(station_id=4, station_name="上海", city="上海"),
]
DIRECT = dict(train_no="G8359", run_id=1, from_station_name="南通西", to_station_name="上海虹桥",
              from_station_id=1, to_station_id=2, departure_at="2026-10-14 13:05:00",
              arrival_at="2026-10-14 14:30:00", seat_type_id=2, seat_type_name="二等座",
              amount="45.10", available_seats="2", can_fulfill="1")


class TravelTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"CR12306_AI_API_KEY": ""})
        env.start()
        self.addCleanup(env.stop)
        self.direct = Mock(return_value=[DIRECT])
        self.transfer = Mock(return_value=[])

    def plan(self, question=travel.EXAMPLE):
        return travel.plan_trip(question, STATIONS, self.direct, self.transfer)

    def test_demo_example(self):
        result = self.plan("10月14日，两个人从南通西去上海虹桥，下午3点前到，优先直达。没有两张票的话，看看能不能换乘一次。")
        self.assertEqual(result["people"], 2)
        self.assertEqual(result["options"][0]["group_price"], "90.20")
        self.assertIn("15:00", result["summary"])
        self.transfer.assert_not_called()

    def test_transfer_has_two_valid_legs(self):
        self.direct.return_value = [dict(DIRECT, available_seats="1", can_fulfill="0")]
        candidate = dict(origin_id=1, transfer_station_id=3, destination_id=2, transfer_minutes=20, can_fulfill="1")
        for prefix, key in (("first", 7), ("second", 10)):
            for field in ("amount", "departure_at", "arrival_at", "available_seats", "seat_type_id", "seat_type_name"):
                candidate[f"{prefix}_{field}"] = DIRECT[field]
            candidate[f"{prefix}_run_id"] = key
            candidate[f"{prefix}_train_no"] = f"G{key}"
        self.transfer.return_value = [candidate, dict(candidate, second_available_seats=1),
                                      dict(candidate, second_arrival_at="2026-10-15 01:30:00")]
        result = self.plan()
        self.assertIn("最多余 1 张", result["answer"])
        self.assertEqual(len(result["options"]), 1)
        legs = result["options"][0]["legs"]
        self.assertEqual((legs[0]["to_station_id"], legs[1]["from_station_id"]), (3, 3))
        self.assertEqual(result["options"][0]["group_price"], "180.40")
        self.direct.return_value = [dict(DIRECT, run_id=i) for i in range(1, 5)]
        result = self.plan(travel.EXAMPLE.replace("一次", "1次"))
        self.assertEqual([len(o["legs"]) for o in result["options"]], [1, 1, 1, 2])
        self.assertIn("最多换乘 1 次", result["summary"])

    def test_transfer_limit_and_city_stations(self):
        for phrase in ("可以换乘1次", "最多一次换乘"):
            result = self.plan("从南通西到上海，" + phrase)
            self.assertIn("最多换乘 1 次", result["summary"])
            self.assertEqual(self.transfer.call_args.args[0]["to"], [2, 4])
        self.transfer.reset_mock()
        self.assertIn("仅直达", self.plan("从南通西到上海，最多换乘0次")["summary"])
        self.assertFalse(self.plan("从南通西到上海，可以换乘2次")["options"])
        self.transfer.assert_not_called()

    def test_constraints_and_city_scope(self):
        for name, expected in (("上海", None), ("上海站", 4)):
            self.plan("从南通西到" + name)
            self.assertEqual(self.direct.call_args.args[0]["toStation"], [expected])
        self.assertFalse(self.plan("从南通西到上海，三个人，不换乘")["options"])
        self.transfer.assert_not_called()
        for clause in ("14点前到", "一等座"):
            self.assertFalse(self.plan("从南通西到上海虹桥，" + clause)["options"])

    def test_unclear_requests(self):
        for question in ("怎么买", "从南通西到上海虹桥 六个人", "明天从南通西到上海虹桥",
                         "10月15日从南通西到上海虹桥", "从南通西到上海虹桥预算30元"):
            self.assertFalse(self.plan(question)["options"])
        self.direct.assert_not_called()

    def test_price_and_duplicate_seat_classes(self):
        self.direct.return_value = [DIRECT, dict(DIRECT, amount="75", seat_type_name="一等座"),
                                    dict(DIRECT, train_no="G2", run_id=2, amount="30", arrival_at="2026-10-14 15:00:00")]
        options = self.plan("从南通西到上海虹桥，最便宜")["options"]
        self.assertEqual([o["price"] for o in options], ["30", "45.10"])

    def test_model_tool_call(self):
        intent = travel.local_intent(travel.EXAMPLE, STATIONS)
        tool = {"function": {"name": "plan_trip", "arguments": json.dumps(intent)}}
        data = {"choices": [{"message": {"tool_calls": [tool]}}]}
        with patch.dict(os.environ, {"CR12306_AI_API_KEY": "test-only",
                                    "CR12306_AI_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                                    "CR12306_AI_TIMEOUT": "45"}), patch.object(
                model_api, "urlopen", return_value=io.BytesIO(json.dumps(data).encode())) as post:
            result = self.plan("帮我们俩挑一趟车")
            self.assertEqual(result["mode"], "模型 API")
            self.assertEqual(result["people"], 2)
            request = post.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
            self.assertEqual(json.loads(request.data)["tools"][0]["function"]["name"], "plan_trip")
            self.assertFalse(json.loads(request.data)["enable_thinking"])
            self.assertEqual(post.call_args.kwargs["timeout"], 45)

    def test_model_failure_falls_back(self):
        with patch.dict(os.environ, {"CR12306_AI_API_KEY": "test-only"}), patch.object(
                model_api, "urlopen", side_effect=TimeoutError):
            result = self.plan()
            self.assertIn("暂不可用", result["mode"])
            self.assertEqual(len(result["options"]), 1)


if __name__ == "__main__":
    unittest.main()
