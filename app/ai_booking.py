"""Translate simulator requests into checked, read-only booking previews."""
import os
import re
import unicodedata
from datetime import date

from model_api import call_tool
from travel_assistant import TRAIN_NO


class BookingPreviewError(ValueError):
    pass


TEXT_FIELDS = ("train_no", "origin", "destination", "seat_type", "clarify")
LIMITS = {"users": (1, 500), "concurrency": (1, 30), "pay_rate": (0, 100), "reserve_seats": (0, 500)}
INTENTS = ("availability", "targeted", "random")
FIELDS = {"intent": {"type": "string", "enum": ["", *INTENTS]},
          **{name: {"type": "string"} for name in TEXT_FIELDS},
          **{name: {"type": ["integer", "null"]} for name in LIMITS},
          "waitlist": {"type": ["boolean", "null"]}}
BOOKING_TOOL = {"name": "plan_ai_booking", "description": "解析只读余票查询或模拟订票参数",
                "parameters": {"type": "object", "properties": FIELDS,
                               "required": list(FIELDS), "additionalProperties": False}}

# Availability counts seats that are free along the whole requested segment.
TARGET_SQL = """SELECT p.run_id, p.train_no, p.service_date, p.origin, p.destination,
       p.from_order, p.to_order, p.seat_type_id, p.seat_type_name,
       COALESCE((SELECT SUM((s.occupied_mask &
           (((CAST(1 AS UNSIGNED) << (p.to_order - p.from_order)) - 1) << (p.from_order - 1))) = 0)
           FROM v_ops_ai_seats s WHERE s.run_id = p.run_id AND s.seat_type_id = p.seat_type_id), 0)
           AS available_seats
FROM v_ops_ai_products p
WHERE """
FIND_TARGET = TARGET_SQL + """p.service_date = %s AND p.train_no = %s
  AND p.origin = %s AND p.destination = %s AND p.seat_type_name = %s
LIMIT 2"""
CHECK_TARGET = TARGET_SQL + """p.run_id = %s AND p.from_order = %s AND p.to_order = %s AND p.seat_type_id = %s
LIMIT 1"""
RANDOM_SQL = "SELECT EXISTS (SELECT 1 FROM v_ops_ai_products) AS has_products"


def service_day(question, selected_date):
    dates = set(re.findall(r"(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", question))
    if len(dates) > 1 or re.search(r"今天|今日|明天|后天|昨天|昨日|\d+月\d+", question):
        raise BookingPreviewError("请在页面选择一个运营日，或写明一个 YYYY-MM-DD 日期。")
    day = next(iter(dates), selected_date)
    try:
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        raise BookingPreviewError("请选择有效的运营日期。") from None
    return day, bool(dates)


def validate_booking_plan(plan):
    if not isinstance(plan, dict) or plan.keys() != FIELDS.keys():
        raise BookingPreviewError("模型返回的计划字段不完整，请重新描述需求。")
    if any(not isinstance(plan[name], str) for name in TEXT_FIELDS):
        raise BookingPreviewError("模型返回的文本字段无效，请重新描述需求。")
    if plan["clarify"].strip():
        raise BookingPreviewError(plan["clarify"].strip()[:200])
    if plan["intent"] not in INTENTS or any(len(plan[name]) > 80 for name in TEXT_FIELDS):
        raise BookingPreviewError("模型返回的查询类型或字段无效，请重新描述需求。")
    for field, (minimum, maximum) in LIMITS.items():
        value = plan[field]
        if value is not None and (type(value) is not int or not minimum <= value <= maximum):
            raise BookingPreviewError("参数超出范围。人数 1–500，并发 1–30，支付率 0–100%，预留 0–500 张。")
    if plan["waitlist"] is not None and type(plan["waitlist"]) is not bool:
        raise BookingPreviewError("请明确无票时是否加入候补。")
    return {**plan, **{name: plan[name].strip() for name in TEXT_FIELDS}}


def check_reserved_seats(read_rows, run_id, from_order, to_order, seat_type_id, users, reserve):
    rows = read_rows(CHECK_TARGET, [run_id, from_order, to_order, seat_type_id])
    if not rows or int(rows[0]["available_seats"]) != users + reserve:
        raise BookingPreviewError("余票或售票状态已变化，请重新生成预览后再启动。")


