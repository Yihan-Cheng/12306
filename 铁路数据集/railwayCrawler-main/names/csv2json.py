# -*- coding: utf-8 -*-
import csv, json, os
keys = ['station', 'service', 'type', 'train', 'from', 'to', 'arrival', 'departure']

with open('../keystations.txt', 'r', encoding='utf-8') as f:
    stations = eval(f.read())

schedulers = []


with open('name' + '.csv', 'r', encoding='gbk') as f:
    reader = csv.reader(f)
    csvfile = list(reader)

name2city = {}

for pair in csvfile:
    name2city[pair[0]] = pair[1]

for station in stations:
    if not name2city.__contains__(station):
        name2city[station] = station[:-1] if station[-1] in ['站', '东', '南', '西', '北'] else station

with open('../station2city.json', 'w', encoding='gbk') as f:
    js = json.dumps(name2city, ensure_ascii = False)
        # shown in chinese character instead of \uxxx
    json.dump(js, f)

#with open('stations.json', 'r') as f:
#    printf(json.load(f))
    
