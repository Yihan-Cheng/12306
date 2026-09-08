"""
Geocode Chinese railway station names to WGS84 lon/lat.

- baidu: 百度地图地理编码 Web 服务 v3（需 ak）. BD-09 → WGS84.
- amap: 高德 Web Service geocode（需 key）. GCJ-02 → WGS84.
- nominatim: OSM Nominatim（免费、约 1 req/s）. WGS84 直接.

Writes data/output/stations_geo.csv and optional GeoJSON.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

from phase2.coord_transform import bd09_to_wgs84, gcj02_to_wgs84

DEFAULT_STATIONS = "data/output/stations.csv"
DEFAULT_OUT_CSV = "data/output/stations_geo.csv"
DEFAULT_CACHE = "data/cache/geocode_cache.json"


def _load_cache(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(path: str, cache: dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def geocode_amap(
    address: str,
    key: str,
    session: requests.Session,
    timeout: float,
) -> Optional[tuple[float, float, str]]:
    url = "https://restapi.amap.com/v3/geocode/geo"
    r = session.get(
        url,
        params={"key": key, "address": address},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    if str(data.get("status")) != "1":
        return None
    geocodes = data.get("geocodes") or []
    if not geocodes:
        return None
    loc = (geocodes[0].get("location") or "").strip()
    if not loc or "," not in loc:
        return None
    parts = loc.split(",")
    lng_g, lat_g = float(parts[0]), float(parts[1])
    lng, lat = gcj02_to_wgs84(lng_g, lat_g)
    return lng, lat, "amap"


def geocode_baidu(
    address: str,
    ak: str,
    session: requests.Session,
    timeout: float,
    city: str,
) -> Optional[tuple[float, float, str]]:
    """https://lbsyun.baidu.com/faq/api?title=webapi/guide/webservice-geocoding-base"""
    url = "https://api.map.baidu.com/geocoding/v3/"
    params: dict[str, str] = {
        "address": address,
        "output": "json",
        "ak": ak,
    }
    if city.strip():
        params["city"] = city.strip()
    r = session.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if int(data.get("status", -1)) != 0:
        return None
    result = data.get("result") or {}
    loc = result.get("location") or {}
    try:
        lng_bd = float(loc["lng"])
        lat_bd = float(loc["lat"])
    except (KeyError, TypeError, ValueError):
        return None
    lng, lat = bd09_to_wgs84(lng_bd, lat_bd)
    return lng, lat, "baidu"


def geocode_nominatim(
    query: str,
    session: requests.Session,
    timeout: float,
    email: Optional[str],
) -> Optional[tuple[float, float, str]]:
    url = "https://nominatim.openstreetmap.org/search"
    headers = {
        "User-Agent": f"RailwayCrawler/1.0 ({email or 'local-dev@example.com'})",
    }
    r = session.get(
        url,
        params={
            "q": query,
            "format": "json",
            "limit": 1,
            "countrycodes": "cn",
        },
        headers=headers,
        timeout=timeout,
    )
    r.raise_for_status()
    arr = r.json()
    if not arr:
        return None
    it = arr[0]
    lng = float(it["lon"])
    lat = float(it["lat"])
    return lng, lat, "nominatim"


