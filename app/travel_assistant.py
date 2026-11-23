"""Passenger intent extraction and read-only itinerary planning."""

import os
import re
from datetime import datetime
from decimal import Decimal
from math import ceil
from urllib.error import URLError
from model_api import call_tool


DEMO_DATE = "2026-10-14"
NUMBER = r"(?:\d+|[零一二两三四五六七八九十]+)"
EXAMPLE = "两个人从南通西到上海虹桥，09:00到14:00出发，人均预算150元，下午3点前到，可以换乘一次"
CLOCK = rf"(?:凌晨|上午|早上|下午|晚上|中午)?{NUMBER}(?:[:：]\d{{2}}|[点时](?:半|\d{{1,2}}分?)?)"
CLOCK_FORMAT = r"(?:[01]\d|2[0-3]):[0-5]\d"
TRAIN_NO = r"(?:[A-Z][0-9]{1,5}|[0-9]{1,6})"
FARE = r"[0-9]{1,6}(?:\.[0-9]{1,2})?"
TRAIN_PREFIXES = {"high_speed": ("G", "C"), "emu": ("D",)}
TRAIN_LABELS = {"high_speed": "仅 G/C 字头", "emu": "仅 D 字头"}
EXTRA_FIELDS = ("depart_after", "depart_before", "max_fare", "max_group_fare",
                "train_no", "train_category", "max_duration_minutes")


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


def clock_value(token, period=""):
    match = re.fullmatch(rf"(凌晨|上午|早上|下午|晚上|中午)?({NUMBER})(?:[:：](\d{{2}})|[点时](半|\d{{1,2}}分?)?)", token)
    hour = number(match[2])
    minute = match[3] or match[4] or "0"
    period = match[1] or period
    if period in ("下午", "晚上") and hour < 12:
        hour += 12
    elif period == "中午" and hour <= 2:
        hour += 12
    elif period == "凌晨" and hour == 12:
        hour = 0
    return f"{hour:02}:{30 if minute == '半' else int(minute.rstrip('分')):02}"


def extract_extra_conditions(text, intent):
    window = re.search(rf"(?:出发(?:时间)?(?:在)?)?({CLOCK})(?:到|至|[-~～—])({CLOCK})(?:之间)?(?:出发|发车)", text)
    if window is None:
        window = re.search(rf"出发(?:时间)?(?:在)?({CLOCK})(?:到|至|[-~～—])({CLOCK})(?:之间)?", text)
    if window:
        start, end = window.groups()
        period = re.match(r"下午|晚上", start)
        intent["depart_after"] = clock_value(start)
        intent["depart_before"] = clock_value(end, period[0] if period else "")
        text = text.replace(window[0], "，", 1)
    for field, terms in (("depart_after", "以后|之后|后"), ("depart_before", "以前|之前|前")):
        bound = re.search(rf"({CLOCK})(?:{terms})(?:出发|发车)|(?:出发|发车)(?:时间)?(?:在)?({CLOCK})(?:{terms})", text)
        if bound:
            if intent[field]:
                raise TravelQuestion("请明确一个出发时间范围。")
            intent[field] = clock_value(bound[1] or bound[2])
            text = text.replace(bound[0], "，", 1)

    for field, scope in (("max_group_fare", r"总预算|总价|合计|一共|所有人预算"),
                         ("max_fare", r"人均(?:预算|票价)?|每人(?:预算|票价)?|单人预算|预算|票价")):
        fare = re.search(rf"(?:{scope})(?:控制在|不超过|最多|至多|在)?(?:[¥￥])?({FARE})(?:元|块)?(?:以内|以下)?", text)
        if fare:
            intent[field] = fare[1]
            text = text.replace(fare[0], "，", 1)

    train = re.search(rf"(?:首段(?:指定|只坐|坐)?|指定(?:车次)?|只坐|坐|车次)({TRAIN_NO})(?:次)?|([A-Z][0-9]{{1,5}})(?:次)?", text, re.I)
    if train:
        intent["train_no"] = (train[1] or train[2]).upper()
        text = text.replace(train[0], "，", 1)
    category = re.search(r"(?:只坐|只要|仅限|只看|仅坐)(G/C字头|高铁|D字头|动车)", text, re.I)
    if category:
        intent["train_category"] = "high_speed" if category[1].upper() in ("高铁", "G/C字头") else "emu"
        text = text.replace(category[0], "，", 1)

    duration = re.search(rf"(?:全程(?:耗时)?|耗时|用时|车程)(?:不超过|最多|至多|控制在)"
                         rf"(?:({NUMBER})(?:小时|钟头)(?:({NUMBER})分钟)?|({NUMBER})分钟)(?:以内)?", text)
    if duration:
        hours, minutes, standalone = duration.groups()
        intent["max_duration_minutes"] = str(number(standalone) if standalone else
                                             60 * number(hours) + (number(minutes) if minutes else 0))
        text = text.replace(duration[0], "，", 1)
    return text


