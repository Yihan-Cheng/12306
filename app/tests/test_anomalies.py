import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import anomalies as a


def seat(**changes):
    return dict(dict(run_id=1,seat_id=2,carriage_no=1,seat_no="01A",stop_count=5,
                     occupied_mask=9,expected_mask=9,allocated_segments=2), **changes)


def sample(tick, queued=2, age=10):
    return dict(tick=tick,captured_at=str(tick),queued=queued,oldest_seconds=age,
                processing=0,expired_leases=0,retried=0)


class AnomalyTests(unittest.TestCase):
    def test_non_overlapping_reuse_and_empty_inventory(self):
        self.assertEqual(a.inventory_result([seat()])["status"], "normal")
        self.assertEqual(a.inventory_result([])["status"], "empty")

    def test_mask_difference_and_overlap_even_when_masks_match(self):
        r = a.inventory_result([seat(occupied_mask=1), seat(allocated_segments=3)])
        self.assertEqual(r["anomaly_count"], 2)
        self.assertEqual(r["findings"][0]["differing_segments"], [4])
        self.assertTrue(r["findings"][1]["overlapping_allocations"])
        self.assertEqual(r["findings"][1]["differing_segments"], [])

    def test_buffer_requires_three_time_spaced_growing_samples(self):
        rows = [sample(0,2,10),sample(5,4,15),sample(10,7,20)]
        self.assertEqual(a.buffer_result(rows,now=10)["status"], "anomaly")
        self.assertEqual(a.buffer_result(rows[:2],now=5)["status"], "warming")
        self.assertEqual(a.buffer_result([sample(0),sample(1),sample(2)],now=2)["status"], "warming")
        rows[-1]["queued"] = 1
        self.assertEqual(a.buffer_result(rows,now=10)["status"], "normal")
        self.assertEqual(a.buffer_result(rows,now=26)["status"], "unavailable")

    def test_failed_sampling_resets_window(self):
        sampler = a.BufferSampler()
        sampler.record(sample(0),tick=0)
        sampler.record(sample(5),tick=5)
        sampler.failed()
        self.assertEqual(sampler.result()["status"], "unavailable")
        sampler.record(sample(10),tick=10)
        self.assertEqual(len(sampler.samples),1)
        sampler.record(sample(30),tick=30)
        self.assertEqual(len(sampler.samples),1)

    def test_empty_buffer_aggregate_and_healthy_recovery(self):
        sampler = a.BufferSampler()
        for tick in (0,5,10):
            sampler.record({"captured_at":"test", "queued":None},tick=tick)
        self.assertEqual(a.buffer_result(list(sampler.samples),now=10)["status"],"normal")

    def test_model_failure_preserves_rule_decision(self):
        with patch.dict(os.environ, {"CR12306_AI_API_KEY":""}):
            report = a.demo_anomalies()
        self.assertEqual(report["inventory"]["anomaly_count"],2)
        self.assertEqual(report["inventory"]["mask_mismatch_count"],1)
        self.assertEqual(report["inventory"]["overlap_seat_count"],1)
        self.assertEqual(report["buffer"]["status"],"anomaly")
        with patch.dict(os.environ, {"CR12306_AI_API_KEY":"test-only"}), patch.object(a,"call_tool") as model:
            model.return_value = {"explanation":"请核对库存事件。"}
            self.assertIn("模型", a.explain_report(report)["mode"])
            model.side_effect = TimeoutError
            self.assertIn("暂不可用",a.explain_report(report)["mode"])
            self.assertEqual(report["inventory"]["anomaly_count"],2)

    def test_validate_and_bind_input(self):
        with self.assertRaises(ValueError):
            a.check_anomalies("2026-10-14","G1;DROP TABLE seat",lambda *args:[],a.BufferSampler())
        seen=[]
        a.check_anomalies("2026-10-14","g8359",lambda *args:seen.append(args) or [],a.BufferSampler())
        self.assertEqual(seen[0][1],["2026-10-14","G8359"])
