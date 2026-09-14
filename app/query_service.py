"""MySQL + Neo4j 组合查询服务（命令行演示版）。文件编码：UTF-8。"""

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pymysql
from neo4j import GraphDatabase


MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "CR12306",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
}
NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "12345678")


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(type(value).__name__)


def station_id(connection: pymysql.Connection, name: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute("SELECT station_id FROM station WHERE station_name=%s", (name,))
        row = cursor.fetchone()
    if not row:
        raise ValueError(f"未知车站：{name}")
    return int(row["station_id"])


def search_direct(
    connection: pymysql.Connection,
    origin_id: int,
    destination_id: int,
    service_date: str,
    passenger_count: int,
    position: Optional[str],
    fallback: bool,
) -> List[Dict[str, Any]]:
    with connection.cursor() as cursor:
        cursor.callproc(
            "sp_search_direct_trains",
            (origin_id, destination_id, service_date, None, None,
             passenger_count, position, fallback),
        )
        return list(cursor.fetchall())


def graph_transfer_candidates(
    origin_id: int, destination_id: int, service_date: str, limit: int
) -> List[Dict[str, int]]:
    query = """
    MATCH (origin:Station {station_id: $origin_id})
    MATCH (destination:Station {station_id: $destination_id})
    MATCH (first:TrainRun {service_date: $service_date})-[a:CALLS_AT]->(origin)
    MATCH (first)-[b:CALLS_AT]->(transfer:Station)
    WHERE b.station_order > a.station_order
      AND transfer <> origin AND transfer <> destination
    MATCH (second:TrainRun {service_date: $service_date})-[c:CALLS_AT]->(transfer)
    MATCH (second)-[d:CALLS_AT]->(destination)
    WHERE second <> first AND d.station_order > c.station_order
      AND b.arrival_at IS NOT NULL AND c.departure_at IS NOT NULL
      AND c.departure_at > b.arrival_at
    RETURN DISTINCT first.run_id AS firstRunId,
           second.run_id AS secondRunId,
           transfer.station_id AS transferStationId
    LIMIT $limit
    """
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        with driver.session() as session:
            return [dict(record) for record in session.run(
                query,
                origin_id=origin_id,
                destination_id=destination_id,
                service_date=service_date,
                limit=limit,
            )]
    finally:
        driver.close()


def validate_transfers(
    connection: pymysql.Connection,
    candidates: List[Dict[str, int]],
    origin_id: int,
    destination_id: int,
    service_date: str,
    passenger_count: int,
    position: Optional[str],
    fallback: bool,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    with connection.cursor() as cursor:
        cursor.callproc(
            "sp_validate_transfer_candidates",
            (json.dumps(candidates), origin_id, destination_id, service_date,
             15, 240, passenger_count, position, fallback),
        )
        return list(cursor.fetchall())


def main() -> None:
    parser = argparse.ArgumentParser(description="长三角 12306 组合查询演示")
    parser.add_argument("origin", help="出发站名，例如 上海虹桥")
    parser.add_argument("destination", help="到达站名，例如 黄山北")
    parser.add_argument("--date", default="2026-09-07", dest="service_date")
    parser.add_argument("--passengers", type=int, default=1)
    parser.add_argument("--position", choices=list("ABCDF"))
    parser.add_argument("--strict-position", action="store_true")
    parser.add_argument("--transfer-limit", type=int, default=50)
    args = parser.parse_args()

    connection = pymysql.connect(**MYSQL_CONFIG)
    try:
        origin_id = station_id(connection, args.origin)
        destination_id = station_id(connection, args.destination)
        fallback = not args.strict_position
        direct = search_direct(
            connection, origin_id, destination_id, args.service_date,
            args.passengers, args.position, fallback,
        )
        candidates = graph_transfer_candidates(
            origin_id, destination_id, args.service_date, args.transfer_limit
        )
        transfers = validate_transfers(
            connection, candidates, origin_id, destination_id,
            args.service_date, args.passengers, args.position, fallback,
        )
        print(json.dumps(
            {"direct": direct, "oneTransfer": transfers},
            ensure_ascii=False, indent=2, default=json_default,
        ))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
