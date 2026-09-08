import pymysql
import pandas as pd
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np

from pypinyin import lazy_pinyin


# ============================================================
# 1. 中文车站名 -> 英文/拼音显示名
# ============================================================

def to_camel_pinyin(text):
    """
    上海 -> ShangHai
    虹桥 -> HongQiao
    """
    if not text:
        return ""

    syllables = lazy_pinyin(str(text))
    return "".join(x.capitalize() for x in syllables)


def station_to_pinyin(station_name, city):
    """
    上海虹桥 + 上海 -> ShangHai HongQiao Station
    南京南 + 南京 -> NanJing Nan Station
    杭州东 + 杭州 -> HangZhou Dong Station
    """

    station_name = str(station_name)
    city = str(city)

    city_py = to_camel_pinyin(city)

    # 如果车站名称以城市名开头
    if station_name.startswith(city):
        remaining = station_name[len(city):]

        if remaining:
            return f"{city_py} {to_camel_pinyin(remaining)} Station"
        else:
            return f"{city_py} Station"

    # 无法拆分时直接整体转拼音
    return f"{to_camel_pinyin(station_name)} Station"


# ============================================================
# 2. 连接 MySQL
# ============================================================

conn = pymysql.connect(
    host="localhost",
    port=3306,
    user="root",
    password="123456",
    database="CR12306",
    charset="utf8mb4"
)


# ============================================================
# 3. 读取车站
# ============================================================

station_sql = """
SELECT
    station_id,
    station_name,
    city
FROM station;
"""

stations = pd.read_sql(station_sql, conn)


# ============================================================
# 4. 读取边
#
# 可视化暂时不区分方向：
# 上海 -> 南京 和 南京 -> 上海
# 在总览图中视作上海--南京
#
# 具体方向仍然完整保存在 train_segment 中
# ============================================================

segment_sql = """
SELECT
    LEAST(from_station_id, to_station_id) AS station_a,
    GREATEST(from_station_id, to_station_id) AS station_b,
    COUNT(DISTINCT train_no) AS train_count
FROM train_segment
GROUP BY
    LEAST(from_station_id, to_station_id),
    GREATEST(from_station_id, to_station_id);
"""

segments = pd.read_sql(segment_sql, conn)

conn.close()


print("车站数量：", len(stations))
print("车站连接数量：", len(segments))


# ============================================================
# 5. 创建无向图
#
# 注意：
# 这里只是“可视化图”
#
# 数据库里的 train_segment 仍然是有方向的。
# ============================================================

G = nx.Graph()


# 添加节点
for _, row in stations.iterrows():

    station_id = int(row["station_id"])

    G.add_node(
        station_id,

        station_name=row["station_name"],

        city=row["city"],

        display_name=station_to_pinyin(
            row["station_name"],
            row["city"]
        )
    )


# 添加边
for _, row in segments.iterrows():

    G.add_edge(
        int(row["station_a"]),
        int(row["station_b"]),

        train_count=int(row["train_count"])
    )


print("图中节点数：", G.number_of_nodes())
print("图中边数：", G.number_of_edges())


# ============================================================
# 6. 去掉完全孤立的车站
# ============================================================

isolated_nodes = list(nx.isolates(G))

G.remove_nodes_from(isolated_nodes)

print("去除孤立节点后：", G.number_of_nodes())


# ============================================================
# 7. 计算节点重要程度
#
# degree = 与多少个其他车站直接相连
# ============================================================

degree_dict = dict(G.degree())


# 按 degree 排序
important_nodes = sorted(
    degree_dict,
    key=degree_dict.get,
    reverse=True
)


# ============================================================
# 8. 只显示最重要的前 35 个车站名称
#
# 否则几百个站名一定会糊成一片
# ============================================================

LABEL_COUNT = 35

label_nodes = set(important_nodes[:LABEL_COUNT])


labels = {
    node: G.nodes[node]["display_name"]
    for node in label_nodes
}


# ============================================================
# 9. 节点大小
#
# 枢纽站连接越多 -> 节点越大
# ============================================================

node_sizes = []

for node in G.nodes():

    degree = degree_dict[node]

    size = 20 + degree * 12

    node_sizes.append(size)


# ============================================================
# 10. 边宽
#
# train_count 越大 -> 线越粗
#
# 使用 log 防止少数超大值把其他边完全压扁
# ============================================================

edge_widths = []

for u, v, data in G.edges(data=True):

    train_count = data["train_count"]

    width = 0.3 + np.log1p(train_count) * 0.35

    edge_widths.append(width)


# ============================================================
# 11. 生成布局
# ============================================================

print("正在计算网络布局...")


# k 越大，节点之间越分散
pos = nx.spring_layout(
    G,

    seed=42,

    k=1.6 / np.sqrt(G.number_of_nodes()),

    iterations=300,

    weight="train_count"
)


# ============================================================
# 12. 开始绘图
# ============================================================

fig, ax = plt.subplots(
    figsize=(24, 18),
    dpi=150
)


# 背景
fig.patch.set_facecolor("#F7F8FA")
ax.set_facecolor("#F7F8FA")


# ------------------------------------------------------------
# 画普通节点
# ------------------------------------------------------------

normal_nodes = [
    node
    for node in G.nodes()
    if node not in label_nodes
]


nx.draw_networkx_nodes(
    G,
    pos,

    nodelist=normal_nodes,

    node_size=[
        node_sizes[list(G.nodes()).index(node)]
        for node in normal_nodes
    ],

    node_color="#9CA3AF",

    alpha=0.55,

    linewidths=0,

    ax=ax
)


# ------------------------------------------------------------
# 画重要节点
# ------------------------------------------------------------

nx.draw_networkx_nodes(
    G,
    pos,

    nodelist=list(label_nodes),

    node_size=[
        80 + degree_dict[node] * 18
        for node in label_nodes
    ],

    node_color="#2563EB",

    edgecolors="white",

    linewidths=1.2,

    alpha=0.9,

    ax=ax
)


# ------------------------------------------------------------
# 绘制边
# ------------------------------------------------------------

nx.draw_networkx_edges(
    G,
    pos,

    width=edge_widths,

    edge_color="#CBD5E1",

    alpha=0.38,

    ax=ax
)


# ------------------------------------------------------------
# 重要站名称
# ------------------------------------------------------------

nx.draw_networkx_labels(
    G,
    pos,

    labels=labels,

    font_size=8,

    font_weight="medium",

    font_color="#111827",

    ax=ax
)


# ============================================================
# 13. 标题
# ============================================================

ax.set_title(
    "Yangtze River Delta Railway Operation Network",
    fontsize=24,
    fontweight="bold",
    pad=25
)

ax.text(
    0.5,
    1.01,

    "Node size = connectivity   |   Edge width = number of trains",

    transform=ax.transAxes,

    horizontalalignment="center",

    fontsize=11,

    color="#6B7280"
)


ax.axis("off")


plt.tight_layout()


# ============================================================
# 14. 保存高清图片
# ============================================================

plt.savefig(
    "railway_network.png",
    dpi=300,
    bbox_inches="tight"
)


plt.show()