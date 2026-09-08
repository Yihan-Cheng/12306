# -*- coding: utf-8 -*-
"""从 train.csv 抽取上海虹桥站时刻表，做站台/检票口分配，输出前端可内置的数据。"""
import csv, json, collections

SRC = 'train.csv'
STATION = '上海虹桥'
PLATFORMS = 30
LOOKAHEAD = 120  # 大屏展示未来 120 分钟内出发的车次


def m(s):
    h, mm = s.split(':')
    return int(h) * 60 + int(mm)


def fmt(v):
    return '%02d:%02d' % (v // 60, v % 60)


rows = list(csv.DictReader(open(SRC, encoding='utf-8-sig')))
by_train = collections.defaultdict(list)
for r in rows:
    by_train[r['train_no']].append(r)

hq = [r for r in rows if r['station_name'] == STATION]

trains = []
for r in hq:
    seq = sorted(by_train[r['train_no']], key=lambda x: int(x['station_order']))
    a = None if r['arrival_time'] == 'NULL' else m(r['arrival_time'])
    d = None if r['departure_time'] == 'NULL' else m(r['departure_time'])
    # 占用区间：始发车提前 25 分钟上客；终点车到点后 20 分钟清客
    s = a if a is not None else d - 25
    e = d if d is not None else a + 20
    trains.append(dict(
        no=r['train_no'], typ=r['train_type'],
        orig=seq[0]['station_name'], dest=seq[-1]['station_name'],
        a=a, d=d, s=s, e=e,
    ))

trains.sort(key=lambda x: (x['s'], x['d'] if x['d'] is not None else x['a']))

# ---- 站台分配：贪心 + 最少最近使用，保证同站台时间窗不重叠 ----
plat_end = [0] * (PLATFORMS + 1)   # plat_end[p] = 该站台上一列车驶离时刻
plat_use = [0] * (PLATFORMS + 1)
assign_fail = 0
for t in trains:
    free = [p for p in range(1, PLATFORMS + 1) if plat_end[p] <= t['s']]
    if not free:
        assign_fail += 1
        t['plat'] = 0
        t['gate'] = '--'
        continue
    # 优先选空闲最久（end 最小）且总使用次数最少的站台，使占用均衡
    p = min(free, key=lambda p: (plat_use[p], plat_end[p], p))
    plat_end[p] = t['e']
    plat_use[p] += 1
    t['plat'] = p
    t['gate'] = '%d%s' % (p, 'A' if plat_use[p] % 2 else 'B')

# 校验：同站台任意两车时间窗不重叠
by_plat = collections.defaultdict(list)
for t in trains:
    by_plat[t['plat']].append(t)
overlap = 0
for p, lst in by_plat.items():
    lst.sort(key=lambda x: x['s'])
    for i in range(1, len(lst)):
        if lst[i]['s'] < lst[i - 1]['e']:
            overlap += 1

# ---- 峰值并发 / 大屏行数评估 ----
pts = sorted([(t['s'], 1) for t in trains] + [(t['e'], -1) for t in trains])
c = mx = 0
for _, dd in pts:
    c += dd
    mx = max(mx, c)


def board_size(now):
    n = 0
    for t in trains:
        if t['d'] is not None:
            if now < t['d'] <= now + LOOKAHEAD:
                n += 1
        else:
            if t['a'] <= now < t['a'] + 5:
                n += 1
    return n


peak_rows = max(board_size(x) for x in range(300, 1440))

meta = dict(
    station=STATION, platforms=PLATFORMS, total=len(trains),
    assign_fail=assign_fail, overlap=overlap, max_concurrent=mx,
    peak_rows=peak_rows, lookahead=LOOKAHEAD,
)
print(json.dumps(meta, ensure_ascii=False))
print('per-platform load:', sorted(collections.Counter(t['plat'] for t in trains).items()))

out = [dict(
    n=t['no'], y=t['typ'], o=t['orig'], g=t['dest'],
    a=(None if t['a'] is None else fmt(t['a'])),
    d=(None if t['d'] is None else fmt(t['d'])),
    am=t['a'], dm=t['d'], s=t['s'], e=t['e'], p=t['plat'], k=t['gate'],
) for t in trains]
out.sort(key=lambda x: (x['d'] is None, x['d'] or x['s']))

json.dump(dict(meta=meta, trains=out), open('board_data.json', 'w', encoding='utf-8'),
          ensure_ascii=False, separators=(',', ':'))
print('wrote board_data.json', len(out))