def booking_preview(question, selected_date, read_rows):
    question = unicodedata.normalize("NFKC", question)
    day, explicit_day = service_day(question, selected_date)
    key = os.getenv("CR12306_AI_API_KEY")
    if not key:
        raise BookingPreviewError("请先配置模型 API Key，或展开手动配置。")
    prompt = ("你负责本地演示库的订票压测预览。返回结构化查询计划。"
              "只读视图 v_ops_ai_products 包含 run_id、train_no、service_date、origin、destination、"
              "from_order、to_order、seat_type_id、seat_type_name，只列出当前在售产品；"
              "v_ops_ai_seats 包含 run_id、seat_type_id、occupied_mask，用于按区间查余票。"
              f"本次运营日由后端确定为 {day}。"
              "availability 是只查余票，targeted 是指定车次压测，random 是全库随机模拟。"
              "查余票和定向压测需要完整的车次号、上车站、下车站和席别。按用户提供的站名填写，"
              "不能把城市猜成某个具体车站。'二等'可规范为'二等座'。"
              "定向压测要指定人数 users 或预留票数 reserve_seats，二者只能填一项。随机模拟须指定人数，"
              "适用于不限制日期、车次、站点和席别的请求。忽略未填写的页面日期在随机模式下的默认值。"
              "查余票时任务参数全部设为 null。没有指定的数字和候补设为 null，未指定的文本用空字符串。"
              "并发为 1–30，人数为 1–500，支付率为 0–100 的整数。"
              "遇到多车次、按城市选站、退票、写 SQL、无法表达的条件或缺少必填项时，填写 clarify。")
    try:
        reply = call_tool(question, key, prompt, BOOKING_TOOL)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        raise BookingPreviewError("模型 API 暂不可用，请重试或展开手动配置。") from None
    plan = validate_booking_plan(reply)
    intent = plan["intent"]
    users, reserve = plan["users"], plan["reserve_seats"]
    explicit_trains = set(re.findall(r"(?<![A-Za-z0-9])[A-Z][0-9]{1,5}(?![A-Za-z0-9])", question.upper()))
    if intent == "random":
        if (explicit_day or explicit_trains or reserve is not None
                or any(plan[name] for name in TEXT_FIELDS if name != "clarify")):
            raise BookingPreviewError("随机压测面向全库在售产品。需要限定车次、运营日或区间时，请使用定向压测。")
        if users is None:
            raise BookingPreviewError("请说明需模拟多少名乘客。")
        sql, params = RANDOM_SQL, []
        if not read_rows(sql, params)[0]["has_products"]:
            raise BookingPreviewError("演示库当前没有在售产品。")
        target = None
    else:
        train = plan["train_no"].upper()
        route = [plan[key] for key in ("origin", "destination", "seat_type")]
        if (not re.fullmatch(TRAIN_NO, train) or not all(route)
                or (explicit_trains and explicit_trains != {train})
                or not re.search(rf"(?<![A-Za-z0-9]){re.escape(train)}(?![A-Za-z0-9])", question.upper())):
            raise BookingPreviewError("请指定一个完整车次号、上下车站及席别。")
        if intent == "availability" and any(plan[key] is not None for key in (*LIMITS, "waitlist")):
            raise BookingPreviewError("请明确只查余票还是预览订票任务。")
        if intent == "targeted" and (users is None) == (reserve is None):
            raise BookingPreviewError("请指定模拟人数或目标预留票数，两者选一。")
        if reserve is not None and plan["waitlist"] is True:
            raise BookingPreviewError("预留余票和自动候补不能同时设置，请确认采用哪一种。")
        sql, params = FIND_TARGET, [day, train, *route]
        candidates = read_rows(sql, params)
        if len(candidates) != 1:
            raise BookingPreviewError("没有唯一匹配的在售产品，请核对运营日、车次、上下车站全名和席别。")
        target = candidates[0]
        if reserve is not None:
            available = int(target["available_seats"])
            users = available - reserve
            if not 1 <= users <= 500:
                raise BookingPreviewError(f"当前余票 {available} 张，按预留 {reserve} 张计算需模拟 {users} 人，任务人数须为 1–500。")

    task = None
    if intent != "availability":
        task = {"mode": intent, "users": users, "concurrency": plan["concurrency"] or (2 if reserve is not None else 8),
                "payRate": plan["pay_rate"] if plan["pay_rate"] is not None else (100 if reserve is not None else 70),
                "waitlist": plan["waitlist"] if plan["waitlist"] is not None else reserve is None}
        if target:
            task.update(runId=target["run_id"], fromOrder=target["from_order"],
                        toOrder=target["to_order"], seatTypeId=target["seat_type_id"])
        if reserve is not None:
            task["reserveSeats"] = reserve
    return {"target": target, "task": task, "sql": sql, "params": params}
