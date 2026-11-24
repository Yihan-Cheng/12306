"""Translate an operations question into a bounded plan over reporting views."""
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone

from model_api import call_tool


@dataclass(frozen=True)
class Dataset:
    view: str
    status: str
    statuses: dict[str, str]
    fields: tuple[str, ...]


@dataclass(frozen=True)
class Metric:
    dataset: str
    title: str
    expression: str
    columns: tuple[str, ...]
    definition: str
    unit: str
    statuses: tuple[str, ...] = ()


ROUTE_FIELDS = ("origin", "destination", "origin_city", "destination_city")
DATASETS = {
    "orders": Dataset("v_ops_analysis_orders", "order_status", {
        "PENDING_PAYMENT": "待支付", "PAID": "已支付", "CANCELLED": "已取消",
        "TIMEOUT": "已超时", "REFUNDING": "退款中", "REFUNDED": "已退款",
    }, (*ROUTE_FIELDS, "order_source", "customer_kind")),
    "waitlist": Dataset("v_ops_analysis_waitlist", "wait_status", {
        "WAITING": "排队中", "MATCHING": "匹配中", "MATCHED_HOLD": "已占座",
        "FULFILLED": "已兑现", "CANCELLED": "已取消", "EXPIRED": "已过期",
    }, (*ROUTE_FIELDS, "fairness_status")),
    "buffer": Dataset("v_ops_analysis_buffer", "request_status", {
        "QUEUED": "排队中", "PROCESSING": "处理中", "SUCCEEDED": "已成功",
        "FAILED": "已失败", "CANCELLED": "已取消",
    }, (*ROUTE_FIELDS, "attempt_band", "failure_category")),
    "inventory": Dataset("v_ops_analysis_inventory", "run_status", {
        "PLANNED": "计划中", "ON_SALE": "售票中", "STOP_SALE": "停售", "CANCELLED": "已取消", "FINISHED": "已结束",
    }, ("carriage_no",)),
}