def main() -> None:
    ap = argparse.ArgumentParser(description="Geocode station names to WGS84 coordinates.")
    ap.add_argument("--stations-csv", default=DEFAULT_STATIONS)
    ap.add_argument("--out-csv", default=DEFAULT_OUT_CSV)
    ap.add_argument("--cache", default=DEFAULT_CACHE)
    ap.add_argument(
        "--provider",
        choices=("baidu", "amap", "nominatim"),
        default="baidu",
        help="baidu: BAIDU_MAP_AK or --baidu-ak (default). amap / nominatim 见 README。",
    )
    ap.add_argument(
        "--baidu-ak",
        default=os.environ.get("BAIDU_MAP_AK", ""),
        help="百度地图开放平台「服务端」AK（也可用环境变量 BAIDU_MAP_AK）。",
    )
    ap.add_argument(
        "--baidu-city",
        default="",
        help="可选：城市限定，如 北京 或全国区划代码，提高命中率。",
    )
    ap.add_argument("--amap-key", default=os.environ.get("AMAP_API_KEY", ""))
    ap.add_argument("--nominatim-email", default=os.environ.get("NOMINATIM_EMAIL", ""))
    ap.add_argument(
        "--query-template",
        default="{name}火车站",
        help="Template for search string; {name} is replaced by station_name.",
    )
    ap.add_argument("--sleep-min", type=float, default=0.15)
    ap.add_argument("--sleep-max", type=float, default=0.35)
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true", help="Print first 3 queries only.")
    args = ap.parse_args()

    if args.provider == "baidu" and not args.baidu_ak and not args.dry_run:
        print(
            "Missing Baidu ak: set BAIDU_MAP_AK or pass --baidu-ak "
            "(https://lbsyun.baidu.com/apiconsole/key)",
            file=sys.stderr,
        )
        sys.exit(1)
    if args.provider == "amap" and not args.amap_key:
        print("Missing AMap key: set AMAP_API_KEY or pass --amap-key", file=sys.stderr)
        sys.exit(1)

    cache = _load_cache(args.cache)
    session = requests.Session()

    rows_in: list[dict[str, str]] = []
    with open(args.stations_csv, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows_in.append(row)

    if args.max_rows:
        rows_in = rows_in[: args.max_rows]

    if args.dry_run:
        for row in rows_in[:3]:
            name = (row.get("station_name") or "").strip()
            if not name:
                continue
            q = args.query_template.format(name=name)
            print(f"[dry-run] would query: {q!r}")
        print("Dry run: no file written.")
        return

    out_rows: list[dict[str, Any]] = []
    for i, row in enumerate(rows_in):
        name = (row.get("station_name") or "").strip()
        if not name:
            continue
        cache_key = f"{args.provider}:{name}"
        if cache_key in cache and cache[cache_key].get("lng") is not None:
            c = cache[cache_key]
            out_rows.append(
                {
                    "station_name": name,
                    "lng": c["lng"],
                    "lat": c["lat"],
                    "source": c.get("source", args.provider),
                    "query": c.get("query", ""),
                }
            )
            continue

        query = args.query_template.format(name=name)

        result: Optional[tuple[float, float, str]] = None
        try:
            if args.provider == "baidu":
                result = geocode_baidu(
                    query,
                    args.baidu_ak,
                    session,
                    args.timeout,
                    args.baidu_city,
                )
            elif args.provider == "amap":
                result = geocode_amap(query, args.amap_key, session, args.timeout)
            else:
                result = geocode_nominatim(query, session, args.timeout, args.nominatim_email or None)
        except requests.RequestException as e:
            print(f"[warn] {name}: {e}", file=sys.stderr)
            result = None

        if result:
            lng, lat, src = result
            cache[cache_key] = {"lng": lng, "lat": lat, "source": src, "query": query}
            out_rows.append(
                {
                    "station_name": name,
                    "lng": lng,
                    "lat": lat,
                    "source": src,
                    "query": query,
                }
            )
        else:
            out_rows.append(
                {
                    "station_name": name,
                    "lng": "",
                    "lat": "",
                    "source": "failed",
                    "query": query,
                }
            )
            cache[cache_key] = {"lng": None, "lat": None, "source": "failed", "query": query}

        if (i + 1) % 50 == 0:
            _save_cache(args.cache, cache)

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    Path(args.out_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["station_name", "lng", "lat", "source", "query"],
        )
        w.writeheader()
        for r in out_rows:
            w.writerow(
                {
                    "station_name": r["station_name"],
                    "lng": r["lng"] if r["lng"] != "" else "",
                    "lat": r["lat"] if r["lat"] != "" else "",
                    "source": r["source"],
                    "query": r["query"],
                }
            )

    _save_cache(args.cache, cache)
    ok = sum(1 for r in out_rows if r.get("lng") not in ("", None))
    print(f"Wrote {args.out_csv}: {ok}/{len(out_rows)} with coordinates.")


if __name__ == "__main__":
    main()
