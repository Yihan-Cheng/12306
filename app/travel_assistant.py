"""Passenger intent extraction and read-only itinerary planning."""

import json
import os
import re
from datetime import datetime
from decimal import Decimal
from urllib.error import URLError
from urllib.request import Request, urlopen


DEMO_DATE = "2026-10-14"
NUMBER = r"(?:\d+|[零一二两三四五六七八九十]+)"
EXAMPLE = "两个人从南通西到上海虹桥，下午3点前到，优先直达，可以换乘一次"


class TravelQuestion(ValueError):
    """A constraint needs clarification before searching."""


def number(token):
    if token.isdecimal():
        return int(token)
    digits = "零一二三四五六七八九"
    token = token.replace("两", "二")
    if "十" in token:
        tens, _, ones = token.partition("十")
        if len(tens) <= 1 and len(ones) <= 1 and "十" not in ones:
            return (digits.index(tens) if tens else 1) * 10 + (digits.index(ones) if ones else 0)
    if len(token) == 1 and token in digits:
        return digits.index(token)
    raise TravelQuestion("请用阿拉伯数字填写人数和时间。")


def local_intent(question, locations):
    """Accept supported Chinese phrases; ask for edits on unparsed constraints."""
    text = re.sub(r"[\s，。！？、；,!?;]", "", question)
    names = {s["station_name"] for s in locations} | {s["city"] for s in locations if s["city"]}
    places = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
    route = re.search(rf"({places})([站市]?)(?:出发)?(?:前往|出发去|到|去|至|→)({places})([站市]?)", text)
    if not route:
        raise TravelQuestion("请写出出发地和目的地，例如“从南通西到上海虹桥”。")
    start, end = route[1] + route[2], route[3] + route[4]
    text = text[:route.start()] + text[route.end():]
    intent = dict(origin=start, destination=end, date=DEMO_DATE, people=1, arrive_by="",
                  seat="", transfer="direct", sort="arrival", clarify="")

    date_match = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})[月/-](\d{1,2})[日号]?", text)
    if date_match:
        intent["date"] = f"{date_match[1] or '2026'}-{int(date_match[2]):02}-{int(date_match[3]):02}"
        text = text.replace(date_match[0], "", 1)
    count = re.search(rf"({NUMBER})(?:个人|位乘客|位|人|张票|张)", text)
    if count:
        intent["people"] = number(count[1])
        text = text.replace(count[0], "", 1)
    deadline = re.search(rf"(上午|早上|下午|晚上|中午)?({NUMBER})(?:[:：](\d{{2}})|[点时](半|\d{{1,2}}分?)?)(?:之?前|以前)(?:抵达|到达|到)?", text)
    if deadline:
        hour = number(deadline[2])
        minute = deadline[3] or deadline[4] or "0"
        if deadline[1] in ("下午", "晚上", "中午") and hour < 12:
            hour += 12
        intent["arrive_by"] = f"{hour:02}:{30 if minute == '半' else int(minute.rstrip('分')):02}"
        text = text.replace(deadline[0], "", 1)
    seat = re.search(r"商务座|一等座|二等座|硬座|软座|硬卧|软卧|无座", text)
    if seat:
        intent["seat"] = seat[0]
        text = text.replace(seat[0], "", 1)
    if re.search("便宜|省钱|低价", text):
        intent["sort"] = "price"
    # Consume negations before positive transfer phrases.
    text = text.replace("能不能", "可以").replace("可不可以", "可以")
    text = re.sub(r"(?:不想|不要|不能|不接受|不)(?:中转|换乘)|(?:只要|仅限|只坐|只看|只)(?:直达)", "", text)
    # Match the requested ceiling before consuming the generic word “换乘”.
    def transfer_count(match):
        count = number(match[1])
        if count > 1:
            raise TravelQuestion("目前可查直达或最多换乘 1 次，请修改换乘次数。")
        return "换乘" if count else "直达"

    text = re.sub(rf"(?:最多|至多|不超过)?(?:换乘|中转)(?:最多|至多|不超过)?({NUMBER})次", transfer_count, text)
    text = re.sub(rf"(?:最多|至多|不超过)?({NUMBER})次(?:换乘|中转)", transfer_count, text)
    if re.search(r"换乘|中转", text):
        conditional = re.search(r"(?:没有|没票|无票|不行|否则).*?(?:换乘|中转)", text)
        intent["transfer"] = "fallback" if conditional else "allowed"
    filler = (r"没有(?:合适的?)?(?:直达|足够|两张|票)?(?:票)?(?:的话)?|如果|没票|无票|不行|否则|再看看|看看|"
              r"能不能|可不可以|可以|允许|接受|一次|换乘|中转|直达|优先|首选|尽量|"
              r"最便宜|便宜|省钱|低价|最早到达|最早到|怎么走|怎么坐|我该怎么买|怎么买|"
              r"帮我查一下|帮我查|请问|请|我们|我想|我要|我|从|买票|车票|的|也|就|再|才|先")
    if re.sub(filler, "", text):
        raise TravelQuestion("本地模式可识别起终点、人数、席别、最晚到达时间和一次换乘。请改写问题，例如“" + EXAMPLE + "”。")
    return intent