ORDER_COUNT = "匹配条件的票项按订单号去重。按席别、区间或车次分组时，同一笔订单可出现在多组。"
METRICS = {
    "order_count": Metric("orders", "订单数", "COUNT(DISTINCT order_id)", ("order_id",), ORDER_COUNT, "笔"),
    "paid_orders": Metric("orders", "已支付订单数", "COUNT(DISTINCT order_id)", ("order_id",),
                         "仅统计当前为已支付状态的订单。" + ORDER_COUNT, "笔", ("PAID",)),
    "refunded_orders": Metric("orders", "已退款订单数", "COUNT(DISTINCT order_id)", ("order_id",),
                             "仅统计当前为已退款状态的订单。" + ORDER_COUNT, "笔", ("REFUNDED",)),
    "ticket_items": Metric("orders", "订单票项数", "COUNT(*)", ("order_item_id",),
                           "匹配条件的单人单程订单票项数。包含各状态，除非指定订单状态。", "项"),
    "ticket_value": Metric("orders", "票面金额合计", "COALESCE(SUM(price_snapshot), 0)", ("price_snapshot",),
                           "按匹配的单人单程票项汇总票价快照。实收、退款额需单独查询。", "元"),
    "waiting_people": Metric("waitlist", "排队候补人数", "COALESCE(SUM(passenger_count), 0)", ("passenger_count",),
                             "汇总当前排队或匹配中的候补请求人数。", "人", ("WAITING", "MATCHING")),
    "wait_requests": Metric("waitlist", "候补请求数", "COUNT(*)", (), "每个候补请求计一次。", "条"),
    "fulfilled_waits": Metric("waitlist", "已兑现候补数", "COUNT(*)", (), "仅统计当前已兑现的候补请求。", "条", ("FULFILLED",)),
    "wait_fulfillment_rate": Metric("waitlist", "候补兑现率",
                                    "ROUND(100.0 * SUM(wait_status = 'FULFILLED') / NULLIF(COUNT(*), 0), 2)",
                                    ("wait_status",), "筛选范围内当前已兑现请求数除以候补总请求数。", "%"),
    "wait_retries": Metric("waitlist", "候补重试次数", "COALESCE(SUM(retry_count), 0)", ("retry_count",),
                           "匹配的候补请求重试次数之和。", "次"),
    "wait_skips": Metric("waitlist", "候补跳过次数", "COALESCE(SUM(skip_count), 0)", ("skip_count",),
                         "匹配的候补请求跳过次数之和。", "次"),
    "buffer_requests": Metric("buffer", "缓冲请求数", "COUNT(*)", (), "每个持久化请求计一次，重试不重复计数。", "条"),
    "failed_requests": Metric("buffer", "失败缓冲请求数", "COUNT(*)", (), "每个当前失败的缓冲请求计一次。", "条", ("FAILED",)),
    "average_elapsed": Metric("buffer", "缓冲平均耗时", "ROUND(AVG(elapsed_ms), 1)", ("elapsed_ms",),
                              "仅汇总已结束的缓冲请求，从入队到结束，包含等待及处理时间。", "毫秒"),
    "buffer_failure_rate": Metric("buffer", "缓冲失败率",
                                   "ROUND(100.0 * SUM(request_status = 'FAILED') / "
                                   "NULLIF(SUM(request_status IN ('SUCCEEDED', 'FAILED')), 0), 2)",
                                   ("request_status",), "失败请求数除以成功与失败请求数之和。", "%"),
    "buffer_retried": Metric("buffer", "缓冲重试请求数", "COALESCE(SUM(attempt_band = 'RETRIED'), 0)", ("attempt_band",),
                             "被处理工作线程领取至少两次的请求数。", "条"),
    "inventory_seats": Metric("inventory", "运行座位数", "COUNT(*)", (), "当前有效编组中的运行座位数。", "席"),
    "inventory_free": Metric("inventory", "全程空闲座位数", "COALESCE(SUM(full_route_free), 0)", ("full_route_free",),
                             "占用位图为零的运行座位数。该指标衡量全程空闲，具体区间余票需单独查询。", "席"),
    "inventory_load": Metric("inventory", "有占用座位比例",
                             "ROUND(100.0 * SUM(full_route_free = 0) / NULLIF(COUNT(*), 0), 2)", ("full_route_free",),
                             "至少一个区段被占用的座位数除以运行座位总数。", "%"),
}

DIMENSIONS = {"service_date": "运营日", "train_no": "车次", "origin": "上车站",
              "destination": "下车站", "seat_type": "席别", "status": "当前状态",
              "origin_city": "出发城市", "destination_city": "到达城市", "train_type": "车型",
              "order_source": "订单来源", "customer_kind": "客群", "fairness_status": "公平保护",
              "attempt_band": "处理尝试", "failure_category": "失败分类", "carriage_no": "车厢"}
COMMON_FIELDS = ("service_date", "train_no", "seat_type", "train_type", "status")
VALUE_FILTERS = tuple(name for name in DIMENSIONS if name not in {"service_date", "train_no"})
FIELD_VALUES = {
    "order_source": {"WEB": "网页下单", "WAITLIST": "候补兑现"},
    "customer_kind": {"SIMULATED": "AI 订票员", "OTHER": "其他乘客"},
    "fairness_status": {"PROTECTED": "已进入公平保护", "UNPROTECTED": "未进入公平保护"},
    "attempt_band": {"UNCLAIMED": "未领取", "ONCE": "领取一次", "RETRIED": "领取多次"},
    "failure_category": {"NONE": "非失败", "INVENTORY": "余票不足", "CONFLICT": "库存并发冲突", "OTHER": "其他失败"},
}
ISO_DATE = r"\d{4}-\d{2}-\d{2}"
TRAIN_NO = r"(?<![A-Za-z0-9])[GCDZTKYS]\d{1,5}(?![A-Za-z0-9])"
RANGE_SEPARATOR = r"\s*(?:到|至|~|—|–)\s*"
MAX_ROWS = 50


class AnalysisInputError(ValueError):
    pass


