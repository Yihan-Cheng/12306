import pymysql
import pandas as pd
from neo4j import GraphDatabase


# ============================================================
# 1. MySQL 配置
# ============================================================

mysql_conn = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="123456",
    database="CR12306",
    charset="utf8mb4"
)


# ============================================================
# 2. Neo4j 配置
# ============================================================

neo4j_uri = "bolt://localhost:7687"
neo4j_user = "neo4j"
neo4j_password = "12345678"

driver = GraphDatabase.driver(
    neo4j_uri,
    auth=(neo4j_user, neo4j_password)
)


# ============================================================
# 3. 从 MySQL 读取 station
# ============================================================

station_sql = """
SELECT
    station_id,
    station_name,
    city
FROM station;
"""

stations = pd.read_sql(station_sql, mysql_conn)

print(f"读取到 {len(stations)} 个车站")


# ============================================================
# 4. 从 MySQL 读取 train_segment
# ============================================================

segment_sql = """
SELECT
    segment_id,
    train_no,
    from_station_id,
    to_station_id,
    from_order,
    to_order,
    departure_time,
    arrival_time
FROM train_segment;
"""

segments = pd.read_sql(segment_sql, mysql_conn)

print(f"读取到 {len(segments)} 条车次区间")


mysql_conn.close()


# ============================================================
# 5. 创建 Station 唯一约束
# ============================================================

with driver.session() as session:

    session.run("""
    CREATE CONSTRAINT station_id_unique IF NOT EXISTS
    FOR (s:Station)
    REQUIRE s.station_id IS UNIQUE
    """)

print("Station 唯一约束创建完成")


# ============================================================
# 6. 导入 Station 节点
# ============================================================

station_records = stations.to_dict("records")

with driver.session() as session:

    session.run("""
    UNWIND $rows AS row

    MERGE (s:Station {station_id: row.station_id})

    SET
        s.station_name = row.station_name,
        s.city = row.city
    """, rows=station_records)

print("Station 节点导入完成")


# ============================================================
# 7. 处理时间字段
# ============================================================

def time_to_string(value):

    if pd.isna(value):
        return None

    return str(value)


segments["departure_time"] = segments["departure_time"].apply(time_to_string)
segments["arrival_time"] = segments["arrival_time"].apply(time_to_string)


# ============================================================
# 8. 导入 TRAIN_SEGMENT 关系
# ============================================================

segment_records = segments.to_dict("records")

with driver.session() as session:

    session.run("""
    UNWIND $rows AS row

    MATCH (from:Station {station_id: row.from_station_id})
    MATCH (to:Station {station_id: row.to_station_id})

    CREATE (from)-[:TRAIN_SEGMENT {
        segment_id: row.segment_id,
        train_no: row.train_no,
        from_order: row.from_order,
        to_order: row.to_order,
        departure_time: row.departure_time,
        arrival_time: row.arrival_time
    }]->(to)
    """, rows=segment_records)

print("TRAIN_SEGMENT 关系导入完成")


# ============================================================
# 9. 关闭 Neo4j
# ============================================================

driver.close()

print("MySQL -> Neo4j 导入全部完成！")