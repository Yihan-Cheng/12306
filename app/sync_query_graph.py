"""将 MySQL 权威时刻数据投影为 Neo4j 查询图。文件编码：UTF-8。"""

from datetime import date, datetime, time
from typing import Any, Dict, Iterable, List, Tuple

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


def iso(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value


def batches(rows: List[Dict[str, Any]], size: int = 1000) -> Iterable[List[Dict[str, Any]]]:
    for offset in range(0, len(rows), size):
        yield rows[offset : offset + size]


def load_mysql() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    connection = pymysql.connect(**MYSQL_CONFIG)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT tr.run_id, tr.train_no, tr.service_date, t.train_type
                FROM train_run tr JOIN train t ON t.train_no=tr.train_no
                """
            )
            runs = cursor.fetchall()
            cursor.execute(
                """
                SELECT v.run_id, v.station_id, v.station_order,
                       v.arrival_at, v.departure_at
                FROM v_train_run_stop v
                ORDER BY v.run_id, v.station_order
                """
            )
            calls = cursor.fetchall()
    finally:
        connection.close()
    return (
        [{key: iso(value) for key, value in row.items()} for row in runs],
        [{key: iso(value) for key, value in row.items()} for row in calls],
    )


def sync() -> None:
    runs, calls = load_mysql()
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            session.run(
                "CREATE CONSTRAINT train_run_id_unique IF NOT EXISTS "
                "FOR (r:TrainRun) REQUIRE r.run_id IS UNIQUE"
            ).consume()
            session.run(
                "CREATE INDEX train_run_service_date IF NOT EXISTS "
                "FOR (r:TrainRun) ON (r.service_date)"
            ).consume()
            session.run("MATCH (:TrainRun)-[c:CALLS_AT]->() DELETE c").consume()
            session.run("MATCH (r:TrainRun) DELETE r").consume()

            for batch in batches(runs):
                session.run(
                    """
                    UNWIND $rows AS row
                    CREATE (r:TrainRun {
                        run_id: row.run_id,
                        train_no: row.train_no,
                        service_date: row.service_date,
                        train_type: row.train_type
                    })
                    """,
                    rows=batch,
                ).consume()
            for batch in batches(calls):
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (r:TrainRun {run_id: row.run_id})
                    MATCH (s:Station {station_id: row.station_id})
                    CREATE (r)-[:CALLS_AT {
                        station_order: row.station_order,
                        arrival_at: row.arrival_at,
                        departure_at: row.departure_at
                    }]->(s)
                    """,
                    rows=batch,
                ).consume()
        print(f"查询图同步完成：TrainRun={len(runs)}，CALLS_AT={len(calls)}")
    finally:
        driver.close()


if __name__ == "__main__":
    sync()
