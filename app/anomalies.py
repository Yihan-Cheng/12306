"""Deterministic anomaly decisions with bounded, process-local queue history."""
import json
import os
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone

from model_api import call_tool


BUFFER_SQL = """
SELECT NOW(6) AS captured_at,
 SUM(request_status='QUEUED') AS queued,
 SUM(request_status='PROCESSING') AS processing,
 COALESCE(MAX(CASE WHEN request_status='QUEUED'
   THEN TIMESTAMPDIFF(SECOND,created_at,NOW(6)) END),0) AS oldest_seconds,
 SUM(request_status='PROCESSING' AND lease_until<NOW(6)) AS expired_leases,
 SUM(request_status IN ('QUEUED','PROCESSING') AND attempt_count>1) AS retried
FROM booking_request_buffer
"""


def inventory_result(rows):
    findings = []
    for row in rows:
        actual, expected = int(row["occupied_mask"]), int(row["expected_mask"])
        overlap = int(row["allocated_segments"]) > expected.bit_count()
        if actual == expected and not overlap:
            continue
        changed = actual ^ expected
        item = {k: row[k] for k in ("run_id", "seat_id", "carriage_no", "seat_no")}
        item.update(actual_mask=str(actual), expected_mask=str(expected),
                    differing_segments=[i + 1 for i in range(int(row["stop_count"]) - 1) if changed & (1 << i)],
                    overlapping_allocations=overlap)
        findings.append(item)
    return {"status": "anomaly" if findings else ("normal" if rows else "empty"),
            "mask_mismatch_count": sum(f["actual_mask"] != f["expected_mask"] for f in findings),
            "overlap_seat_count": sum(f["overlapping_allocations"] for f in findings),
            "checked_seats": len(rows), "anomaly_count": len(findings), "findings": findings[:50],
            "definition": "同一只读快照中，对现有运行座位核对 HOLD、CONFIRMED 分配区间的按位或与库存位图。"
                          "另检查有效分配占用的区段总数是否超过合并位图的区段数。证据最多展示50个座位。"}


def buffer_result(samples, error=None, now=None):
    now = time.monotonic() if now is None else now
    public = [{k: v for k, v in s.items() if k != "tick"} for s in samples]
    result = {"samples": public, "interval_seconds": 5, "window_seconds": 10,
              "definition": "全库订票缓冲，最近3次有效采样覆盖至少10秒，排队数与最老请求等待秒数均逐次增加，"
                            "且最老请求已等待至少10秒时，判为持续积压。每5秒采样，失败或超过15秒中断后重新积累。"}
    if error or not samples or now - samples[-1]["tick"] > 15:
        return dict(result, status="unavailable", message="采样暂不可用，正在等待后台恢复。")
    tail = samples[-3:]
    if len(tail) < 3 or tail[-1]["tick"] - tail[0]["tick"] < 10:
        return dict(result, status="warming", message="采样中，需要至少3次连续采样，覆盖10秒。")
    growing = all(b["queued"] > a["queued"] and b["oldest_seconds"] > a["oldest_seconds"]
                  for a, b in zip(tail, tail[1:]))
    detected = growing and tail[-1]["oldest_seconds"] >= 10
    return dict(result, status="anomaly" if detected else "normal",
                message="最近3次采样满足持续积压规则。" if detected else "最近3次采样未触发持续积压规则。")


class BufferSampler:
    def __init__(self):
        self.samples = deque(maxlen=13)
        self.lock = threading.Lock()
        self.error = None

    def record(self, row, tick=None):
        tick = time.monotonic() if tick is None else tick
        sample = {k: int(row.get(k) or 0) for k in ("queued", "processing", "oldest_seconds", "expired_leases", "retried")}
        sample.update(captured_at=str(row["captured_at"]), tick=tick)
        with self.lock:
            if self.samples and tick - self.samples[-1]["tick"] > 15:
                self.samples.clear()
            self.samples.append(sample)
            self.error = None

    def failed(self):
        with self.lock:
            self.samples.clear()
            self.error = True

    def result(self):
        with self.lock:
            return buffer_result(list(self.samples), self.error)

    def run(self, read_rows):
        while True:
            try:
                self.record(read_rows(BUFFER_SQL)[0])
            except Exception:
                self.failed()
            time.sleep(5)


