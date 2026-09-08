# -*- coding: utf-8 -*-
import csv, json, os
line_keys = ['name', 'service', 'speed', 'electrification', 'date', 'start', 'end', 'route']
item_keys = ['service', 'type', 'train', 'start', 'end', 'arrival', 'departure']
train_keys = ['service', 'start', 'end']
inf = 1440 * 10

def csv_reader(name):
    with open(name, 'r', encoding = 'gbk') as f:
        raw = list(csv.reader(f))
    return raw

def json_printer(name, data):
    with open(name, 'w', encoding = 'utf-8') as f:
        js = json.dumps(data, ensure_ascii = False)
        json.dump(js, f)
    
def read_schedulers():
    schedulers = dict()
    station_list = []
    for file in os.listdir('schedulers'):
        if file[-4:] != '.csv': continue
        station = file[:-4]
        station_list.append(station)
        raw = csv_reader('schedulers/' + file)

        for line in raw:
            item = dict(zip(item_keys, line[:len(item_keys)]))
            train = item['train']
            if train not in schedulers:
                schedulers[train] = {key: item[key] for key in train_keys}
                schedulers[train]['route'] = []
            schedulers[train]['route'].append({'station': station, 'arrival': item['arrival'], 'departure': item['departure']})
    return schedulers, station_list

def read_railways(station_list):
    network = dict()
    raw = csv_reader('railways/railways.csv')
    for line in raw[1:]: # omit heading
        item = dict(zip(line_keys, line[:len(line_keys)])) # omit marks
        name = item['name']
        network[name] = {key: item[key] for key in line_keys[1: -1]}
        route = item['route'].split('-')
        network[name]['route'] = []
        for station in route:
            if station in station_list: network[name]['route'].append(station)
        if len(network[name]['route']) <= 1:
            print('remove', name)
            del network[name]
    return network

def read_selected():
    with open('keystations.txt', 'r', encoding = 'utf-8') as f:
        selected = eval(f.readline())
    return selected

def read_citys(station_list):
    dictionary, station2index = dict(), dict()
    city_list, numCities = dict(), 0
    raw = csv_reader('names/names.csv')
    for line in raw: # omit heading
        dictionary[line[0]] = line[1]
    for station in station_list:
        if station not in dictionary:
            city = station
            if len(station) > 2 and station[-1] in ['北', '东', '西', '南', '站']:
                city = station[:-1]
            dictionary[station] = city
    
    for station, city in dictionary.items():
        if city not in city_list:
            city_list[city] = numCities
            numCities += 1
        station2index[station] = city_list[city]
        
    return dictionary, station2index, city_list

def get_inv(dictionary):
    dictionary_inv = dict()
    for key, value in dictionary.items():
        if value not in dictionary_inv:
            dictionary_inv[value] = [key]
        else:
            dictionary_inv[value].append(key)
    return dictionary_inv
    

