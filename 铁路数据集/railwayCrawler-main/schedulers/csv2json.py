# -*- coding: utf-8 -*-
import csv, json, os
keys = ['station', 'service', 'type', 'train', 'from', 'to', 'arrival', 'departure']

with open('../keystations.txt', 'r', encoding='utf-8') as f:
    stations = eval(f.read())

schedulers = []

for station in stations:
    if not os.path.isfile(station + '.csv'):
        print('{}.csv not found'.format(station))
        continue

    with open(station + '.csv', 'r', encoding='gbk') as f:
        reader = csv.reader(f)
        sched = list(reader)

    schedulers += [dict(zip(keys, [station] + train)) for train in sched]

with open('../schedulers.json', 'w', encoding='gbk') as f:
    #js = json.dumps({'schedulers': schedulers}, ensure_ascii = False)
    js = json.dumps(schedulers, ensure_ascii = False)
        # shown in chinese character instead of \uxxx
    json.dump(js, f)

#with open('stations.json', 'r') as f:
#    printf(json.load(f))
    