@dataclass(frozen=True)
class Scope:
    days: tuple[str, ...]
    date_range: bool
    trains: tuple[str, ...]

    @property
    def label(self):
        dates = (" 至 " if self.date_range else "、").join(self.days)
        return f"运营日 {dates} · {'、'.join(self.trains) or '全部车次'}"


def analysis_scope(question, service_date):
    text = unicodedata.normalize("NFKC", question)
    days = tuple(dict.fromkeys(re.findall(ISO_DATE, text)))
    trains = tuple(dict.fromkeys(re.findall(TRAIN_NO, text.upper())))
    relative = (r"今天|今日|昨天|昨日|明天|近\s*[一二两三四五六七八九十几\d]|本周|上周|本月|上月"
                r"|\d+月\d+|\d{1,2}[-/]\d{1,2}|下单日|支付日|创建日")
    if re.search(relative, re.sub(ISO_DATE, "", text)):
        raise AnalysisInputError("请使用 YYYY-MM-DD 格式指定列车运营日，或使用页面选择的日期。")
    if len(days) > 2 or len(trains) > 8:
        raise AnalysisInputError("可比较两个运营日或查询连续日期范围，最多指定 8 个车次。")
    days = days or (service_date,)
    try:
        if any(not isinstance(day, str) or not re.fullmatch(ISO_DATE, day) for day in days):
            raise ValueError
        parsed = [date.fromisoformat(day) for day in days]
    except ValueError:
        raise AnalysisInputError("请选择有效的运营日期。") from None
    date_range = len(days) == 2 and re.search(ISO_DATE + RANGE_SEPARATOR + ISO_DATE, text) is not None
    if date_range and not 0 <= (parsed[1] - parsed[0]).days < 31:
        raise AnalysisInputError("日期范围须按先后顺序填写，最多包含 31 天。")
    return Scope(days, date_range, trains)


def dimension_columns(dataset):
    return {name: dataset.status if name == "status" else name for name in (*COMMON_FIELDS, *dataset.fields)}


def available_catalog(read_rows):
    views = tuple(dataset.view for dataset in DATASETS.values())
    placeholders = ", ".join(["%s"] * len(views))
    rows = read_rows("SELECT TABLE_NAME AS view_name, COLUMN_NAME AS column_name, DATA_TYPE AS data_type "
                     "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() "
                     f"AND TABLE_NAME IN ({placeholders}) ORDER BY TABLE_NAME, ORDINAL_POSITION", views)
    schema = {view: {} for view in views}
    for row in rows:
        schema[row["view_name"]][row["column_name"]] = row["data_type"]

    catalog = {}
    for dataset_key, dataset in DATASETS.items():
        actual_columns = schema[dataset.view]
        dimensions = {name: col for name, col in dimension_columns(dataset).items() if col in actual_columns}
        if not {"service_date", "train_no", "status"}.issubset(dimensions):
            continue
        metrics = {key: {"名称": metric.title, "口径": metric.definition}
                   for key, metric in METRICS.items()
                   if metric.dataset == dataset_key and set(metric.columns).issubset(actual_columns)}
        if metrics:
            catalog[dataset_key] = {"视图": dataset.view, "指标": metrics, "字段": {
                name: {"名称": DIMENSIONS[name], "数据库列": column, "类型": actual_columns[column]}
                for name, column in dimensions.items()}, "筛选枚举": {
                    "status": dataset.statuses, **{name: FIELD_VALUES[name] for name in dimensions if name in FIELD_VALUES}}}
    return catalog


def plan_tool(catalog):
    metrics = [metric for dataset in catalog.values() for metric in dataset["指标"]]
    available_fields = set().union(*(dataset["字段"] for dataset in catalog.values()))

    def enum(values):
        return {"type": "string", "enum": list(values)}

    def array(items):
        return {"type": "array", "items": items}

    properties = {"metric": enum(["", *metrics]), "group_by": array(enum(k for k in DIMENSIONS if k in available_fields)),
                  "filters": {"type": "object", "additionalProperties": False,
                              "properties": {name: array({"type": "string"}) for name in VALUE_FILTERS if name in available_fields}},
                  "sort": enum(["asc", "desc"]), "limit": {"type": "integer"}, "clarify": {"type": "string"}}
    return {"name": "plan_operations_query", "description": "返回运营查询计划或澄清问题",
            "parameters": {"type": "object", "properties": properties,
                           "required": list(properties), "additionalProperties": False}}


