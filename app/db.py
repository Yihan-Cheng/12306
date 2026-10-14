"""Pooled MySQL / Neo4j access for the web server.

The original helpers shelled out to ``docker exec mysql`` and
``docker exec cypher-shell`` once per statement. Process creation alone costs
130-230 ms on Windows (and 2.8-4.4 s for cypher-shell), so a page that polls a
handful of queries per user per second saturated Docker Desktop and stalled.

This module keeps persistent connections instead:

* MySQL   -> a small thread-safe pool of PyMySQL connections (~1 ms per query).
* Neo4j   -> the official bolt driver (~0.1 s vs ~3 s for cypher-shell).

Public helpers keep the exact signatures used across the codebase, so callers
do not change: ``mysql_rows(sql, timeout)`` and ``neo4j_rows(cypher, timeout)``.
Set ``CR12306_DB_BACKEND=exec`` to fall back to the original subprocess path.
"""

import csv
import io
import os
import re
import subprocess
import threading
from datetime import date, datetime
from decimal import Decimal
from queue import Empty, LifoQueue
from typing import Any, Dict, List, Optional

import pymysql
from neo4j import GraphDatabase
from pymysql.constants import CLIENT
from pymysql.cursors import DictCursor


BACKEND = os.environ.get("CR12306_DB_BACKEND", "pool").strip().lower()
if BACKEND not in {"pool", "exec"}:
    BACKEND = "pool"

