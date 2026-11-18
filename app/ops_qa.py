"""Constrained NL2SQL for administrator reports, with explicit metric definitions."""
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

from model_api import call_tool


@dataclass(frozen=True)
class Report:
    title: str
    definition: str
    select: str
    tail: str
    columns: tuple
    pattern: str


REPORTS = {
    "waiting": Report(
        "候补区间排行",
        "按班次和相同上下车站汇总 WAITING、MATCHING 请求的乘客人数，包含所有席别；"
        "二等座余票单独按同一区间全程空闲的座位计数。0 表示售罄，空值表示没有在售二等座产品。"
        "人数相同时按车次、上下车站排序。",
        "train_no, origin, destination, waiting_people, second_seats FROM v_ops_wait_segments",
        "ORDER BY waiting_people DESC, train_no, origin, destination",
        (("train_no", "车次"), ("origin", "上车站"), ("destination", "下车站"),
         ("waiting_people", "候补人数"), ("second_seats", "二等座余票")),
        r"(?:哪个|哪些|哪段|哪一段|各)?(?:乘车)?(?:区间)?(?:的)?(?:等待)?候补(?:人数|的人|人)?"
        r"(?:最多|最高|排行(?:榜)?|排名|分布)?(?:的?区间)?"
        r"(?:(?:这个|那个|该|对应|同一)?区间(?:的)?(?:二等座(?:余票|还剩多少(?:张)?|还有多少(?:张)?)"
        r"|(?:还有|还剩)多少(?:张)?二等座(?:余票|票)?))?"
        r"|候补区间(?:排行(?:榜)?|排名)"),
    "orders": Report(
        "订单状态分布",
        "按当前订单状态统计，按订单号去重；一笔多人订单计一笔，包含模拟乘客订单。",
        "order_status, COUNT(DISTINCT order_id) AS orders FROM v_ops_orders",
        "GROUP BY order_status ORDER BY orders DESC, order_status",
        (("order_status", "订单状态"), ("orders", "订单数")),
        r"(?:各(?:个|种)?状态|按状态)订单(?:分别)?(?:有多少(?:笔)?|分布|数量|统计)"
        r"|订单(?:按|各)?状态(?:分别)?(?:分布|统计|各?有多少笔|数量)"),
    "paid": Report(
        "已支付订单数",
        "仅统计当前状态为 PAID 的订单，按订单号去重；已退款订单不计入，包含模拟乘客订单。",
        "COUNT(DISTINCT order_id) AS paid_orders FROM v_ops_orders",
        "AND order_status = 'PAID'",
        (("paid_orders", "已支付订单数"),),
        r"(?:当前)?(?:有多少(?:笔)?|共有多少(?:笔)?)?已支付(?:的)?订单(?:数(?:量)?|有多少(?:笔)?|共多少笔)?"
        r"|已支付(?:了)?多少(?:笔)?订单"),
    "buffer": Report(
        "缓冲请求状态分布",
        "按订票缓冲表中的当前请求状态计数，每条持久化请求计一条；重试次数不另计。",
        "request_status, SUM(requests) AS request_count FROM v_ops_buffer",
        "GROUP BY request_status ORDER BY request_count DESC, request_status",
        (("request_status", "缓冲状态"), ("request_count", "请求数")),
        r"(?:订票|购票|订单)?缓冲(?:区)?(?:中)?(?:的)?(?:请求)?(?:按|各)?状态(?:分别)?"
        r"(?:分布|统计|有多少(?:条|个)?(?:请求)?|数量)"),
}


class Clarify(ValueError):
    pass


def parse_scope(question, service_date):
    text = unicodedata.normalize("NFKC", question).strip()
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    trains = re.findall(r"(?<![A-Za-z0-9])[GCDZTKYS]\d{1,5}(?![A-Za-z0-9])", text, re.I)
    if len(set(dates)) > 1 or len({t.upper() for t in trains}) > 1:
        raise Clarify("请每次查询一个运营日，可指定一个车次或查看全部车次。")
    if re.search(r"今天|今日|昨天|昨日|明天|近\d|本周|本月|\d+月\d+|下单日|支付日|创建日", text):
        raise Clarify("这里按列车运营日统计，请选择日期或写明 YYYY-MM-DD 格式的运营日。")
    day = dates[0] if dates else service_date
    try:
        if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
            raise ValueError
        date.fromisoformat(day)
    except ValueError:
        raise Clarify("请选择有效的运营日期。") from None
    for token in dates + trains:
        text = text.replace(token, "")
    top = re.search(r"(?:前\s*|top\s*)(\d+)\s*(?:名|个|段|条|项)?", text, re.I)
    limit = int(top[1]) if top else (1 if re.search(r"哪个|哪段|哪一段|最多的区间", text) else 10)
    if not 1 <= limit <= 20:
        raise Clarify("区间排行每次可查看前 1 至 20 项。")
    if top:
        text = text[:top.start()] + text[top.end():]
    text = re.sub(r"[\s,。?？、，:：]", "", text)
    text = re.sub(r"^(?:请问|请查询|请查|查询|查看|统计一下|看看|请|运营日|全网|全部车次|车次|现在|当前|的)+", "", text)
    return day, trains[0].upper() if trains else None, limit, text, bool(top)