def validate_plan(plan, catalog):
    if not isinstance(plan, dict) or set(plan) != {"metric", "group_by", "filters", "sort", "limit", "clarify"}:
        raise ValueError("invalid plan")
    clarify = plan["clarify"]
    if not isinstance(clarify, str):
        raise ValueError("invalid clarification")
    if clarify.strip():
        raise AnalysisInputError(clarify.strip())
    key, groups, filters, sort, limit = (plan[k] for k in ("metric", "group_by", "filters", "sort", "limit"))
    if not isinstance(key, str) or key not in METRICS:
        raise ValueError("invalid metric")
    metric = METRICS[key]
    entry = catalog.get(metric.dataset, {})
    if key not in entry.get("指标", {}):
        raise ValueError("metric is absent in the database schema")
    if (not isinstance(groups, list) or len(groups) > 4
            or any(not isinstance(group, str) or group not in DIMENSIONS for group in groups)
            or len(set(groups)) != len(groups)):
        raise ValueError("invalid groups")
    for group in groups:
        if group not in entry["字段"]:
            raise AnalysisInputError(f"{DIMENSIONS[group]}不适用于该指标，或当前数据库尚未提供该字段。")
    if sort not in ("asc", "desc") or type(limit) is not int or not 1 <= limit <= MAX_ROWS:
        raise ValueError("invalid sort or limit")
    if not isinstance(filters, dict) or set(filters).difference(VALUE_FILTERS):
        raise ValueError("invalid filters")
    for name, values in filters.items():
        if (not isinstance(values, list) or len(values) > 8
                or any(not isinstance(v, str) or not 1 <= len(v.strip()) <= 60 for v in values)):
            raise ValueError("invalid filter values")
        if values and name not in entry["字段"]:
            raise AnalysisInputError(f"{DIMENSIONS[name]}不适用于该指标，或当前数据库尚未提供该字段。")
    filters = {name: tuple(dict.fromkeys(value.strip() for value in filters.get(name, []))) for name in VALUE_FILTERS}
    dataset = DATASETS[metric.dataset]
    for name, options in entry["筛选枚举"].items():
        if set(filters[name]).difference(options):
            raise AnalysisInputError(f"{DIMENSIONS[name]}超出支持的筛选范围。")
    if any(not re.fullmatch(r"[1-9]\d{0,2}", value) for value in filters["carriage_no"]):
        raise AnalysisInputError("车厢号应为数字，例如 3 号车厢。")
    if metric.statuses and set(filters["status"]).difference(metric.statuses):
        raise AnalysisInputError("指标与指定的状态不匹配，请调整问题中的状态或指标。")
    return metric, dataset, groups, filters, sort, limit


def build_query(scope, metric, dataset, groups, filters, sort, limit):
    columns = dimension_columns(dataset)
    group_columns = [columns[group] for group in groups]
    params = []
    predicates = []

    def include(column, values):
        if values:
            predicates.append(f"{column} IN ({', '.join(['%s'] * len(values))})")
            params.extend(values)

    if scope.date_range:
        predicates.append("service_date BETWEEN %s AND %s")
        params.extend(scope.days)
    else:
        include("service_date", scope.days)
    include("train_no", scope.trains)
    for field in (name for name in VALUE_FILTERS if name in columns):
        values = filters[field]
        include(columns[field], (values or metric.statuses) if field == "status" else values)
    select = [*group_columns, f"{metric.expression} AS metric_value"]
    sql = f"SELECT {', '.join(select)}\nFROM {dataset.view}\nWHERE " + "\n  AND ".join(predicates)
    if group_columns:
        group_list = ", ".join(group_columns)
        sql += f"\nGROUP BY {group_list}\nORDER BY metric_value {sort.upper()}, {group_list}"
    # Fetch one extra group to detect truncation without another aggregate query.
    return sql + f"\nLIMIT {limit + 1}", params