def explain_report(report):
    """Keep model suggestions separate from the recorded rule decisions."""
    inventory, buffer = report["inventory"], report["buffer"]
    local = (
        f"本次核对 {inventory['checked_seats']} 个座位，发现 {inventory['anomaly_count']} 个异常座位。"
        "可按 run_id、seat_id 核对有效分配区间、订单事件与释放库存事务。"
        if inventory["anomaly_count"] else
        f"本次核对 {inventory['checked_seats']} 个座位，库存一致性规则未发现异常。"
    ) if inventory["status"] != "empty" else "所选日期与车次没有可检查的运行座位，请核对查询条件。"
    local += buffer["message"]
    if buffer["status"] == "anomaly":
        local += "可查看订票工作线程、重试请求和过期处理租约。增长原因仍需结合日志确认。"
    key = os.getenv("CR12306_AI_API_KEY")
    if not key:
        return {"mode": "本地规则解释", "text": local}
    evidence = {"scope": report["scope"], "inventory": {k: v for k, v in inventory.items() if k != "findings"},
                "buffer": buffer}
    schema = {"name": "explain_anomalies", "description": "解释已经由程序判定的检测结果",
              "parameters": {"type": "object", "properties": {"explanation": {"type": "string"}},
                             "required": ["explanation"], "additionalProperties": False}}
    try:
        reply = call_tool(json.dumps(evidence, ensure_ascii=False), key,
                          "你是铁路运营诊断助手。仅据证据解释规则状态和建议人工核查的方向。"
                          "库存日期是固定演示班次运营日，缓冲覆盖全库并按当前真实时间采样，两者时间范围独立。"
                          "缓冲样本直接SELECT数据库取得；采样失败或过期会显示unavailable，"
                          "有效样本均为0表示数据库中没有对应状态的请求。"
                          "mask_mismatch_count是两份位图不同的座位数，overlap_seat_count是重叠分配座位数，"
                          "anomaly_count是两者并集，禁止将其等同于所有位图不一致。"
                          "保持检测结果，推测必须标明待验证。不要编造故障原因、数字或已完成的修复。"
                          "用简短中文回复，最多500字。", schema)
        if not isinstance(reply.get("explanation"), str) or not reply["explanation"].strip():
            raise ValueError("missing explanation")
        return {"mode": "模型辅助解释（建议需人工核查）", "text": reply["explanation"][:1500]}
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return {"mode": "本地规则解释（模型接口暂不可用）", "text": local}


def check_anomalies(day, train, read_rows, sampler, explain=False):
    date = datetime.strptime(day, "%Y-%m-%d").date()
    if date.isoformat() != day:
        raise ValueError("日期格式必须为 YYYY-MM-DD")
    train = train.strip().upper()
    if not re.fullmatch(r"[A-Z]?\d{1,6}", train):
        raise ValueError("请输入一个完整车次号")
    rows = read_rows("SELECT * FROM v_anomaly_seats WHERE service_date=%s AND train_no=%s", [day, train])
    report = {"scope": f"{day} · {train} 库存；全库订票缓冲",
              "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "inventory": inventory_result(rows), "buffer": sampler.result()}
    if explain:
        report["explanation"] = explain_report(report)
    return report


def demo_anomalies():
    rows = [
        dict(run_id=0,seat_id=1,carriage_no=1,seat_no="01A",stop_count=4,
             occupied_mask=3,expected_mask=1,allocated_segments=1),
        dict(run_id=0,seat_id=2,carriage_no=1,seat_no="01B",stop_count=4,
             occupied_mask=7,expected_mask=7,allocated_segments=4),
    ]
    samples = [dict(tick=t, captured_at=f"模拟第{t}秒", queued=q, oldest_seconds=age,
                    processing=1, expired_leases=0, retried=0)
               for t,q,age in ((0,2,10),(5,4,15),(10,7,20))]
    report = {"source": "模拟证据样本，独立于业务数据", "scope": "模拟库存与模拟缓冲",
              "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "inventory": inventory_result(rows), "buffer": buffer_result(samples, now=10)}
    report["explanation"] = {
        "mode": "样本说明", "text": "01A库存位图多占用了第2个区段；01B有重叠的有效分配。"
                                "模拟缓冲连续3次排队数和最老等待时间上升，触发持续积压规则。"}
    return report