FIELDS = {
    "origin": {"type": "string"}, "destination": {"type": "string"},
    "date": {"type": "string"}, "people": {"type": "integer"},
    "arrive_by": {"type": "string"}, "seat": {"type": "string"},
    "transfer": {"type": "string", "enum": ["direct", "allowed", "fallback"]},
    "sort": {"type": "string", "enum": ["arrival", "price"]},
    "clarify": {"type": "string"},
}


def model_intent(question, key):
    base = os.getenv("CR12306_AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    prompt = (
        f"提取铁路购票条件。默认日期 {DEMO_DATE}、1人、优先直达。保留地名及站/市后缀。"
        "date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，"
        "即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。"
        "超过1次的换乘需求用 clarify 提示目前最多支持1次。"
        "arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。"
        "价格优先用 price，其他用 arrival。不要编造地点或票务信息。"
        "缺起终点、相对日期不明或有无法表达的硬条件（如出发时间、预算、指定车次）时，"
        "在 clarify 写简短中文追问，不要忽略条件。"
    )
    schema = {"name": "plan_trip", "description": "解析条件后由服务端查询演示车票",
              "parameters": {"type": "object", "properties": FIELDS,
                             "required": list(FIELDS), "additionalProperties": False}}
    payload = {"model": os.getenv("CR12306_AI_MODEL", "gpt-4o-mini"),
               "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": question}],
               "tools": [{"type": "function", "function": schema}],
               "tool_choice": {"type": "function", "function": {"name": "plan_trip"}}}
    request = Request(base + "/chat/completions", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + key})
    with urlopen(request, timeout=15) as response:
        call = json.load(response)["choices"][0]["message"]["tool_calls"][0]["function"]
    if call["name"] != "plan_trip":
        raise ValueError("unexpected tool")
    return json.loads(call["arguments"])


def resolve(name, locations):
    # A bare 上海 means the city; 上海站 means that specific station.
    if not name.endswith("站"):
        city = name.removesuffix("市")
        stations = [s for s in locations if s["city"] == city]
        if stations:
            return city, None, stations
    stations = [s for s in locations if s["station_name"] == name.removesuffix("站")]
    if len(stations) != 1:
        raise TravelQuestion(f"请在车站列表中确认“{name}”的完整名称。")
    return stations[0]["city"], stations[0]["station_id"], stations


def validate(intent):
    if not isinstance(intent, dict) or any(not isinstance(intent.get(k), str)
            for k in FIELDS if k != "people"):
        raise ValueError("invalid tool arguments")
    if type(intent.get("people")) is not int or intent["transfer"] not in FIELDS["transfer"]["enum"] or intent["sort"] not in ("arrival", "price"):
        raise ValueError("invalid tool arguments")
    if intent["clarify"]:
        raise TravelQuestion(intent["clarify"][:240])
    if not intent["origin"] or not intent["destination"]:
        raise TravelQuestion("请补充出发地和目的地。")
    if intent["date"] != DEMO_DATE:
        raise TravelQuestion(f"本项目目前仅提供 {DEMO_DATE} 的演示班次，请修改乘车日期。")
    if not 1 <= intent["people"] <= 5:
        raise TravelQuestion("每次可查询 1 至 5 人，请修改人数。")
    if intent["arrive_by"] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", intent["arrive_by"]):
        raise TravelQuestion("请用 24 小时制写明最晚到达时间，例如 15:30 前到。")


def plan_trip(question, locations, direct_search, transfer_search):
    key = os.getenv("CR12306_AI_API_KEY")
    mode = "模型 API" if key else "本地规则"
    if key:
        try:
            intent = model_intent(question, key)
            validate(intent)
        except TravelQuestion as exc:
            return {"mode": mode, "answer": str(exc), "options": []}
        except (URLError, OSError, KeyError, ValueError, TypeError, IndexError):
            mode = "本地规则（模型 API 暂不可用）"
    try:
        if mode != "模型 API":
            intent = local_intent(question, locations)
            validate(intent)
        return search_plan(intent, locations, direct_search, transfer_search, mode)
    except TravelQuestion as exc:
        return {"mode": mode, "answer": str(exc), "options": []}