def analyze_operations(question, service_date, read_rows):
    mode = "模型查询计划"
    try:
        scope = analysis_scope(question, service_date)
        key = os.getenv("CR12306_AI_API_KEY")
        if not key:
            raise AnalysisInputError("组合分析需要配置模型。也可以使用页面上的四个常用查询。")
        catalog = available_catalog(read_rows)
        if not catalog:
            raise AnalysisInputError("未找到可用的组合分析视图，请使用启动脚本更新数据库。")
        prompt = ("将运营问题转换为查询计划，只选择下列实时视图字段和一个指标。"
                  "日期和车次由后端提取，无需放入 filters，也不要改写这些条件。"
                  f"已确定范围：{scope.label}。日期是列车运营日，状态取当前值。"
                  "按区间分组时使用 origin 和 destination。按车次或日期分别比较时加入相应分组。"
                  "城市用数据库城市名，例如上海、南京。车站用全名，席别和车型用数据库名称。"
                  "用指标所属视图的筛选枚举，车厢号用数字字符串。未指定的筛选可省略。"
                  "库存指标按全程座位位图统计。用户指定上下车区间时，请澄清并引导查区间余票。"
                  "sort 表示指标升降序，limit 默认 20，范围 1 至 50，最多四个分组字段。"
                  "如果条件、统计口径或指标无法表达，用一到两句完整中文说明缺少的条件或暂不支持的能力。"
                  "不得跳过条件或擅自近似。上下车记录不能当作列车经停站表。"
                  "询问明细、退款金额、乘客资料、历史库存、跨主题查询时请澄清。\n"
                  + json.dumps(catalog, ensure_ascii=False))
        try:
            plan = call_tool(question, key, prompt, plan_tool(catalog))
        except (OSError, ValueError, TypeError, KeyError, IndexError):
            raise AnalysisInputError("模型接口暂不可用，请稍后重试或使用常用查询。") from None
        try:
            metric, dataset, groups, filters, sort, limit = validate_plan(plan, catalog)
        except AnalysisInputError:
            raise
        except ValueError:
            raise AnalysisInputError("模型的查询计划未通过校验，请尝试明确一个指标和筛选条件。") from None
    except AnalysisInputError as exc:
        return {"mode": mode, "clarify": str(exc)}

    sql, params = build_query(scope, metric, dataset, groups, filters, sort, limit)
    result = read_rows(sql, params)
    rows = result[:limit]
    columns = [(dimension_columns(dataset)[group], DIMENSIONS[group]) for group in groups]
    columns.append(("metric_value", f"{metric.title}（{metric.unit}）"))
    details = [f"{DIMENSIONS[field]} {'、'.join(FIELD_VALUES.get(field, {}).get(value, value) for value in values)}"
               for field, values in filters.items() if values and field != "status"]
    statuses = filters["status"] or metric.statuses
    if statuses:
        details.append("状态 " + "、".join(dataset.statuses[status] for status in statuses))
    if not rows or (not groups and rows[0]["metric_value"] is None):
        answer = "此范围内没有可用于该指标的记录。"
    elif groups:
        answer = f"按{'、'.join(DIMENSIONS[group] for group in groups)}分组，共显示 {len(rows)} 组。"
        if len(result) > limit:
            answer += f"结果超过 {limit} 组，已按指标{'升序' if sort == 'asc' else '降序'}截取。"
    else:
        answer = f"{metric.title}为 {rows[0]['metric_value']} {metric.unit}。"
    return {"mode": mode, "scope": " · ".join([scope.label, *details]), "title": metric.title, "answer": answer,
            "definition": metric.definition + "日期按列车运营日，状态按查询时当前值。", "columns": columns,
            "rows": rows, "sql": sql, "params": params, "empty_value": "—",
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