def local_intent(question, locations):
    """Accept supported Chinese phrases; ask for edits on unparsed constraints."""
    text = re.sub(r"\s", "", question)
    names = {s["station_name"] for s in locations} | {s["city"] for s in locations if s["city"]}
    places = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
    route = re.search(rf"({places})([站市]?)(?:出发)?(?:前往|出发去|到|去|至|→)({places})([站市]?)", text)
    if not route:
        raise TravelQuestion("请写出出发地和目的地，例如“从南通西到上海虹桥”。")
    start, end = route[1] + route[2], route[3] + route[4]
    text = text[:route.start()] + "，" + text[route.end():]
    intent = dict(origin=start, destination=end, date=DEMO_DATE, people=1, arrive_by="",
                  seat="", transfer="direct", sort="arrival", clarify="", **dict.fromkeys(EXTRA_FIELDS, ""))

    date_match = re.search(r"(?:(\d{4})[年/-])?(\d{1,2})[月/-](\d{1,2})[日号]?", text)
    if date_match:
        intent["date"] = f"{date_match[1] or '2026'}-{int(date_match[2]):02}-{int(date_match[3]):02}"
        text = text.replace(date_match[0], "，", 1)
    count = re.search(rf"({NUMBER})(?:个人|位乘客|位|人|张票|张)", text)
    if count:
        intent["people"] = number(count[1])
        text = text.replace(count[0], "，", 1)
    text = extract_extra_conditions(text, intent)
    deadline = re.search(rf"({CLOCK})(?:之?前|以前)(?:抵达|到达|到)?", text)
    if deadline:
        intent["arrive_by"] = clock_value(deadline[1])
        text = text.replace(deadline[0], "，", 1)
    seat = re.search(r"商务座|一等座|二等座|硬座|软座|硬卧|软卧|无座", text)
    if seat:
        intent["seat"] = seat[0]
        text = text.replace(seat[0], "，", 1)
    if re.search("便宜|省钱|低价", text):
        intent["sort"] = "price"
    elif re.search("用时最短|耗时最短|全程最快|车程最短|最快", text):
        intent["sort"] = "duration"
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
              r"用时最短|耗时最短|全程最快|车程最短|最快|最便宜|便宜|省钱|低价|最早到达|最早到|怎么走|怎么坐|我该怎么买|怎么买|"
              r"帮我查一下|帮我查|请问|请|我们|我想|我要|我|从|买票|车票|的|也|就|再|才|先")
    if re.sub(filler + r"|[，。！？、；,!?;]", "", text):
        raise TravelQuestion("有些条件未能识别。请用明确时间、金额或车次表达，例如“" + EXAMPLE + "”。")
    return intent


FIELDS = {
    "origin": {"type": "string"}, "destination": {"type": "string"},
    "date": {"type": "string"}, "people": {"type": "integer"},
    "arrive_by": {"type": "string"}, "seat": {"type": "string"},
    "transfer": {"type": "string", "enum": ["direct", "allowed", "fallback"]},
    "sort": {"type": "string", "enum": ["arrival", "price", "duration"]},
    "depart_after": {"type": "string", "description": "最早出发时间 HH:MM"},
    "depart_before": {"type": "string", "description": "最晚出发时间 HH:MM"},
    "max_fare": {"type": "string", "description": "每人全程票价上限，单位元"},
    "max_group_fare": {"type": "string", "description": "所有乘客全程票价合计上限，单位元"},
    "train_no": {"type": "string", "description": "指定车次，换乘时用于首段"},
    "train_category": {"type": "string", "enum": ["", "high_speed", "emu"]},
    "max_duration_minutes": {"type": "string", "description": "含换乘等待的全程分钟数上限，整数"},
    "clarify": {"type": "string"},
}


