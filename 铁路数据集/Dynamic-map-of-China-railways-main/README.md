# Liecheba Scraper (今日车次)

目标网站：`https://www.liecheba.com/`

robots：`User-agent: *` `Allow: /`（见 `https://www.liecheba.com/robots.txt`）

## 输出

运行后生成：

- `data/output/trains_segments.csv`：相邻站点区间（Phase2 仿真直接用）
- `data/output/trains_segments.jsonl`
- `data/output/trains.csv`：车次级汇总（起终站/起终时刻/全程耗时）
- `data/output/stations.csv`：由区间表去重得到的站名及在区间里作为起点/终点的出现次数（`./venv/bin/python3 -m phase1.derive_stations_from_segments`）
- 与参考站表（如 `cnstation.csv`）对比：先做空白规范化再去掉末尾「站」再比键名（`./venv/bin/python3 -m phase1.compare_station_tables`），会写出 `data/output/station_compare_*.csv` 与 `station_compare_summary.txt`。

字段里会带 `crawl_date` 表示“今天这次抓取批次”的日期（注意：站点/车次时刻表本身不是按日期查询的页面）。

## Phase 2：地图与 24 小时仿真

### 快速出图（无需爬虫/无需 Key）

仓库自带 `phase2/web/data/simulation_demo.json`，即使你还没生成 `simulation.json` 也能直接打开地图页面：

```bash
cd phase2/web && python3 -m http.server 8765
```

浏览器打开 `http://127.0.0.1:8765/`。

### 1. 坐标（地理编码）

- **百度地图（默认）**：在 [百度地图开放平台](https://lbsyun.baidu.com/apiconsole/key) 创建应用，申请 **服务端** 的 `ak`，设置环境变量 `BAIDU_MAP_AK` 后运行：
  - `./venv/bin/python3 -m phase2.geocode_stations --provider baidu`
  - 接口返回 **BD-09**，脚本会转为 **WGS84** 供 Leaflet + OSM 底图使用。
  - 可选：`--baidu-city 北京` 等城市限定提高命中率。
- **高德 Web 服务**：在 [高德开放平台](https://lbs.amap.com/) 申请 **Web 服务** Key，设置 `AMAP_API_KEY`，运行 `--provider amap`（GCJ-02 → WGS84）。
- **Nominatim**（免费、无需 Key，请遵守 [使用政策](https://operations.osmfoundation.org/policies/nominatim/)，约 1 请求/秒）：`--provider nominatim`；可选 `NOMINATIM_EMAIL`。
- 结果写入 `data/output/stations_geo.csv`；缓存为 `data/cache/geocode_cache.json`，可断点续跑。

### 2. 合并仿真数据

在已有 `data/output/trains_segments.csv` 与 `data/output/stations_geo.csv` 后：

```bash
./venv/bin/python3 -m phase2.prepare_simulation_data
```

生成 `phase2/web/data/simulation.json`（体积可能较大，已默认 gitignore）。若尚无坐标，地图页会回退加载内置的 `simulation_demo.json`。

### 3. 静态线路 + 时间轴仿真界面

在项目根目录启动本地 HTTP 服务（避免 `file://` 下 `fetch` 失败）：

```bash
cd phase2/web && python3 -m http.server 8765
```

或**一行跑完**（需已设置 `BAIDU_MAP_AK`；无 `#` 注释行，避免 zsh 把 `#` 当命令报错；也不要把多行粘成一行，否则 `#` 后面整段会被当成注释）：

```bash
export BAIDU_MAP_AK="你的百度服务端ak"
./phase2/run_phase2_pipeline.sh
```

若已跑过地理编码，只想合并数据并起服务：

```bash
SKIP_GEOCODE=1 ./phase2/run_phase2_pipeline.sh
```

**zsh 说明**：若你手动粘贴带 `#` 注释的片段，先执行 `setopt interactivecomments`，或只粘贴不含 `#` 的命令行。

浏览器打开 `http://127.0.0.1:8765/`：全国车站与去重区间边线、按时刻表在区间上以**匀速**插值的车次点；底部为 **时间滑块**、**播放/暂停**、**倍速**（0.25×～12×）。

说明：仿真时间轴取「发车日在首日内」的区间（`dep_abs < 1440`）；跨午夜区间按当日 0:00–24:00 折叠处理。

## 安装与运行

```bash
cd "/Users/starry/铁路爬虫"
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 全量（不设上限），按“每个站点 0-24 点遍历候选车次 -> 抓车次详情 -> 导出 segment”
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
./venv/bin/python3 -m phase1.liecheba_scraper \
  --max-train-detail-pages -1 \
  --sleep-min 0.8 --sleep-max 1.8 \
  --timeout-s 12 \
  --retries 3 \
  --db-path data/cache/state.sqlite
```

断点续爬：不要删除 `--db-path` 指向的 SQLite 文件。

## 如果你遇到 HTTPS 证书报错

如果终端出现 `CERTIFICATE_VERIFY_FAILED`，说明你当前网络/VPN 出口的证书链无法被本机校验。可加 `--insecure` 继续抓取：

```bash
env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
./venv/bin/python3 -m phase1.liecheba_scraper --insecure \
  --max-train-detail-pages -1 \
  --sleep-min 0.8 --sleep-max 1.8 \
  --timeout-s 12 \
  --retries 3 \
  --db-path data/cache/state.sqlite
```

# Railway Scraper (Phase 1)

This repo contains the Phase 1 data pipeline for `qq.ip138.com/train/`.

## What it produces

Run Phase 1 to generate:

- `data/output/trains_segments.csv`
- `data/output/trains_segments.jsonl`

These files contain adjacent-stop *segments* extracted from train detail pages, including:

- `train_no`
- `segment_from_station`, `segment_to_station`
- `segment_depart_time_*`, `segment_arrive_time_*` (minute-of-day, day-offset, and absolute minute totals)

## Run

```bash
cd "铁路爬虫"
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python3 -m phase1.ip138_train_scraper --max-train-detail-pages 200 --max-provinces 1 --max-stations-per-province 1
```

## Important scraping policy

The assignment requires checking `robots.txt` before scraping. This project uses a local override file:

- `config/robots_override.txt`

By default, it contains:

- `User-agent: *`
- `Allow: /train/`

If you want stricter enforcement, update `config/robots_override.txt` accordingly.

## “4/1当天（00:00-23:59口径）”全量抓取示例

默认按 00:00-23:59 的时刻筛选车次，并用 `--day-offset-mode zero` 将“当日/次日”统一映射到当日时间轴。

```bash
./venv/bin/python3 -m phase1.ip138_train_scraper \
  --max-train-detail-pages -1 \
  --day-offset-mode zero \
  --sleep-min 0.5 --sleep-max 1.2 \
  --db-path data/cache/phase1_state.sqlite \
  --robots-override config/robots_override.txt
```

如果你希望加速重跑/断点调试，可额外加上 `--cache-html --html-cache-dir data/cache/html`。

