import pandas as pd
import pymysql

# 1. 读取 CSV
train_station_path = r"E:\学习\2026秋季学期（大三上）\数据库系统\12306\铁路数据集\output\train_station.csv"

df = pd.read_csv(train_station_path)

print("读取到的数据：")
print(df.head())

print(f"共 {len(df)} 条车次停站记录")

# 2. 将 NaN 转换成 None
# 这样才能正确写入 MySQL 的 NULL
df = df.where(pd.notnull(df), None)

# 3. 连接 MySQL
conn = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="123456",
    database="CR12306",
    charset="utf8mb4"
)

cursor = conn.cursor()

# 4. 插入数据
sql = """
INSERT INTO train_station
(train_no, station_order, station_id, arrival_time, departure_time)
VALUES (%s, %s, %s, %s, %s)
"""

for _, row in df.iterrows():
    cursor.execute(
        sql,
        (
            row["train_no"],
            int(row["station_order"]),
            int(row["station_id"]),
            row["arrival_time"],
            row["departure_time"]
        )
    )

# 5. 提交
conn.commit()

print("train_station 数据导入成功！")

# 6. 关闭
cursor.close()
conn.close()