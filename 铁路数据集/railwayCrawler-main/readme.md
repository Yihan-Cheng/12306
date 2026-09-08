How to use this data generator?
- In linux environment, execute reptile.py to retrieve data from http://cnrail.geogv.org/zhcn/about, which are located in folder stations. It's worth noting that bad internet connection, to some extent, cramp the data-generating step.
- Then, run generator.py to convert raw data to formated data.

Here below are some discussions about the details in data-generating step. (can be skipped.)
- stations/*.csv: each station's schedule. Each item represents a train passing the correspoding railway station.
  
  Each column respectively represents: train type(列车类型：普快、快速、直达特快、高速动车、动车组、城际动车、国际联运、旅游), status(始/过/终), train number(车次), departure station(始发站), terminus(终点站), arrival time(到达本站时间), departure time(驶离本站时间).

- railways/railways.csv: railway lines listed with its construction time, design speed, two ends of the line, and of course its name
  
  Each column respectively represents: 线路、线路类型、现设计时速、电气化与否、建成年份、起点、终点、途径站点。
  
  Some railways are divided into subintervals because of three reasons.
    1. No trains run through the entire interval now. For example, due to safety reasons (earthquakes), no trains now travel from 成都 to 昆明 (成昆铁路). 
    2. Construction may not be a one-time completion. For example, 京广高铁 should be divided into several subintervals: 京石客运专线(2012.9), 石武客运专线(2012.12)，武广客运专线(2009.12)
    3. The starting stations of some railways are pretty small (no passenger service 无客运), approximation is imperative here to reduce excessive annotation work. For instance, 新月铁路(新乡-月山) is recorded as 新乡-焦作.

- names/names.csv:
  Some major cities have multiple railway stations in downtown. Though stations are often named as 'CityName + Direction' like '北京南', however, some are named as Cityname + VillageName, such as '上海虹桥' or '洛阳潼关'. In some scenarios, you will even have no idea about where the station is located when given their irregular names like '宋城路'(开封), '福田'(深圳). Those stations with irregular names are listed in names.csv, where the first column stands for stations and the second for belonging cities.

Here remains the crux of the problem: How can we extract weight bewteen any two given nodes? Intuitively, we assign the length of the shortest travel path to every edge. In addition, some details are prompt to be clarified.

    1. How do we define nodes? One option is to regard each station as a node. But this will bring us into trouble: If one city has multiple stations, there might be some linking-up lines to connect them (联络线), which needs dimunitive annotation on the railway network. To reduce mannual annotation, it's better to avert station-grained design. (However, when we are dealing with 24-hour connectivity problem, station-grained graph is acceptable, because we no longer care about the completion dates of each railway lines.) So we choose to take cities as nodes.

    2. How can we sort route sites of a given train in chronological order? Raw data only tells us: when and where will a train arrive at which station. We definitely know the route sites of each train (G1:{济南西,北京南,上海虹桥,南京南}), but don't know the order (G1:北京南-济南西-南京南-上海虹桥). It seems that we can sort by arrival time, but arrival time is in format of HH:MM, while some trains travel for more than 24 hours. It's a fatal problem. At the end, we decide to cope this problem with manual annotations.