def search_plan(intent, locations, direct_search, transfer_search, mode):
    origin, dest = intent["origin"], intent["destination"]
    fc, fs, starts = resolve(origin, locations)
    tc, ts, ends = resolve(dest, locations)
    if (fc, fs) == (tc, ts):
        raise TravelQuestion("出发地和目的地相同，请写明不同的车站。")
    people, date = intent["people"], intent["date"]
    base = {"date": [date], "passengers": [str(people)]}
    rows = direct_search(dict(base, fromCity=[fc], toCity=[tc], fromStation=[fs], toStation=[ts]))
    options = []
    deadline = intent["arrive_by"]

    def within_constraints(legs):
        arrival = str(legs[-1]["arrival_at"]).replace("T", " ")[:16]
        return (not deadline or arrival <= f"{date} {deadline}") and all(
            not intent["seat"] or leg["seat_type_name"] == intent["seat"] for leg in legs)

    def add(legs, minutes=0):
        if within_constraints(legs) and all(int(leg["available_seats"]) >= people for leg in legs):
            price = sum(Decimal(str(leg["amount"])) for leg in legs)
            options.append({"legs": legs, "price": str(price), "group_price": str(price * people),
                            "transfer_minutes": minutes})

    fields = ("train_no", "from_station_name", "to_station_name", "from_station_id", "to_station_id",
              "run_id", "departure_at", "arrival_at", "seat_type_id", "seat_type_name", "amount", "available_seats")
    # Retain only the public fields the result cards and booking handoff need.
    for row in rows:
        if int(row["can_fulfill"]):
            add([{k: row[k] for k in fields}])
    has_direct = bool(options)
    reason = "直达方案满足所选条件。"
    if not has_direct:
        reason = "当前查询未找到满足这些条件的直达票。"
        stocks = [int(row["available_seats"]) for row in rows if within_constraints([row])]
        if stocks and max(stocks) < people:
            reason = f"符合时刻和席别条件的直达班次，同一席别最多余 {max(stocks)} 张，本次需要 {people} 张。"
    policy = intent["transfer"]
    if policy == "allowed" or (policy == "fallback" and not has_direct):
        pairs = transfer_search({**base, "from": [s["station_id"] for s in starts],
                                 "to": [s["station_id"] for s in ends], "arriveBy": [deadline]})
        names = {int(s["station_id"]): s["station_name"] for s in locations}
        for row in pairs:
            if not int(row["can_fulfill"]):
                continue
            start, via, end = (int(row[k]) for k in ("origin_id", "transfer_station_id", "destination_id"))
            legs = []
            for prefix, a, b in (("first", start, via), ("second", via, end)):
                leg = {k: row[f"{prefix}_{k}"] for k in fields if k not in
                       ("from_station_name", "to_station_name", "from_station_id", "to_station_id")}
                leg.update(from_station_name=names[a], to_station_name=names[b], from_station_id=a, to_station_id=b)
                legs.append(leg)
            add(legs, int(row["transfer_minutes"]))
        reason += ("已找到两段余票均足够的一次换乘方案。" if any(len(o["legs"]) == 2 for o in options)
                   else "已查一次同站换乘，当前候选未满足条件。")
    by_price = intent["sort"] == "price"
    def rank(option):
        arrival, fare = option["legs"][-1]["arrival_at"], Decimal(option["price"])
        return (fare, arrival) if by_price else (arrival, fare)
    options.sort(key=rank)
    # Show one bookable fare per itinerary before suggesting another train.
    best = {1: {}, 2: {}}
    for option in options:
        route = tuple((leg["run_id"], leg["from_station_id"], leg["to_station_id"]) for leg in option["legs"])
        group = best[len(route)]
        if len(group) < 3:
            group.setdefault(route, option)
    transfer_label = {"direct": "仅直达", "allowed": "最多换乘 1 次", "fallback": "无合适直达时换乘 1 次"}
    summary = f"{date} · {origin} → {dest} · {people} 人 · {transfer_label[policy]}"
    if intent["seat"]:
        summary += " · " + intent["seat"]
    if deadline:
        summary += f" · {deadline} 前到"
    return {"mode": mode, "summary": summary, "people": people, "date": date,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "answer": reason,
            "ranking": "各类方案按票价排序" if by_price else "各类方案按到达时间排序",
            "options": [*best[1].values(), *best[2].values()]}
