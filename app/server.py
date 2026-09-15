"""长三角 12306 本地演示服务。仅使用 Python 标准库，文件编码 UTF-8。"""

import csv
import hashlib
import io
import json
import mimetypes
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
MYSQL_DATABASE = os.environ.get("CR12306_DB", "CR12306")
SERVER_PORT = int(os.environ.get("CR12306_PORT", "8080"))
MYSQL_CONTAINER = os.environ.get("CR12306_MYSQL_CONTAINER", "mysql84")
MYSQL_PASSWORD = os.environ.get("CR12306_MYSQL_PASSWORD", "123456")
NEO4J_CONTAINER = os.environ.get("CR12306_NEO4J_CONTAINER", "neo4j-12306")
NEO4J_PASSWORD = os.environ.get("CR12306_NEO4J_PASSWORD", "12345678")
MYSQL_BASE = [
    "docker", "exec", MYSQL_CONTAINER, "mysql", "--default-character-set=utf8mb4",
    "-uroot", f"-p{MYSQL_PASSWORD}", "-D", MYSQL_DATABASE, "--batch", "--raw",
]
NEO4J_BASE = [
    "docker", "exec", NEO4J_CONTAINER, "cypher-shell",
    "-u", "neo4j", "-p", NEO4J_PASSWORD, "--format", "plain",
]
POSITION_CODES = {"A", "B", "C", "D", "F"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
AI_JOBS: Dict[str, Dict[str, Any]] = {}
AI_JOBS_LOCK = threading.Lock()


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def sql_text(value: str) -> str:
    """用 UTF-8 十六进制字面量传值，避免引号注入和终端编码变化。"""
    return f"CONVERT(0x{value.encode('utf-8').hex()} USING utf8mb4)"


def run_process(command: List[str], timeout: int = 30) -> str:
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        match = re.search(r"ERROR \d+ \([^)]*\).*?: (.+)", detail)
        raise ApiError(match.group(1) if match else detail or "数据库命令失败", 409)
    return completed.stdout


def mysql_rows(sql: str, timeout: int = 30) -> List[Dict[str, Any]]:
    output = run_process(MYSQL_BASE + ["-e", sql], timeout)
    if not output.strip():
        return []
    reader = csv.DictReader(io.StringIO(output), delimiter="\t")
    return [{key: (None if value == "NULL" else value) for key, value in row.items()}
            for row in reader]


def neo4j_rows(cypher: str, timeout: int = 30) -> List[Dict[str, Any]]:
    output = run_process(NEO4J_BASE + [cypher], timeout)
    if not output.strip():
        return []
    # cypher-shell plain 格式在逗号后保留一个空格；跳过该空格，
    # 否则 JSON 候选会产生 " secondRunId" 这类错误字段名。
    return list(csv.DictReader(io.StringIO(output), skipinitialspace=True))


def integer(value: Any, name: str, minimum: int = 1, maximum: int = 2**63 - 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ApiError(f"{name} 必须是整数")
    if not minimum <= parsed <= maximum:
        raise ApiError(f"{name} 超出范围")
    return parsed


def boolean(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).lower() in {"1", "true", "yes", "on"}


def position(value: Any) -> Optional[str]:
    if value in (None, "", "ANY"):
        return None
    parsed = str(value).upper()
    if parsed not in POSITION_CODES:
        raise ApiError("位置必须是 A/B/C/D/F")
    return parsed


def json_body(handler: SimpleHTTPRequestHandler) -> Dict[str, Any]:
    length = integer(handler.headers.get("Content-Length", "0"), "Content-Length", 0, 100_000)
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ApiError("请求 JSON 无效")


def direct_search(params: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    origin = integer(params.get("from", [None])[0], "from")
    destination = integer(params.get("to", [None])[0], "to")
    passengers = integer(params.get("passengers", ["1"])[0], "passengers", 1, 5)
    service_date = params.get("date", ["2026-09-07"])[0]
    if not DATE_RE.match(service_date):
        raise ApiError("date 格式必须为 YYYY-MM-DD")
    preferred = position(params.get("position", [None])[0])
    fallback = boolean(params.get("fallback", ["true"])[0])
    pos_sql = "NULL" if preferred is None else sql_text(preferred)
    return mysql_rows(
        "CALL sp_search_direct_trains("
        f"{origin},{destination},'{service_date}',NULL,NULL,{passengers},"
        f"{pos_sql},{1 if fallback else 0});",
        timeout=20,
    )


def scoped_direct_search(params: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    """Search a station pair or every valid station pair inside two cities."""
    from_city = str(params.get("fromCity", [""])[0]).strip()
    to_city = str(params.get("toCity", [""])[0]).strip()
    if not from_city or not to_city or len(from_city) > 50 or len(to_city) > 50:
        raise ApiError("请选择出发城市和到达城市")
    from_station_raw = params.get("fromStation", [""])[0]
    to_station_raw = params.get("toStation", [""])[0]
    from_station = integer(from_station_raw, "fromStation") if from_station_raw else None
    to_station = integer(to_station_raw, "toStation") if to_station_raw else None
    passengers = integer(params.get("passengers", ["1"])[0], "passengers", 1, 5)
    service_date = params.get("date", ["2026-09-07"])[0]
    if not DATE_RE.match(service_date):
        raise ApiError("date 格式必须为 YYYY-MM-DD")
    if from_city == to_city and from_station is None and to_station is None:
        raise ApiError("出发城市与到达城市不能相同")
    from_filter = f" AND origin.station_id={from_station}" if from_station else ""
    to_filter = f" AND destination.station_id={to_station}" if to_station else ""
    rows = mysql_rows(
        "SELECT tr.run_id,tr.train_no,t.train_type,origin.station_id AS from_station_id,"
        "origin_station.station_name AS from_station_name,origin.station_order AS from_order,"
        "origin.departure_at,destination.station_id AS to_station_id,"
        "destination_station.station_name AS to_station_name,destination.station_order AS to_order,"
        "destination.arrival_at,TIMESTAMPDIFF(MINUTE,origin.departure_at,destination.arrival_at) duration_minutes,"
        "CASE WHEN origin.station_order=1 THEN '始' ELSE '过' END AS from_marker,"
        "CASE WHEN destination.station_order=tr.stop_count THEN '终' ELSE '过' END AS to_marker,"
        "st.seat_type_id,st.seat_type_code,st.seat_type_name,st.display_order,"
        "rf.journey_distance_km,rf.amount,COUNT(*) total_seats,"
        "SUM((trs.occupied_mask & fn_segment_mask(origin.station_order,destination.station_order))=0) available_seats,"
        f"SUM((trs.occupied_mask & fn_segment_mask(origin.station_order,destination.station_order))=0)>={passengers} can_fulfill "
        "FROM train_run tr JOIN train t ON t.train_no=tr.train_no "
        "JOIN v_train_run_stop origin ON origin.run_id=tr.run_id "
        "JOIN station origin_station ON origin_station.station_id=origin.station_id "
        "JOIN v_train_run_stop destination ON destination.run_id=tr.run_id "
        " AND destination.station_order>origin.station_order "
        "JOIN station destination_station ON destination_station.station_id=destination.station_id "
        "JOIN run_fare rf ON rf.run_id=tr.run_id AND rf.from_order=origin.station_order "
        " AND rf.to_order=destination.station_order AND rf.sale_status='OPEN' "
        "JOIN seat_type st ON st.seat_type_id=rf.seat_type_id AND st.active=TRUE "
        "JOIN train_run_seat trs ON trs.run_id=tr.run_id "
        "JOIN seat s ON s.seat_id=trs.seat_id AND s.seat_type_id=rf.seat_type_id AND s.active=TRUE "
        "JOIN carriage_template ct ON ct.carriage_id=s.carriage_id "
        " AND ct.formation_id=tr.formation_id AND ct.active=TRUE "
        f"WHERE tr.service_date='{service_date}' AND tr.run_status='ON_SALE' "
        f"AND origin_station.city={sql_text(from_city)} AND destination_station.city={sql_text(to_city)}"
        f"{from_filter}{to_filter} "
        "AND origin.departure_at IS NOT NULL AND destination.arrival_at IS NOT NULL "
        "GROUP BY tr.run_id,tr.train_no,t.train_type,origin.station_id,origin_station.station_name,"
        "origin.station_order,origin.departure_at,destination.station_id,destination_station.station_name,"
        "destination.station_order,destination.arrival_at,tr.stop_count,st.seat_type_id,st.seat_type_code,"
        "st.seat_type_name,st.display_order,rf.journey_distance_km,rf.amount "
        "ORDER BY origin.departure_at,tr.train_no,st.display_order;",
        timeout=30,
    )
    # A train may stop at more than one station in a selected city. Keep one
    # deterministic OD product per run and seat class for a concise train list.
    unique: Dict[tuple, Dict[str, Any]] = {}
    for row in rows:
        key = (row["run_id"], row["seat_type_id"])
        if key not in unique:
            unique[key] = row
    return list(unique.values())


def transfer_search(params: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    origin = integer(params.get("from", [None])[0], "from")
    destination = integer(params.get("to", [None])[0], "to")
    passengers = integer(params.get("passengers", ["1"])[0], "passengers", 1, 5)
    service_date = params.get("date", ["2026-09-07"])[0]
    if not DATE_RE.match(service_date):
        raise ApiError("date 格式必须为 YYYY-MM-DD")
    preferred = position(params.get("position", [None])[0])
    fallback = boolean(params.get("fallback", ["true"])[0])
    cypher = f"""
    MATCH (origin:Station {{station_id:{origin}}}),
          (destination:Station {{station_id:{destination}}})
    MATCH (first:TrainRun {{service_date:'{service_date}'}})-[a:CALLS_AT]->(origin)
    MATCH (first)-[b:CALLS_AT]->(transfer:Station)
    WHERE b.station_order>a.station_order AND transfer<>origin AND transfer<>destination
    MATCH (second:TrainRun {{service_date:'{service_date}'}})-[c:CALLS_AT]->(transfer)
    MATCH (second)-[d:CALLS_AT]->(destination)
    WHERE second<>first AND d.station_order>c.station_order
      AND b.arrival_at IS NOT NULL AND c.departure_at IS NOT NULL
      AND c.departure_at>b.arrival_at
    RETURN DISTINCT first.run_id AS firstRunId,
           second.run_id AS secondRunId,
           transfer.station_id AS transferStationId
    LIMIT 80
    """
    graph_rows = neo4j_rows(cypher, timeout=20)
    candidates = [{key: int(value) for key, value in row.items()} for row in graph_rows]
    if not candidates:
        return []
    candidate_json = json.dumps(candidates, separators=(",", ":"))
    pos_sql = "NULL" if preferred is None else sql_text(preferred)
    return mysql_rows(
        "CALL sp_validate_transfer_candidates("
        f"{sql_text(candidate_json)},{origin},{destination},'{service_date}',"
        f"15,240,{passengers},{pos_sql},{1 if fallback else 0});",
        timeout=20,
    )


def public_ai_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Remove internal timing data and calculate live task metrics."""
    result = {key: value for key, value in job.items() if not key.startswith("_")}
    elapsed = max(0.001, time.monotonic() - job.get("_started_monotonic", time.monotonic()))
    if job.get("status") != "RUNNING" and job.get("elapsed") is not None:
        elapsed = float(job["elapsed"])
    result["elapsed"] = round(elapsed, 2)
    result["rps"] = round(int(job.get("completed", 0)) / elapsed, 2)
    return result


def ai_products(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    target = ""
    if config["mode"] == "targeted":
        target = (
            f" AND rf.run_id={config['run_id']}"
            f" AND rf.seat_type_id={config['seat_type_id']}"
        )
    return mysql_rows(
        "SELECT rf.run_id,rf.from_order,rf.to_order,rf.seat_type_id "
        "FROM run_fare rf JOIN train_run tr ON tr.run_id=rf.run_id "
        "WHERE rf.sale_status='OPEN' AND tr.run_status='ON_SALE'" + target +
        " ORDER BY RAND() LIMIT 500;"
    )


def simulate_ai_passenger(job_id: str, index: int, product: Dict[str, Any],
                          config: Dict[str, Any]) -> str:
    """Execute one real database booking flow and return its terminal outcome."""
    token = uuid.uuid4().hex
    username = f"ai_{job_id.lower()}_{index}_{token[:6]}"
    password_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    account_rows = mysql_rows(
        "CALL sp_register_demo_account("
        f"{sql_text(username)},{sql_text(password_hash)},"
        f"{sql_text('AI乘客' + str(index))},{sql_text('AI-DOC-' + token)},@uid,@pid);"
        "SELECT @uid AS user_id,@pid AS passenger_id;"
    )
    account = account_rows[-1]
    user_id, passenger_id = int(account["user_id"]), int(account["passenger_id"])
    run_id, from_order = int(product["run_id"]), int(product["from_order"])
    to_order, seat_type_id = int(product["to_order"]), int(product["seat_type_id"])
    order_key = "AI-" + uuid.uuid4().hex
    try:
        order_rows = mysql_rows(
            "CALL sp_create_order_hold("
            f"{user_id},{run_id},{from_order},{to_order},{seat_type_id},"
            f"NULL,1,JSON_ARRAY({passenger_id}),'{order_key}',600,@oid);"
            "SELECT @oid AS order_id;"
        )
        order_id = int(order_rows[-1]["order_id"])
        if random.random() * 100 < config["pay_rate"]:
            request_no = "AI-PAY-" + uuid.uuid4().hex
            trade_no = "AI-TRADE-" + uuid.uuid4().hex
            mysql_rows(
                f"SET @amount=(SELECT total_amount FROM ticket_order WHERE order_id={order_id});"
                "CALL sp_confirm_order_payment("
                f"{user_id},{order_id},'{request_no}','{trade_no}',@amount,@payment_id);"
            )
            return "paid"
        return "held"
    except Exception as hold_error:
        if not config["waitlist"]:
            raise hold_error
        cutoff = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        mysql_rows(
            "CALL sp_create_wait_request("
            f"{user_id},{run_id},{from_order},{to_order},{seat_type_id},"
            f"NULL,1,JSON_ARRAY({passenger_id}),'AI-WAIT-{uuid.uuid4().hex}',"
            f"TIMESTAMPADD(DAY,1,'{cutoff}'),@wid);"
        )
        return "waitlisted"


def run_ai_job(job_id: str, config: Dict[str, Any]) -> None:
    started = time.monotonic()
    try:
        products = ai_products(config)
        if not products:
            raise ApiError("没有符合当前策略的在售票价产品")
        with ThreadPoolExecutor(max_workers=config["concurrency"]) as executor:
            futures = [executor.submit(
                simulate_ai_passenger, job_id, index + 1,
                random.choice(products), config,
            ) for index in range(config["users"])]
            for future in as_completed(futures):
                try:
                    outcome = future.result()
                    with AI_JOBS_LOCK:
                        AI_JOBS[job_id][outcome] += 1
                except Exception as exc:
                    with AI_JOBS_LOCK:
                        AI_JOBS[job_id]["failed"] += 1
                        if len(AI_JOBS[job_id]["errors"]) < 12:
                            AI_JOBS[job_id]["errors"].append(str(exc)[:180])
                finally:
                    with AI_JOBS_LOCK:
                        AI_JOBS[job_id]["completed"] += 1
        with AI_JOBS_LOCK:
            AI_JOBS[job_id]["status"] = "COMPLETED"
            AI_JOBS[job_id]["elapsed"] = round(time.monotonic() - started, 2)
    except Exception as exc:
        with AI_JOBS_LOCK:
            AI_JOBS[job_id]["status"] = "FAILED"
            AI_JOBS[job_id]["elapsed"] = round(time.monotonic() - started, 2)
            AI_JOBS[job_id]["errors"].append(str(exc)[:180])


def ai_order_action(order_id: int) -> Dict[str, Any]:
    rows = mysql_rows(
        "SELECT o.order_id,o.user_id,o.order_status FROM ticket_order o "
        "JOIN app_user u ON u.user_id=o.user_id "
        f"WHERE o.order_id={order_id} AND u.username LIKE 'ai\\_%';"
    )
    if not rows:
        raise ApiError("只能操作 AI 订票员生成的订单", 403)
    order = rows[0]
    user_id = int(order["user_id"])
    if order["order_status"] == "PAID":
        result = mysql_rows(
            "CALL sp_refund_paid_order("
            f"{user_id},{order_id},'ADMIN-AI-REF-{uuid.uuid4().hex}',"
            "'ADMIN_LOAD_TEST',@rid);SELECT @rid AS refund_id;"
        )
        return {"order_id": order_id, "action": "REFUNDED",
                "refund_id": result[-1].get("refund_id") if result else None}
    if order["order_status"] == "PENDING_PAYMENT":
        mysql_rows(f"CALL sp_cancel_unpaid_order({user_id},{order_id});")
        return {"order_id": order_id, "action": "CANCELLED"}
    raise ApiError("该 AI 订单当前状态不可退票或取消", 409)


class Handler(SimpleHTTPRequestHandler):
    server_version = "CR12306Demo/1.0"

    def send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def handle_api(self, method: str) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if method == "GET" and parsed.path == "/api/health":
            mysql = mysql_rows("SELECT COUNT(*) AS runs FROM train_run WHERE run_status='ON_SALE';")[0]
            graph = neo4j_rows("MATCH (r:TrainRun) RETURN count(r) AS runs")
            self.send_json({"ok": True, "mysql": mysql, "neo4j": graph[0] if graph else {}})
        elif method == "GET" and parsed.path == "/api/stations":
            self.send_json(mysql_rows(
                "SELECT station_id,station_name,city FROM station ORDER BY city,station_name"
            ))
        elif method == "GET" and parsed.path == "/api/locations":
            self.send_json(mysql_rows(
                "SELECT station_id,station_name,city FROM station ORDER BY city,station_name"
            ))
        elif method == "GET" and re.match(r"^/api/runs/\d+/stops$", parsed.path):
            run_id = integer(parsed.path.split("/")[3], "runId")
            self.send_json(mysql_rows(
                "SELECT v.run_id,v.train_no,v.station_order,s.station_name,"
                "v.arrival_at,v.departure_at,"
                "CASE WHEN v.arrival_at IS NULL OR v.departure_at IS NULL THEN NULL "
                "ELSE TIMESTAMPDIFF(MINUTE,v.arrival_at,v.departure_at) END AS dwell_minutes "
                "FROM v_train_run_stop v JOIN station s ON s.station_id=v.station_id "
                f"WHERE v.run_id={run_id} ORDER BY v.station_order;"
            ))
        elif method == "GET" and parsed.path == "/api/search/direct":
            self.send_json(direct_search(params))
        elif method == "GET" and parsed.path == "/api/search/scoped-direct":
            self.send_json(scoped_direct_search(params))
        elif method == "GET" and parsed.path == "/api/search/transfer":
            self.send_json(transfer_search(params))
        elif method == "GET" and parsed.path == "/api/orders":
            user_id = integer(params.get("userId", [None])[0], "userId")
            self.send_json(mysql_rows(
                "SELECT * FROM v_order_detail WHERE user_id="
                f"{user_id} ORDER BY created_at DESC,order_item_id"
            ))
        elif method == "POST" and parsed.path == "/api/register":
            body = json_body(self)
            username = str(body.get("username", "")).strip()
            passenger_name = str(body.get("passengerName", "")).strip()
            document_token = str(body.get("documentToken", "")).strip()
            password_hash = str(body.get("passwordHash", "")).strip()
            rows = mysql_rows(
                "CALL sp_register_demo_account("
                f"{sql_text(username)},{sql_text(password_hash)},"
                f"{sql_text(passenger_name)},{sql_text(document_token)},@uid,@pid);"
                "SELECT @uid AS user_id,@pid AS passenger_id;"
            )
            self.send_json(rows[-1], HTTPStatus.CREATED)
        elif method == "POST" and parsed.path == "/api/auth/simple":
            body = json_body(self)
            display_name = str(body.get("name", "")).strip()
            password_hash = str(body.get("passwordHash", "")).strip().lower()
            if not display_name or len(display_name) > 80:
                raise ApiError("请输入姓名")
            if not re.fullmatch(r"[0-9a-f]{64}", password_hash):
                raise ApiError("密码摘要无效")
            name_digest = hashlib.sha256(display_name.encode("utf-8")).hexdigest()
            username = "user_" + name_digest[:24]
            existing = mysql_rows(
                "SELECT u.user_id,u.password_hash,p.passenger_id,p.passenger_name "
                "FROM app_user u LEFT JOIN passenger p ON p.owner_user_id=u.user_id "
                f"WHERE u.username={sql_text(username)} ORDER BY p.passenger_id LIMIT 1;"
            )
            if existing:
                if not hashlib.compare_digest(str(existing[0]["password_hash"]), password_hash):
                    raise ApiError("姓名或密码错误", 401)
                self.send_json({"user_id": existing[0]["user_id"],
                                "passenger_id": existing[0]["passenger_id"],
                                "display_name": existing[0]["passenger_name"]})
            else:
                rows = mysql_rows(
                    "CALL sp_register_demo_account("
                    f"{sql_text(username)},{sql_text(password_hash)},{sql_text(display_name)},"
                    f"{sql_text('USER-' + name_digest)},@uid,@pid);"
                    "SELECT @uid AS user_id,@pid AS passenger_id;"
                )
                result = rows[-1]
                result["display_name"] = display_name
                self.send_json(result, HTTPStatus.CREATED)
        elif method == "POST" and parsed.path == "/api/orders":
            body = json_body(self)
            user_id = integer(body.get("userId"), "userId")
            passenger_id = integer(body.get("passengerId"), "passengerId")
            run_id = integer(body.get("runId"), "runId")
            from_order = integer(body.get("fromOrder"), "fromOrder", 1, 64)
            to_order = integer(body.get("toOrder"), "toOrder", 2, 64)
            seat_type_id = integer(body.get("seatTypeId"), "seatTypeId", 1, 65535)
            preferred = position(body.get("position"))
            fallback = boolean(body.get("fallback"))
            pos_sql = "NULL" if preferred is None else sql_text(preferred)
            key = "WEB-" + uuid.uuid4().hex
            rows = mysql_rows(
                "CALL sp_create_order_hold("
                f"{user_id},{run_id},{from_order},{to_order},{seat_type_id},"
                f"{pos_sql},{1 if fallback else 0},JSON_ARRAY({passenger_id}),"
                f"'{key}',600,@oid);SELECT @oid AS order_id;"
            )
            self.send_json(rows[-1], HTTPStatus.CREATED)
        elif method == "POST" and parsed.path == "/api/orders/confirm":
            body = json_body(self)
            user_id = integer(body.get("userId"), "userId")
            passenger_id = integer(body.get("passengerId"), "passengerId")
            run_id = integer(body.get("runId"), "runId")
            from_order = integer(body.get("fromOrder"), "fromOrder", 1, 64)
            to_order = integer(body.get("toOrder"), "toOrder", 2, 64)
            seat_type_id = integer(body.get("seatTypeId"), "seatTypeId", 1, 65535)
            preferred = position(body.get("position"))
            pos_sql = "NULL" if preferred is None else sql_text(preferred)
            order_key = "WEB-CONFIRM-" + uuid.uuid4().hex
            pay_request = "PAY-" + uuid.uuid4().hex
            trade_no = "TRADE-" + uuid.uuid4().hex
            rows = mysql_rows(
                "CALL sp_create_order_hold("
                f"{user_id},{run_id},{from_order},{to_order},{seat_type_id},{pos_sql},1,"
                f"JSON_ARRAY({passenger_id}),'{order_key}',600,@oid);"
                "SET @amount=(SELECT total_amount FROM ticket_order WHERE order_id=@oid);"
                "CALL sp_confirm_order_payment("
                f"{user_id},@oid,'{pay_request}','{trade_no}',@amount,@payment_id);"
                "SELECT d.*,@payment_id AS payment_id FROM v_order_detail d WHERE d.order_id=@oid;"
            )
            if not rows:
                raise ApiError("订单确认后未返回详情", 500)
            self.send_json(rows[-1], HTTPStatus.CREATED)
        elif method == "POST" and re.match(r"^/api/orders/\d+/(pay|cancel|refund)$", parsed.path):
            body = json_body(self)
            parts = parsed.path.split("/")
            order_id = integer(parts[3], "orderId")
            action = parts[4]
            user_id = integer(body.get("userId"), "userId")
            if action == "pay":
                request_no = "PAY-" + uuid.uuid4().hex
                trade_no = "TRADE-" + uuid.uuid4().hex
                rows = mysql_rows(
                    f"SET @amount=(SELECT total_amount FROM ticket_order WHERE order_id={order_id});"
                    "CALL sp_confirm_order_payment("
                    f"{user_id},{order_id},'{request_no}','{trade_no}',@amount,@pid);"
                    "SELECT @pid AS payment_id;"
                )
                self.send_json(rows[-1])
            elif action == "cancel":
                mysql_rows(f"CALL sp_cancel_unpaid_order({user_id},{order_id});")
                self.send_json({"order_id": order_id, "status": "CANCELLED"})
            else:
                request_no = "REF-" + uuid.uuid4().hex
                rows = mysql_rows(
                    "CALL sp_refund_paid_order("
                    f"{user_id},{order_id},'{request_no}','USER_REQUEST',@rid);"
                    "SELECT @rid AS refund_id;"
                )
                self.send_json(rows[-1])
        elif method == "POST" and parsed.path == "/api/waits":
            body = json_body(self)
            user_id = integer(body.get("userId"), "userId")
            passenger_id = integer(body.get("passengerId"), "passengerId")
            preferred = position(body.get("position"))
            pos_sql = "NULL" if preferred is None else sql_text(preferred)
            fallback = boolean(body.get("fallback"))
            cutoff = datetime.now().replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
            rows = mysql_rows(
                "CALL sp_create_wait_request("
                f"{user_id},{integer(body.get('runId'),'runId')},"
                f"{integer(body.get('fromOrder'),'fromOrder',1,64)},"
                f"{integer(body.get('toOrder'),'toOrder',2,64)},"
                f"{integer(body.get('seatTypeId'),'seatTypeId',1,65535)},"
                f"{pos_sql},{1 if fallback else 0},JSON_ARRAY({passenger_id}),"
                f"'WEB-WAIT-{uuid.uuid4().hex}',TIMESTAMPADD(DAY,1,'{cutoff}'),@wid);"
                "SELECT @wid AS wait_request_id;"
            )
            self.send_json(rows[-1], HTTPStatus.CREATED)
        elif method == "GET" and parsed.path == "/api/admin/overview":
            metrics = mysql_rows(
                "SELECT "
                "(SELECT COUNT(*) FROM train_run) AS runs,"
                "(SELECT COUNT(*) FROM train_run WHERE run_status='ON_SALE') AS on_sale,"
                "(SELECT COUNT(*) FROM train_run_seat) AS seats,"
                "(SELECT COUNT(*) FROM train_run_seat WHERE occupied_mask<>0) AS occupied_seats,"
                "ROUND(100*(SELECT COUNT(*) FROM train_run_seat WHERE occupied_mask<>0)/"
                "NULLIF((SELECT COUNT(*) FROM train_run_seat),0),1) AS occupancy_rate,"
                "(SELECT COUNT(*) FROM ticket_order) AS orders,"
                "(SELECT COUNT(*) FROM ticket_order WHERE order_status='PAID') AS paid_orders,"
                "(SELECT COUNT(*) FROM wait_request WHERE wait_status IN ('WAITING','MATCHING')) AS waiting,"
                "(SELECT COUNT(*) FROM passenger) AS passengers;"
            )[0]
            order_statuses = mysql_rows(
                "SELECT order_status,COUNT(*) AS count FROM ticket_order "
                "GROUP BY order_status ORDER BY count DESC;"
            )
            top_trains = mysql_rows(
                "SELECT tr.run_id,tr.train_no,"
                "(SELECT s.station_name FROM v_train_run_stop v JOIN station s ON s.station_id=v.station_id "
                " WHERE v.run_id=tr.run_id ORDER BY v.station_order LIMIT 1) AS origin_name,"
                "(SELECT s.station_name FROM v_train_run_stop v JOIN station s ON s.station_id=v.station_id "
                " WHERE v.run_id=tr.run_id ORDER BY v.station_order DESC LIMIT 1) AS destination_name,"
                "COUNT(trs.seat_id) AS total_seats,SUM(trs.occupied_mask<>0) AS occupied_seats,"
                "ROUND(100*SUM(trs.occupied_mask<>0)/NULLIF(COUNT(trs.seat_id),0),1) AS occupancy_rate "
                "FROM train_run tr JOIN train_run_seat trs ON trs.run_id=tr.run_id "
                "GROUP BY tr.run_id,tr.train_no ORDER BY occupancy_rate DESC,total_seats DESC LIMIT 5;"
            )
            pulse = mysql_rows(
                "SELECT bucket,SUM(order_count) AS orders,SUM(inventory_count) AS inventory FROM ("
                "SELECT DATE_FORMAT(occurred_at,'%Y-%m-%d %H:%i') bucket,COUNT(*) order_count,0 inventory_count "
                "FROM order_event GROUP BY bucket UNION ALL "
                "SELECT DATE_FORMAT(occurred_at,'%Y-%m-%d %H:%i') bucket,0,COUNT(*) "
                "FROM inventory_event GROUP BY bucket) x GROUP BY bucket ORDER BY bucket DESC LIMIT 12;"
            )
            pulse.reverse()
            activity = mysql_rows(
                "SELECT category,event_type,subject,occurred_at FROM ("
                "SELECT 'ORDER' category,oe.event_type,CONCAT('订单 #',oe.order_id) subject,oe.occurred_at "
                "FROM order_event oe UNION ALL "
                "SELECT 'INVENTORY',ie.event_type,CONCAT(tr.train_no,' · 席位 #',ie.seat_id),ie.occurred_at "
                "FROM inventory_event ie JOIN train_run tr ON tr.run_id=ie.run_id) a "
                "ORDER BY occurred_at DESC LIMIT 10;"
            )
            self.send_json({"metrics": metrics, "order_statuses": order_statuses,
                            "top_trains": top_trains, "pulse": pulse, "activity": activity})
        elif method == "GET" and parsed.path == "/api/admin/trains":
            service_date = params.get("date", ["2026-09-07"])[0]
            if not DATE_RE.match(service_date):
                raise ApiError("date 格式必须为 YYYY-MM-DD")
            query = str(params.get("q", [""])[0]).strip()[:20]
            where_query = "" if not query else f" AND tr.train_no LIKE CONCAT('%',{sql_text(query)},'%')"
            self.send_json(mysql_rows(
                "SELECT tr.run_id,tr.train_no,tr.service_date,tr.stop_count,tr.run_status,"
                "origin.station_name AS origin_name,destination.station_name AS destination_name,"
                "first_stop.departure_at,last_stop.arrival_at,COUNT(trs.seat_id) AS total_seats,"
                "SUM(trs.occupied_mask<>0) AS occupied_seats,"
                "ROUND(100*SUM(trs.occupied_mask<>0)/NULLIF(COUNT(trs.seat_id),0),1) AS occupancy_rate "
                "FROM train_run tr "
                "JOIN v_train_run_stop first_stop ON first_stop.run_id=tr.run_id AND first_stop.station_order=1 "
                "JOIN station origin ON origin.station_id=first_stop.station_id "
                "JOIN v_train_run_stop last_stop ON last_stop.run_id=tr.run_id AND last_stop.station_order=tr.stop_count "
                "JOIN station destination ON destination.station_id=last_stop.station_id "
                "LEFT JOIN train_run_seat trs ON trs.run_id=tr.run_id "
                f"WHERE tr.service_date='{service_date}'{where_query} "
                "GROUP BY tr.run_id,tr.train_no,tr.service_date,tr.stop_count,tr.run_status,"
                "origin.station_name,destination.station_name,first_stop.departure_at,last_stop.arrival_at "
                "ORDER BY first_stop.departure_at,tr.train_no LIMIT 300;"
            ))
        elif method == "GET" and parsed.path == "/api/admin/train-seats":
            run_id = integer(params.get("runId", [None])[0], "runId")
            self.send_json(mysql_rows(
                "SELECT ct.carriage_no,st.seat_type_id,st.seat_type_name,COUNT(*) AS total_seats,"
                "SUM(trs.occupied_mask=0) AS free_full_route,SUM(trs.occupied_mask<>0) AS occupied_seats,"
                "ROUND(100*SUM(trs.occupied_mask<>0)/COUNT(*),1) AS occupancy_rate,"
                "(SELECT COUNT(*) FROM seat_allocation sa JOIN seat sx ON sx.seat_id=sa.seat_id "
                " WHERE sa.run_id=trs.run_id AND sx.carriage_id=ct.carriage_id "
                " AND sx.seat_type_id=st.seat_type_id AND sa.allocation_status IN ('HOLD','CONFIRMED')) AS active_holds "
                "FROM train_run_seat trs JOIN seat s ON s.seat_id=trs.seat_id "
                "JOIN carriage_template ct ON ct.carriage_id=s.carriage_id "
                "JOIN seat_type st ON st.seat_type_id=s.seat_type_id "
                f"WHERE trs.run_id={run_id} GROUP BY trs.run_id,ct.carriage_id,ct.carriage_no,"
                "st.seat_type_id,st.seat_type_name ORDER BY ct.carriage_no,st.display_order;"
            ))
        elif method == "GET" and parsed.path == "/api/admin/orders":
            status = str(params.get("status", [""])[0]).strip()
            allowed = {"", "PENDING_PAYMENT", "PAID", "CANCELLED", "TIMEOUT", "REFUNDING", "REFUNDED"}
            if status not in allowed:
                raise ApiError("未知订单状态")
            status_sql = "" if not status else f" WHERE d.order_status={sql_text(status)}"
            self.send_json(mysql_rows(
                "SELECT d.order_id,d.order_no,d.order_status,d.total_amount,d.created_at,d.passenger_name,"
                "u.username,d.train_no,d.run_id,d.from_station_name,d.to_station_name,tr.service_date,"
                "d.seat_type_name,d.carriage_no,d.seat_no FROM v_order_detail d "
                "JOIN app_user u ON u.user_id=d.user_id JOIN train_run tr ON tr.run_id=d.run_id" +
                status_sql + " ORDER BY d.created_at DESC,d.order_id DESC LIMIT 300;"
            ))
        elif method == "GET" and parsed.path == "/api/admin/passengers":
            query = str(params.get("q", [""])[0]).strip()[:80]
            query_sql = "" if not query else (
                f" WHERE p.passenger_name LIKE CONCAT('%',{sql_text(query)},'%')"
                f" OR u.username LIKE CONCAT('%',{sql_text(query)},'%')"
            )
            self.send_json(mysql_rows(
                "SELECT p.passenger_id,p.passenger_name,p.document_type,p.passenger_status,p.created_at,"
                "p.owner_user_id,u.username,u.user_status,"
                "COUNT(DISTINCT oi.order_id) AS order_count,COUNT(DISTINCT wp.wait_request_id) AS wait_count "
                "FROM passenger p JOIN app_user u ON u.user_id=p.owner_user_id "
                "LEFT JOIN order_item oi ON oi.passenger_id=p.passenger_id "
                "LEFT JOIN wait_passenger wp ON wp.passenger_id=p.passenger_id" + query_sql +
                " GROUP BY p.passenger_id,p.passenger_name,p.document_type,p.passenger_status,p.created_at,"
                "p.owner_user_id,u.username,u.user_status ORDER BY p.created_at DESC LIMIT 300;"
            ))
        elif method == "GET" and parsed.path == "/api/admin/waits":
            summary = mysql_rows(
                "SELECT SUM(wait_status IN ('WAITING','MATCHING')) AS waiting,"
                "SUM(wait_status IN ('MATCHED_HOLD','FULFILLED')) AS fulfilled,"
                "SUM(skip_count>=3 AND wait_status IN ('WAITING','MATCHING')) AS protected,"
                "COALESCE(SUM(skip_count),0) AS skipped FROM wait_request;"
            )[0]
            rows = mysql_rows(
                "SELECT wr.wait_request_id,wr.wait_request_no,wr.passenger_count,wr.wait_status,"
                "wr.skip_count,wr.retry_count,wr.cutoff_at,tr.train_no,st.seat_type_name,"
                "origin_station.station_name AS from_station_name,dest_station.station_name AS to_station_name,"
                "q.queue_position,q.fairness_protected FROM wait_request wr "
                "JOIN train_run tr ON tr.run_id=wr.run_id JOIN seat_type st ON st.seat_type_id=wr.seat_type_id "
                "JOIN v_train_run_stop origin ON origin.run_id=wr.run_id AND origin.station_order=wr.from_order "
                "JOIN station origin_station ON origin_station.station_id=origin.station_id "
                "JOIN v_train_run_stop dest ON dest.run_id=wr.run_id AND dest.station_order=wr.to_order "
                "JOIN station dest_station ON dest_station.station_id=dest.station_id "
                "LEFT JOIN v_wait_queue q ON q.wait_request_id=wr.wait_request_id "
                "ORDER BY FIELD(wr.wait_status,'MATCHING','WAITING','MATCHED_HOLD','FULFILLED','CANCELLED','EXPIRED'),"
                "wr.created_at DESC LIMIT 300;"
            )
            self.send_json({"summary": summary, "rows": rows})
        elif method == "GET" and parsed.path == "/api/admin/ai/options":
            runs = mysql_rows(
                "SELECT tr.run_id,tr.train_no,origin.station_name origin_name,dest.station_name destination_name "
                "FROM train_run tr JOIN v_train_run_stop vo ON vo.run_id=tr.run_id AND vo.station_order=1 "
                "JOIN station origin ON origin.station_id=vo.station_id "
                "JOIN v_train_run_stop vd ON vd.run_id=tr.run_id AND vd.station_order=tr.stop_count "
                "JOIN station dest ON dest.station_id=vd.station_id WHERE tr.run_status='ON_SALE' "
                "ORDER BY tr.train_no LIMIT 500;"
            )
            seat_types = mysql_rows(
                "SELECT trs.run_id,st.seat_type_id,st.seat_type_name,COUNT(*) total_seats,"
                "SUM(trs.occupied_mask=0) free_full_route FROM train_run_seat trs "
                "JOIN seat s ON s.seat_id=trs.seat_id JOIN seat_type st ON st.seat_type_id=s.seat_type_id "
                "JOIN train_run tr ON tr.run_id=trs.run_id WHERE tr.run_status='ON_SALE' "
                "GROUP BY trs.run_id,st.seat_type_id,st.seat_type_name ORDER BY st.display_order;"
            )
            with AI_JOBS_LOCK:
                jobs = [public_ai_job(job) for job in reversed(list(AI_JOBS.values()))]
            self.send_json({"runs": runs, "seat_types": seat_types, "jobs": jobs[:30]})
        elif method == "GET" and parsed.path == "/api/admin/ai/orders":
            run_raw = params.get("runId", [""])[0]
            run_id = integer(run_raw, "runId") if run_raw else None
            query = str(params.get("q", [""])[0]).strip()[:80]
            filters = ["u.username LIKE 'ai\\_%'"]
            if run_id:
                filters.append(f"d.run_id={run_id}")
            if query:
                filters.append(
                    f"(d.passenger_name LIKE CONCAT('%',{sql_text(query)},'%') "
                    f"OR u.username LIKE CONCAT('%',{sql_text(query)},'%'))"
                )
            self.send_json(mysql_rows(
                "SELECT d.order_id,d.order_no,d.order_status,d.total_amount,d.created_at,"
                "d.passenger_name,u.username,d.user_id,d.train_no,d.run_id,d.from_station_name,"
                "d.to_station_name,d.seat_type_name,d.carriage_no,d.seat_no,d.allocated_position_code "
                "FROM v_order_detail d JOIN app_user u ON u.user_id=d.user_id WHERE " +
                " AND ".join(filters) + " ORDER BY d.created_at DESC LIMIT 500;"
            ))
        elif method == "GET" and parsed.path == "/api/admin/ai/jobs":
            with AI_JOBS_LOCK:
                jobs = [public_ai_job(job) for job in reversed(list(AI_JOBS.values()))]
            self.send_json(jobs[:30])
        elif method == "GET" and re.match(r"^/api/admin/ai/jobs/[A-Za-z0-9-]+$", parsed.path):
            job_id = parsed.path.rsplit("/", 1)[-1]
            with AI_JOBS_LOCK:
                if job_id not in AI_JOBS:
                    raise ApiError("AI 任务不存在", 404)
                job = public_ai_job(AI_JOBS[job_id])
            self.send_json(job)
        elif method == "POST" and parsed.path == "/api/admin/ai/start":
            body = json_body(self)
            mode = str(body.get("mode", "random"))
            if mode not in {"random", "targeted"}:
                raise ApiError("mode 必须是 random 或 targeted")
            config = {
                "mode": mode,
                "users": integer(body.get("users"), "users", 1, 500),
                "concurrency": integer(body.get("concurrency"), "concurrency", 1, 30),
                "pay_rate": integer(body.get("payRate"), "payRate", 0, 100),
                "waitlist": boolean(body.get("waitlist"), True),
            }
            if mode == "targeted":
                config["run_id"] = integer(body.get("runId"), "runId")
                config["seat_type_id"] = integer(body.get("seatTypeId"), "seatTypeId", 1, 65535)
            job_id = uuid.uuid4().hex[:8].upper()
            job = {
                "job_id": job_id, "mode": mode, "users": config["users"],
                "concurrency": config["concurrency"], "status": "RUNNING", "completed": 0,
                "held": 0, "paid": 0, "waitlisted": 0, "failed": 0, "errors": [],
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "_started_monotonic": time.monotonic(),
            }
            with AI_JOBS_LOCK:
                AI_JOBS[job_id] = job
            threading.Thread(target=run_ai_job, args=(job_id, config), daemon=True).start()
            self.send_json(public_ai_job(job), HTTPStatus.ACCEPTED)
        elif method == "POST" and re.match(r"^/api/admin/ai/orders/\d+/refund$", parsed.path):
            order_id = integer(parsed.path.split("/")[5], "orderId")
            self.send_json(ai_order_action(order_id))
        elif method == "POST" and parsed.path == "/api/admin/ai/refund-batch":
            body = json_body(self)
            run_id = integer(body.get("runId"), "runId")
            count = integer(body.get("count"), "count", 1, 100)
            candidates = mysql_rows(
                "SELECT DISTINCT d.order_id FROM v_order_detail d "
                "JOIN app_user u ON u.user_id=d.user_id "
                f"WHERE u.username LIKE 'ai\\_%' AND d.run_id={run_id} "
                "AND d.order_status IN ('PAID','PENDING_PAYMENT') ORDER BY RAND() "
                f"LIMIT {count};"
            )
            results, errors = [], []
            for candidate in candidates:
                try:
                    results.append(ai_order_action(int(candidate["order_id"])))
                except Exception as exc:
                    errors.append(str(exc)[:160])
            self.send_json({"requested": count, "selected": len(candidates),
                            "completed": len(results), "results": results, "errors": errors})
        else:
            raise ApiError("接口不存在", 404)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            try:
                self.handle_api("GET")
            except ApiError as exc:
                self.send_json({"error": str(exc)}, exc.status)
            except Exception as exc:
                self.send_json({"error": f"服务器错误：{exc}"}, 500)
            return
        parsed = urlparse(self.path)
        relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT.resolve() not in target.parents and target != WEB_ROOT.resolve():
            self.send_error(403)
            return
        if not target.is_file():
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        try:
            self.handle_api("POST")
        except ApiError as exc:
            self.send_json({"error": str(exc)}, exc.status)
        except Exception as exc:
            self.send_json({"error": f"服务器错误：{exc}"}, 500)

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stdout.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


if __name__ == "__main__":
    address = ("127.0.0.1", SERVER_PORT)
    print(f"长三角 12306 演示服务：http://{address[0]}:{address[1]}")
    ThreadingHTTPServer(address, Handler).serve_forever()