def model_intent(question, key):
    prompt = (
        f"提取铁路购票条件。默认日期 {DEMO_DATE}、1人、优先直达。保留地名及站/市后缀。"
        "date 为 YYYY-MM-DD。transfer 默认 direct（仅直达）。允许或最多换乘1次用 allowed，"
        "即使提到优先直达也要查换乘；明确说没有合适直达才换乘时用 fallback。"
        "超过1次的换乘需求用 clarify 提示目前最多支持1次。"
        "arrive_by 是同一乘车日最晚到达的 HH:MM。seat 是请求的席别。未指定的可选字符串为空。"
        "depart_after、depart_before 是同一乘车日首段出发时间的上下限，格式 HH:MM。"
        "max_fare 是一人的全程票价上限，未写明总价的预算按一人计。"
        "明确说全部乘客合计时用 max_group_fare。金额只返回数字字符串，最多两位小数。"
        "指定一个车次用 train_no，换乘时只支持限定首段车次。只坐高铁用 high_speed（G/C），"
        "只坐动车用 emu（D），车型约束应用于所有段。max_duration_minutes 是含等车时间的整数分钟上限，返回数字字符串。"
        "价格优先用 price，用时最短用 duration，其他用 arrival。不要编造地点或票务信息。"
        "缺起终点、相对日期不明或有无法表达的硬条件（如连座、指定换乘站、指定第二段车次或优先而非限定某车型）时，"
        "在 clarify 写简短中文追问，不要忽略条件。"
    )
    schema = {"name": "plan_trip", "description": "解析条件后由服务端查询演示车票",
              "parameters": {"type": "object", "properties": FIELDS,
                             "required": list(FIELDS), "additionalProperties": False}}
    return call_tool(question, key, prompt, schema)


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
    if isinstance(intent, dict):
        for field in EXTRA_FIELDS:
            intent.setdefault(field, "")
    if not isinstance(intent, dict) or any(not isinstance(intent.get(k), str)
            for k in FIELDS if k != "people"):
        raise ValueError("invalid tool arguments")
    if type(intent.get("people")) is not int or any(intent[k] not in FIELDS[k]["enum"] for k in ("transfer", "sort", "train_category")):
        raise ValueError("invalid tool arguments")
    if intent["clarify"]:
        raise TravelQuestion(intent["clarify"][:240])
    if not intent["origin"] or not intent["destination"]:
        raise TravelQuestion("请补充出发地和目的地。")
    if intent["date"] != DEMO_DATE:
        raise TravelQuestion(f"本项目目前仅提供 {DEMO_DATE} 的演示班次，请修改乘车日期。")
    if not 1 <= intent["people"] <= 5:
        raise TravelQuestion("每次可查询 1 至 5 人，请修改人数。")
    for field in ("arrive_by", "depart_after", "depart_before"):
        if intent[field] and not re.fullmatch(CLOCK_FORMAT, intent[field]):
            raise TravelQuestion("请用有效的 24 小时时间，例如 09:00 后出发、15:30 前到。")
    after, before, arrive = (intent[k] for k in ("depart_after", "depart_before", "arrive_by"))
    if after and ((before and after > before) or (arrive and after > arrive)):
        raise TravelQuestion("最早出发时间须早于或等于最晚出发、到达时间。")
    for field in ("max_fare", "max_group_fare"):
        if intent[field] and (not re.fullmatch(FARE, intent[field]) or Decimal(intent[field]) <= 0):
            raise TravelQuestion("请填写大于 0 的预算金额，最多保留两位小数。")
    if intent["train_no"]:
        intent["train_no"] = intent["train_no"].upper()
        if not re.fullmatch(TRAIN_NO, intent["train_no"]):
            raise TravelQuestion("请填写一个完整的车次号，例如 G8359。")
        prefixes = TRAIN_PREFIXES.get(intent["train_category"])
        if prefixes and not intent["train_no"].startswith(prefixes):
            raise TravelQuestion("指定车次和车型条件冲突，请修改其中一项。")
    duration = intent["max_duration_minutes"]
    if duration and (not re.fullmatch(r"[0-9]{1,5}", duration) or int(duration) <= 0):
        raise TravelQuestion("请填写大于 0 的全程耗时上限，例如全程不超过 2 小时。")


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
    after, before = intent["depart_after"], intent["depart_before"]
    fare_limit = Decimal(intent["max_fare"]) if intent["max_fare"] else None
    group_limit = Decimal(intent["max_group_fare"]) if intent["max_group_fare"] else None
    prefixes = TRAIN_PREFIXES.get(intent["train_category"])
    train_no = intent["train_no"]
    max_duration = int(intent["max_duration_minutes"] or 0)
    day_start = f"{date} 00:00"

    def trip_metrics(legs):
        departure = str(legs[0]["departure_at"]).replace("T", " ")
        arrival = str(legs[-1]["arrival_at"]).replace("T", " ")
        if (after or before) and not f"{date} {after or '00:00'}" <= departure[:16] <= f"{date} {before or '23:59'}":
            return None
        if deadline and not day_start <= arrival[:16] <= f"{date} {deadline}":
            return None
        if train_no and legs[0]["train_no"].upper() != train_no:
            return None
        if any((intent["seat"] and leg["seat_type_name"] != intent["seat"]) or
               (prefixes and not leg["train_no"].upper().startswith(prefixes)) for leg in legs):
            return None
        duration = ceil((datetime.fromisoformat(arrival) - datetime.fromisoformat(departure)).total_seconds() / 60)
        if max_duration and duration > max_duration:
            return None
        price = sum(Decimal(str(leg["amount"])) for leg in legs)
        if (fare_limit is not None and price > fare_limit) or (group_limit is not None and price * people > group_limit):
            return None
        return price, duration

    def add(legs, minutes=0):
        metrics = trip_metrics(legs)
        if metrics and all(int(leg["available_seats"]) >= people for leg in legs):
            price, duration = metrics
            options.append({"legs": legs, "price": str(price), "group_price": str(price * people),
                            "transfer_minutes": minutes, "duration_minutes": duration})

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
        stocks = [int(row["available_seats"]) for row in rows if trip_metrics([row])]
        if stocks and max(stocks) < people:
            reason = f"符合其他筛选条件的直达班次，同一席别最多余 {max(stocks)} 张，本次需要 {people} 张。"
    policy = intent["transfer"]
    if policy == "allowed" or (policy == "fallback" and not has_direct):
        pairs = transfer_search({**base, "from": [s["station_id"] for s in starts],
                                 "to": [s["station_id"] for s in ends], "arriveBy": [deadline],
                                 "departAfter": [after], "departBefore": [before], "trainNo": [train_no],
                                 "trainCategory": [intent["train_category"]], "maxDuration": [intent["max_duration_minutes"]],
                                 "sort": [intent["sort"]]})
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
    sort = intent["sort"]
    def rank(option):
        arrival, fare = option["legs"][-1]["arrival_at"], Decimal(option["price"])
        if sort == "duration":
            return (option["duration_minutes"], arrival, fare)
        return (fare, arrival) if sort == "price" else (arrival, fare)
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
    if after or before:
        departure_label = f"{after}–{before}" if after and before else (f"{after} 后" if after else f"{before} 前")
        summary += f" · {departure_label}出发"
    if fare_limit is not None:
        summary += f" · 人均不超过 ¥{fare_limit}"
    if group_limit is not None:
        summary += f" · 合计不超过 ¥{group_limit}"
    if train_no:
        summary += f" · {'首段 ' if policy != 'direct' else ''}{train_no}"
    if prefixes:
        summary += " · " + TRAIN_LABELS[intent["train_category"]]
    if max_duration:
        summary += f" · 全程不超过 {max_duration} 分钟"
    ranking = {"price": "各类方案按票价排序", "arrival": "各类方案按到达时间排序", "duration": "各类方案按全程用时排序"}
    return {"mode": mode, "summary": summary, "people": people, "date": date,
            "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "answer": reason,
            "ranking": ranking[sort],
            "options": [*best[1].values(), *best[2].values()]}
