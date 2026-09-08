"""
Build Phase2 stations_geo.csv using:
1) existing cnstation.csv rows (for stations already covered)
2) Baidu geocoding only for station names missing in cnstation

This avoids wasting Baidu quota on stations that already have coordinates.

Outputs:
- data/output/stations_geo.csv (fields: station_name,lng,lat,source,query,address?)
- data/output/cnstation_missing_from_segments.csv (only the missing station names)
- data/output/cnstation_completed.csv (merge: cnstation.backup + baidu missing; best-effort)
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

from phase1.parsers import normalize_station_name
from phase2.coord_transform import bd09_to_gcj02, bd09_to_wgs84


def canonical_key(name: str) -> str:
    t = normalize_station_name(name)
    while t.endswith("站"):
        t = t[:-1]
    return normalize_station_name(t)


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")


def baidu_geocode_bd09_to_wgs84(
    *,
    session: requests.Session,
    ak: str,
    query: str,
    timeout: float,
    city: str,
) -> Optional[dict[str, Any]]:
    """
    Returns dict with:
      bd_lng, bd_lat, gcj_lng, gcj_lat, wgs_lng, wgs_lat, address
    """
    url = "https://api.map.baidu.com/geocoding/v3/"
    params: dict[str, str] = {
        "address": query,
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
        bd_lng = float(loc["lng"])
        bd_lat = float(loc["lat"])
    except (KeyError, TypeError, ValueError):
        return None

    gcj_lng, gcj_lat = bd09_to_gcj02(bd_lng, bd_lat)
    wgs_lng, wgs_lat = bd09_to_wgs84(bd_lng, bd_lat)
    addr = (result.get("formatted_address") or result.get("address") or "").strip()

    return {
        "bd_lng": bd_lng,
        "bd_lat": bd_lat,
        "gcj_lng": gcj_lng,
        "gcj_lat": gcj_lat,
        "wgs_lng": wgs_lng,
        "wgs_lat": wgs_lat,
        "address": addr,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Only geocode missing stations for Phase2.")
    ap.add_argument("--stations-csv", default="data/output/stations.csv")
    ap.add_argument("--cnstation-csv", default="data/output/cnstation.csv.backup.csv")
    ap.add_argument("--out-geo-csv", default="data/output/stations_geo.csv")
    ap.add_argument("--out-missing-csv", default="data/output/cnstation_missing_from_segments.csv")
    ap.add_argument("--out-cn-completed-csv", default="data/output/cnstation_completed.csv")
    ap.add_argument("--cache", default="data/cache/baidu_geocode_cache.json")

    ap.add_argument("--query-template", default="{name}站")
    ap.add_argument("--baidu-city", default="", help="Optional: city constraint for Baidu (e.g. 北京).")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--sleep-min", type=float, default=0.15)
    ap.add_argument("--sleep-max", type=float, default=0.35)
    ap.add_argument("--baidu-retries", type=int, default=3, help="Baidu request retry count per station.")
    ap.add_argument("--max-missing", type=int, default=None, help="For testing: cap missing rows.")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be geocoded.")

    ap.add_argument("--baidu-ak", default=os.environ.get("BAIDU_MAP_AK", ""))
    args = ap.parse_args()

    if not args.baidu_ak and not args.dry_run:
        print("Missing BAIDU_MAP_AK env or --baidu-ak.", file=sys.stderr)
        sys.exit(1)

    stations_path = Path(args.stations_csv)
    cn_path = Path(args.cnstation_csv)

    def build_query(station_name: str) -> str:
        """
        User requirement: for stations.csv name, search with a trailing "站" suffix.
        Avoid duplicates when station_name already endswith "站".
        """
        station_name = (station_name or "").strip()
        tpl = (args.query_template or "").strip()
        if tpl == "{name}站":
            if station_name.endswith("站"):
                return station_name
            return station_name + "站"
        return tpl.format(name=station_name)

    if not stations_path.exists():
        raise FileNotFoundError(stations_path)
    if not cn_path.exists():
        raise FileNotFoundError(cn_path)

    # key -> best available coord row from cnstation
    cn_map: dict[str, dict[str, str]] = {}
    cn_fieldnames: list[str] = []
    with open(cn_path, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        cn_fieldnames = list(r.fieldnames or [])
        for row in r:
            raw_name = (row.get("站名") or "").strip()
            if not raw_name:
                continue
            k = canonical_key(raw_name)
            wgs_lng = (row.get("WGS84_Lng") or "").strip()
            wgs_lat = (row.get("WGS84_Lat") or "").strip()
            if not wgs_lng or not wgs_lat:
                continue
            # Keep first occurrence (or you can change strategy if needed)
            if k not in cn_map:
                cn_map[k] = row

    # Decide which stations are missing
    geo_out_rows: list[dict[str, Any]] = []
    missing_names: list[str] = []
    missing_keys: set[str] = set()

    with open(stations_path, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            name = (row.get("station_name") or "").strip()
            if not name:
                continue
            k = canonical_key(name)
            if k in cn_map:
                cn_row = cn_map[k]
                geo_out_rows.append(
                    {
                        "station_name": name,
                        "lng": cn_row.get("WGS84_Lng") or "",
                        "lat": cn_row.get("WGS84_Lat") or "",
                        "source": "cnstation",
                        "query": "",
                        "address": (cn_row.get("车站地址") or "").strip(),
                    }
                )
            else:
                missing_names.append(name)
                missing_keys.add(k)

    # De-duplicate missing by canonical key, but keep first raw name
    missing_unique: list[str] = []
    seen_k: set[str] = set()
    for n in missing_names:
        k = canonical_key(n)
        if k in seen_k:
            continue
        seen_k.add(k)
        missing_unique.append(n)

    if args.max_missing is not None:
        missing_unique = missing_unique[: args.max_missing]

    # Save missing list for transparency
    with open(args.out_missing_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["station_name", "canonical_key"])
        for n in missing_unique:
            w.writerow([n, canonical_key(n)])

    if args.dry_run:
        print(f"Missing {len(missing_unique)} stations (dry-run). Missing list: {args.out_missing_csv}")
        return

    cache_path = Path(args.cache)
    cache = _load_cache(cache_path)
    session = requests.Session()

    # Geocode missing
    missing_geo: dict[str, dict[str, Any]] = {}  # canonical_key -> coords
    retries = max(1, int(args.baidu_retries))
    for idx, name in enumerate(missing_unique):
        k = canonical_key(name)
        query = build_query(name)
        cache_key = f"baidu:{query}"

        cached = cache.get(cache_key)
        if isinstance(cached, dict) and cached.get("wgs_lng") is not None:
            missing_geo[k] = cached
        else:
            res = None
            last_err: Optional[Exception] = None
            for attempt in range(retries):
                try:
                    res = baidu_geocode_bd09_to_wgs84(
                        session=session,
                        ak=args.baidu_ak,
                        query=query,
                        timeout=args.timeout,
                        city=args.baidu_city,
                    )
                    break
                except requests.RequestException as e:
                    last_err = e
                    # exponential backoff: 0, 1x, 2x ...
                    time.sleep((attempt + 1) * 0.5)
            if res is None and last_err is not None:
                print(f"[warn] {name}: {last_err}", file=sys.stderr)

            if res is None:
                cache[cache_key] = None
                missing_geo[k] = {"wgs_lng": None, "wgs_lat": None, "address": "", "bd_lng": None, "bd_lat": None}
            else:
                cache[cache_key] = res
                missing_geo[k] = res

        if (idx + 1) % 30 == 0:
            _save_cache(cache_path, cache)

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    _save_cache(cache_path, cache)

    # Append missing coords into geo output (so stations_geo covers all)
    # (We recompute stations_geo from stations.csv to keep station_name stable.)
    geo_out_rows2: list[dict[str, Any]] = []
    with open(stations_path, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            name = (row.get("station_name") or "").strip()
            if not name:
                continue
            k = canonical_key(name)
            if k in cn_map:
                cn_row = cn_map[k]
                geo_out_rows2.append(
                    {
                        "station_name": name,
                        "lng": cn_row.get("WGS84_Lng") or "",
                        "lat": cn_row.get("WGS84_Lat") or "",
                        "source": "cnstation",
                        "query": "",
                        "address": (cn_row.get("车站地址") or "").strip(),
                    }
                )
            else:
                mg = missing_geo.get(k) or {}
                lng = mg.get("wgs_lng")
                lat = mg.get("wgs_lat")
                geo_out_rows2.append(
                    {
                        "station_name": name,
                        "lng": "" if lng is None else lng,
                        "lat": "" if lat is None else lat,
                        "source": "baidu",
                    "query": build_query(name),
                        "address": mg.get("address") or "",
                    }
                )

    # Write stations_geo.csv
    Path(args.out_geo_csv).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["station_name", "lng", "lat", "source", "query", "address"]
    with open(args.out_geo_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in geo_out_rows2:
            w.writerow(r)

    # Write cnstation_completed.csv (merge best-effort)
    # Keep original cn rows, then append missing rows (no attempt to de-dup raw 站名).
    out_fields = cn_fieldnames if cn_fieldnames else [
        "站名",
        "车站地址",
        "铁路局",
        "类别",
        "性质",
        "省",
        "市",
        "lng火星",
        "lat火星",
        "WGS84_Lng",
        "WGS84_Lat",
        "BD_Lng",
        "BD_Lat",
    ]
    out_rows: list[dict[str, str]] = []
    with open(cn_path, encoding="utf-8", errors="ignore", newline="") as f:
        for row in csv.DictReader(f):
            out_rows.append(row)

    # Append generated missing rows
    for name in missing_unique:
        k = canonical_key(name)
        mg = missing_geo.get(k) or {}
        wgs_lng = mg.get("wgs_lng")
        wgs_lat = mg.get("wgs_lat")
        bd_lng = mg.get("bd_lng")
        bd_lat = mg.get("bd_lat")
        gcj_lng = mg.get("gcj_lng")
        gcj_lat = mg.get("gcj_lat")
        addr = mg.get("address") or ""

        row = {fn: "" for fn in out_fields}
        row["站名"] = name
        row["车站地址"] = addr
        row["lng火星"] = "" if gcj_lng is None else gcj_lng
        row["lat火星"] = "" if gcj_lat is None else gcj_lat
        row["WGS84_Lng"] = "" if wgs_lng is None else wgs_lng
        row["WGS84_Lat"] = "" if wgs_lat is None else wgs_lat
        row["BD_Lng"] = "" if bd_lng is None else bd_lng
        row["BD_Lat"] = "" if bd_lat is None else bd_lat
        out_rows.append(row)

    Path(args.out_cn_completed_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_cn_completed_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out_fields)
        w.writeheader()
        w.writerows(out_rows)

    # Final stats
    ok = sum(1 for r in geo_out_rows2 if (r.get("lng") not in ("", None) and r.get("lat") not in ("", None)))
    print(f"Missing: {len(missing_unique)} · stations_geo: wrote {args.out_geo_csv} with {ok}/{len(geo_out_rows2)} coords.")
    print(f"Missing list: {args.out_missing_csv}")
    print(f"Completed cnstation: {args.out_cn_completed_csv}")


if __name__ == "__main__":
    main()