def query_for(report, train, limit):
    sql = f"SELECT {report.select}\nWHERE service_date = %s"
    if train:
        sql += " AND train_no = %s"
    return f"{sql}\n{report.tail}\nLIMIT {limit}"


def select_report(question, candidates, known, day):
    key = os.getenv("CR12306_AI_API_KEY")
    mode = "本地 NL2SQL 规则"
    if key:
        catalog = "\n\n".join(f"{REPORTS[k].title}。{REPORTS[k].definition}\n{sql}" for k, sql in candidates.items())
        prompt = ("将运营问题翻译为单条 MySQL SELECT。仅支持以下指标和 SQL 形式。"
                  f"页面已选择运营日 {day}，问题中明确的日期也已由后端处理。"
                  "车次和日期均由后端提取并绑定，SQL保持%s占位符，日期已确定，无需追问日期。"
                  "保留 %s 绑定参数、列、分组、排序、LIMIT。不得丢弃条件或回答其他问题。"
                  "若口径不清、包含无法支持的筛选或指标，sql 留空，clarify 给出中文说明。\n" + catalog)
        schema = {"name": "query_operations", "description": "生成只读报表 SQL 或提出澄清",
                  "parameters": {"type": "object", "properties": {"sql": {"type": "string"}, "clarify": {"type": "string"}},
                                 "required": ["sql", "clarify"], "additionalProperties": False}}
        try:
            reply = call_tool(question, key, prompt, schema)
            if not isinstance(reply, dict) or not isinstance(reply.get("sql"), str) or not isinstance(reply.get("clarify"), str):
                raise ValueError("invalid result")
            if reply["clarify"]:
                return None, "模型 NL2SQL", reply["clarify"][:200]
            normalized = " ".join(reply["sql"].strip().removesuffix(";").split()).casefold()
            for k, sql in candidates.items():
                if normalized == " ".join(sql.split()).casefold() and (known is None or k == known):
                    return k, "模型 NL2SQL", ""
            mode = "本地 NL2SQL 规则（模型 SQL 未通过校验）"
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            mode = "本地 NL2SQL 规则（模型接口暂不可用）"
    return known, mode, "" if known else "当前支持候补区间排行、订单状态分布、已支付订单数和缓冲请求状态分布。请明确一个指标，可指定车次。"


STATUS_NAMES = {"PAID": "已支付", "REFUNDED": "已退款", "PENDING_PAYMENT": "待支付", "CANCELLED": "已取消",
                "TIMEOUT": "已超时", "QUEUED": "排队中", "PROCESSING": "处理中", "SUCCEEDED": "已成功", "FAILED": "已失败"}


def operations_answer(question, service_date, read_rows):
    try:
        day, train, limit, text, top = parse_scope(question, service_date)
    except Clarify as exc:
        return {"clarify": str(exc)}
    candidates = {k: query_for(r, train, limit if k == "waiting" else 20)
                  for k, r in REPORTS.items() if not top or k == "waiting"}
    known = next((k for k in candidates if re.fullmatch(REPORTS[k].pattern, text)), None)
    metric, mode, clarification = select_report(question, candidates, known, day)
    if not metric:
        return {"clarify": clarification, "mode": mode}
    report = REPORTS[metric]
    params = [day, train] if train else [day]
    sql = candidates[metric]
    rows = read_rows(sql, params)
    scope = f"运营日 {day} · {train or '全部车次'}"
    if not rows:
        answer = "该范围内没有正在排队或匹配的候补请求。" if metric == "waiting" else "该范围内没有符合统计口径的记录。"
    elif metric == "waiting":
        first = rows[0]
        seats = first["second_seats"]
        stock = "该区间没有在售二等座产品" if seats is None else f"该区间二等座余 {seats} 张"
        answer = f"候补人数最多的区间为 {first['train_no']} {first['origin']} → {first['destination']}，共 {first['waiting_people']} 人。{stock}。"
    elif metric == "paid":
        answer = f"当前已支付订单共 {rows[0]['paid_orders']} 笔。"
    else:
        status, count = [c[0] for c in report.columns]
        unit = "笔" if metric == "orders" else "条"
        answer = "，".join(f"{STATUS_NAMES.get(r[status], r[status])} {r[count]} {unit}" for r in rows) + "。"
    return {"mode": mode, "scope": scope, "title": report.title, "answer": answer, "definition": report.definition,
            "columns": report.columns, "rows": rows, "sql": sql, "params": params,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