# Pool backend configuration (host networking published by docker-compose).
MYSQL_HOST = os.environ.get("CR12306_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("CR12306_MYSQL_PORT", "3307"))
MYSQL_USER = os.environ.get("CR12306_MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("CR12306_MYSQL_PASSWORD", "123456")
MYSQL_DATABASE = os.environ.get("CR12306_DB", "CR12306")
MYSQL_POOL_SIZE = max(2, min(64, int(os.environ.get("CR12306_MYSQL_POOL_SIZE", "16"))))
NEO4J_URI = os.environ.get("CR12306_NEO4J_URI", "bolt://127.0.0.1:7687")
NEO4J_USER = os.environ.get("CR12306_NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("CR12306_NEO4J_PASSWORD", "12345678")

# Exec backend configuration (legacy fallback only).
MYSQL_CONTAINER = os.environ.get("CR12306_MYSQL_CONTAINER", "mysql84")
NEO4J_CONTAINER = os.environ.get("CR12306_NEO4J_CONTAINER", "neo4j-12306")
MYSQL_BASE = [
    "docker", "exec", MYSQL_CONTAINER, "mysql", "--default-character-set=utf8mb4",
    "-uroot", f"-p{MYSQL_PASSWORD}", "-D", MYSQL_DATABASE, "--batch", "--raw",
]
NEO4J_BASE = [
    "docker", "exec", NEO4J_CONTAINER, "cypher-shell",
    "-u", "neo4j", "-p", NEO4J_PASSWORD, "--format", "plain",
]


class DatabaseError(Exception):
    """Business-level database failure, surfaced as HTTP 409 like before."""

    status = 409

    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


# --------------------------------------------------------------------------- #
# Pool backend
# --------------------------------------------------------------------------- #
_pool: "LifoQueue" = LifoQueue(maxsize=MYSQL_POOL_SIZE)
_pool_guard = threading.Lock()
_pool_created = 0
_neo4j_driver = None
_neo4j_guard = threading.Lock()


def _new_mysql_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=DictCursor,
        client_flag=CLIENT.MULTI_STATEMENTS,
        connect_timeout=5,
        read_timeout=120,
        write_timeout=120,
    )


def _acquire_mysql():
    global _pool_created
    try:
        return _pool.get_nowait()
    except Empty:
        pass
    with _pool_guard:
        if _pool_created < MYSQL_POOL_SIZE:
            _pool_created += 1
            try:
                connection = _new_mysql_connection()
                connection.ping(reconnect=False)
                return connection
            except Exception:
                _pool_created -= 1
                raise
    # Pool is saturated: wait for a connection to come back.
    try:
        return _pool.get(timeout=15)
    except Empty:
        raise DatabaseError("数据库连接池繁忙，请稍后重试", 503)


def _release_mysql(connection) -> None:
    global _pool_created
    if connection is None:
        return
    try:
        _pool.put_nowait(connection)
    except Exception:
        try:
            connection.close()
        finally:
            with _pool_guard:
                _pool_created -= 1


def _discard_mysql(connection) -> None:
    global _pool_created
    if connection is None:
        return
    try:
        connection.close()
    finally:
        with _pool_guard:
            _pool_created = max(0, _pool_created - 1)


def _normalize(value: Any) -> Any:
    """Match the string form produced by ``mysql --batch --raw``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return value


def _fetch_all(cursor) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    while True:
        if cursor.description is not None:
            for row in cursor.fetchall():
                rows.append({key: _normalize(val) for key, val in row.items()})
        if not cursor.nextset():
            break
    return rows


def _clean_db_message(exc: Exception) -> str:
    args = getattr(exc, "args", None)
    if args and len(args) >= 2 and isinstance(args[1], str) and args[1].strip():
        return args[1].strip()
    if args and isinstance(args[0], str) and args[0].strip():
        return args[0].strip()
    return str(exc)


def _pool_mysql_rows(sql: str) -> List[Dict[str, Any]]:
    if pymysql is None:
        raise DatabaseError("未安装 PyMySQL，请先 pip install -r app/requirements.txt", 500)
    connection = _acquire_mysql()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(sql)
            rows = _fetch_all(cursor)
        finally:
            cursor.close()
    except pymysql.err.MySQLError as exc:
        if isinstance(exc, (pymysql.err.OperationalError, pymysql.err.InterfaceError)):
            # A dropped pooled connection must not poison the next request.
            _discard_mysql(connection)
            connection = None
        raise DatabaseError(_clean_db_message(exc))
    finally:
        if connection is not None:
            _release_mysql(connection)
    return rows


# --------------------------------------------------------------------------- #
# Exec backend (legacy fallback)
# --------------------------------------------------------------------------- #
def _run_process(command: List[str], timeout: int = 30) -> str:
    completed = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        match = re.search(r"ERROR \d+ \([^)]*\).*?: (.+)", detail)
        raise DatabaseError(match.group(1) if match else detail or "数据库命令失败")
    return completed.stdout


def _exec_mysql_rows(sql: str, timeout: int) -> List[Dict[str, Any]]:
    output = _run_process(MYSQL_BASE + ["-e", sql], timeout)
    if not output.strip():
        return []
    reader = csv.DictReader(io.StringIO(output), delimiter="\t")
    return [{key: (None if value == "NULL" else value) for key, value in row.items()}
            for row in reader]


def _exec_neo4j_rows(cypher: str, timeout: int) -> List[Dict[str, Any]]:
    output = _run_process(NEO4J_BASE + [cypher], timeout)
    if not output.strip():
        return []
    return list(csv.DictReader(io.StringIO(output), skipinitialspace=True))


# --------------------------------------------------------------------------- #
# Neo4j pool backend
# --------------------------------------------------------------------------- #
def _driver():
    global _neo4j_driver
    if GraphDatabase is None:
        raise DatabaseError("未安装 neo4j 驱动，请先 pip install -r app/requirements.txt", 500)
    if _neo4j_driver is None:
        with _neo4j_guard:
            if _neo4j_driver is None:
                _neo4j_driver = GraphDatabase.driver(
                    NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD)
                )
    return _neo4j_driver


def mysql_rows(sql: str, timeout: int = 30) -> List[Dict[str, Any]]:
    if BACKEND == "exec":
        return _exec_mysql_rows(sql, timeout)
    return _pool_mysql_rows(sql)


def neo4j_rows(cypher: str, timeout: int = 30) -> List[Dict[str, Any]]:
    if BACKEND == "exec":
        return _exec_neo4j_rows(cypher, timeout)
    driver = _driver()
    try:
        with driver.session() as session:
            result = session.run(cypher)  # type: ignore[arg-type]
            return [
                {key: _normalize(value) for key, value in record.items()}
                for record in result
            ]
    except DatabaseError:
        raise
    except Exception as exc:
        raise DatabaseError(_clean_db_message(exc))


def health() -> Dict[str, Any]:
    """Lightweight connectivity probe used by ``/api/health`` if desired."""
    return {
        "backend": BACKEND,
        "mysql": {"host": MYSQL_HOST, "port": MYSQL_PORT, "database": MYSQL_DATABASE},
        "neo4j": {"uri": NEO4J_URI},
    }