def min2hhmm(min):
    return str(min // 60) + ":" + str(min % 60).zfill(2)
def hhmm2min(hhmm):
    return int(hhmm[:-3]) * 60 + int(hhmm[-2:])
def nextday(hhmm, days):
    return min2hhmm(days * 1440 + hhmm2min(hhmm))
def get_time(hhmm1, hhmm2):
    min1, min2 = hhmm2min(hhmm1), hhmm2min(hhmm2)
    while min2 <= min1: min2 += 1440
    return min2hhmm(min2)
def dif(hhmm1, hhmm2):
    x, y = hhmm2min(hhmm1), hhmm2min(hhmm2)
    assert x < 1440 and y < 1440
    return y - x + 1440 if y - x < 0 else y - x

def yymmdd(str):
    data = str.split('.')
    if len(data) == 1: return int(data[0]), 0, 0
    if len(data) == 2: return int(data[0]), int(data[1]), 0
    return int(data[0]), int(data[1]), int(data[2])

def max_date(x, y):
    yy1, mm1, dd1 = yymmdd(x)
    yy2, mm2, dd2 = yymmdd(y)
    if yy1 != yy2: return x if yy1 > yy2 else y
    if mm1 != mm2: return x if mm1 > mm2 else y
    return x if dd1 > dd2 else y

def floyd(g, g_ext, n):
    for k in range(n):
        for i in range(n):
            if (g[i][k] == inf): continue
            for j in range(n):
                if g[i][j] > g[i][k] + g[k][j]:
                    g[i][j] = g[i][k] + g[k][j]
                    g_ext[i][j] = max_date(g_ext[i][k], g_ext[k][j])

service = {'普速铁路': ['普快', '快速', '直达特快', '特快', '普客'], '快速铁路': ['动车组', '城际动车', '市郊动车'], '高速铁路': ['高速动车']}
service_inv = dict()
for key, values in service.items():
    for value in values:
        service_inv[value] = key

def construct_graph(raw_schedulers, station2index, network):
    numStations = len(station2index.keys())
    railways = [[ dict() for i in range(numStations)] for j in range(numStations)]
    for name, line in network.items():
        for u, v in zip(line['route'][:-1], line['route'][1:]):
            _u, _v = station2index[u], station2index[v]
            if line['service'] not in railways[_u][_v]:
                railways[_u][_v][line['service']] = name
            if line['service'] not in railways[_v][_u]:
                railways[_v][_u][line['service']] = name

    graph, graph_ext = dict(), dict()
    for railway_type in service.keys():
        graph[railway_type] = [[inf if i != j else 0 for i in range(numStations)] for j in range(numStations)]
        graph_ext[railway_type] = [["2050" if i != j else "0" for i in range(numStations)] for j in range(numStations)]


    '''
    for train, item in raw_schedulers.items():
        tmp_record = {station['station']: station for station in item['route']}
        for _, line in network.items():
            g, g_ext = graph[line['service']], graph_ext[line['service']]
            if item['service'] not in service[line['service']]: continue
            for u, v in zip(line['route'][:-1], line['route'][1:]):
                if u in tmp_record and v in tmp_record:
                    _u, _v = station2index[u], station2index[v]
                    if tmp_record[u]['departure'] != '-' and tmp_record[v]['arrival'] != '-':
                        cost = dif(tmp_record[u]['departure'], tmp_record[v]['arrival'])
                        if g[_u][_v] > cost:
                            g[_u][_v], g_ext[_u][_v] = cost, line['date']
                    if tmp_record[v]['departure'] != '-' and tmp_record[u]['arrival'] != '-':
                        cost = dif(tmp_record[v]['departure'], tmp_record[u]['arrival'])
                        if g[_v][_u] > cost:
                            g[_v][_u], g_ext[_v][_u] = cost, line['date']
    '''
    
    
    for train, item in raw_schedulers.items():
        tmp_record = {station['station']: station for station in item['route']}
        for u in station2index.keys():
            if u not in tmp_record: continue
            for v in station2index.keys():
                if v not in tmp_record or u == v: continue

                _u, _v = station2index[u], station2index[v]
                if item['service'] not in service_inv: continue # print(item['service'])
                train_service = service_inv[item['service']]
                status = railways[_u][_v]
                if len(status) < 1: continue

                def update(service, date):
                    if graph[service][_u][_v] > cost:
                        graph[service][_u][_v], graph_ext[service][_u][_v] = cost, date

                K, D, G = '普速铁路', '快速铁路', '高速铁路'

                if len(status) == 3:
                    pass # print(u, v, status[K], status[D], status[G])

                if tmp_record[u]['departure'] != '-' and tmp_record[v]['arrival'] != '-':
                    cost = dif(tmp_record[u]['departure'], tmp_record[v]['arrival'])
                    assert train_service in [K, D, G]
                    if train_service == K:
                        if K in status:
                            update(K, network[status[K]]['date'])
                            update(D, network[status[K]]['date'])
                        elif D in status:
                            update(K, network[status[D]]['date'])
                    else:
                        if D not in status and G not in status:
                            update(D, network[status[K]]['date'])
                            continue
                        if D in status and G in status:
                            update(train_service, network[status[train_service]]['date'])
                        else:
                            date = network[status[D]]['date'] if D in status else network[status[G]]['date']
                            update(G, date), update(D, date)
                        # if K not in status and D in status:
                        #    update(K, network[status[D]]['date'])

                
    
    for key in graph.keys():
        floyd(graph[key], graph_ext[key], numStations)
    return graph, graph_ext 


def refine_schedulers(raw_schedulers, station2index, network, graph, graph_ext): # based on rough assumption: every adjacent route sites of one train must belong only to one railway line
    print("Refinement..")
    schedulers = dict()
    for train, item in raw_schedulers.items():
        if len(item['route']) <= 1: continue
        date, route = [], []
        tmp_record = {station['station']: station for station in item['route']}
        if item['service'] not in service_inv: continue
        train_service = service_inv[item['service']]
        rev = False

        def get_dis(x, y):
            return graph[train_service][x][y], graph_ext[train_service][x][y]
        
        def get_run_dis(x, y):
            _u = station2index[x['station']]
            _v = station2index[y['station']]
            d, date = get_dis(_u, _v)
            drun = inf
            if not rev:
                drun = dif(x['departure'], y['arrival'])
            else:
                drun = dif(y['departure'], x['arrival'])
            # print(d, drun)
            while drun + 290 < d: drun += 1440
            return drun, date

        def get_diameter(route):
            dia, b, e = 0, 'null', 'null'
            for i in route:
                for j in route:
                    d, _ = get_run_dis(i, j)
                    if d > dia: dia, b, e = d, i['station'], j['station']
            return b, e
        
        def get_next(now):
            # print('finding next of', route[-1]['station'])
            nxt, dis, date = 'null', inf, "2050"
            for name, station in tmp_record.items():
                _dis, _date = get_run_dis(now, station)
                # print(name, ":", _dis)
                if _dis < dis: nxt, dis, date = name, _dis, _date
            return nxt, date
        
        b, e = None, None
        for station in item['route']:
            if station['arrival'] == '-': b = station['station']
            if station['departure'] == '-': e = station['station']
        if not b and not e:
            # print('skip', train) # skip
            continue
            b, e = get_diameter(item['route'])
        elif not b:
            b, rev = e, True
        
        route = [tmp_record.pop(b)]
        while len(tmp_record) > 0:
            now = route[-1]
            nxt, nxt_date = get_next(route[-1])
            # date = max_date(date, _date)
            nxt_item = tmp_record.pop(nxt)
            if station2index[nxt] != station2index[now['station']]:
                route.append(nxt_item)
                date.append(nxt_date)
        
        if len(route) <= 1: continue

        if rev: route.reverse()

        '''
        for u, v, in zip(route[:-1], route[1:]):
            _u, _v = station2index[u['station']], station2index[v['station']]
            dis, date = get_dis(_u, _v)
            if dis < 480:
                assert dif(u['departure'], v['arrival']) < 720
        '''

        '''
        flag = True
        for u, v, in zip(route[:-1], route[1:]):
            _u, _v = station2index[u['station']], station2index[v['station']]
            dis, date = get_dis(_u, _v)
            if dis < 480:
                if not dif(u['departure'], v['arrival']) < 720: flag = False
        if not flag:
            print(route)
            print(train)
            # assert(False)
            continue
        '''
        
        for i in range(len(route)):
            if i > 0:
                route[i]['arrival'] = get_time(route[i - 1]['departure'], route[i]['arrival'])
            if route[i]['arrival'] != '-' and route[i]['departure'] != '-':
                route[i]['departure'] = get_time(route[i]['arrival'], route[i]['departure'])
        item['route'], item['date'] = route, date
        schedulers[train] = item

    return schedulers

def print_schedulers(schedulers, dictionary, selected):
    result = dict()
    for key in schedulers.keys():
        route, date = [], []
        item = schedulers[key]

        station = item['route'][0]
        city = dictionary[station['station']]
        last_date, first_station = "1800", True
        if not selected or city in selected:
            station['city'] = city
            del station['station']
            route.append(station)
            first_station = False

        for sub_date, station in zip(item['date'], item['route'][1:]):
            last_date = max_date(last_date, sub_date)
            city = dictionary[station['station']]
            if not selected or city in selected:
                station['city'] = city
                del station['station']
                route.append(station)
                if first_station:
                    first_station = False
                else:
                    date.append(last_date)
                last_date = "1800"

        if len(route) > 1:
            item['route'] = route
            item['date'] = date
            result[key] = item
            assert len(route) == len(date) + 1
    print(result)
    json_printer('schedulers.json', result)

def print_network(network, dictionary, selected):
    result = dict()
    for key in network.keys():
        route = []
        item = network[key]
        for station in item['route']:
            city = dictionary[station]
            if not selected or city in selected:
                route.append(city)
        if len(route) > 1:
            item['route'] = route
            result[key] = item
    # print(result)
    json_printer('network.json', result)
    

schedulers, station_list = read_schedulers()
network = read_railways(station_list)
selected = read_selected()
dictionary, station2index, _ = read_citys(station_list)
# dictionary_inv = get_inv(dictionary)
graph, graph_ext = construct_graph(schedulers, station2index, network)
schedulers = refine_schedulers(schedulers, station2index, network, graph, graph_ext)
# selected = []
print_schedulers(schedulers, dictionary, selected)
print_network(network, dictionary, selected)

'''
def query(x, y):
    u = station2index[x]
    v = station2index[y]
    for key in service.keys():
        if graph[key][u][v] != inf:
            print(x, y, key, graph[key][u][v])

def get_city(x):
    for key, item in station2index.items():
        if item == x: return key
for x in []:
    print(x, station2index[x])
query('阜阳', '商丘')
query('阜阳', '菏泽')
query('商丘', '菏泽')
exit(0)
'''