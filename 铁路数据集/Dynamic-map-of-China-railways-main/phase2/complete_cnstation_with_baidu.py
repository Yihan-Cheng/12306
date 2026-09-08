"""
Complete `data/output/cnstation.csv` coordinates using Baidu geocoding:
1) For station keys that appear in `data/output/stations.csv` but whose cnstation row
   lacks WGS84 and/or BD coordinates, call Baidu geocoding.
2) Update existing cnstation rows in-place (only fill empty coordinate fields).
3) If a canonical key does not exist in cnstation at all, append a new row.

Also writes:
- data/output/stations_geo.csv (Leaflet WGS84 lon/lat) for all stations in stations.csv.

Important user requirement:
- When searching Baidu, use the name from `stations.csv` and ensure it ends with "站".
  (i.e. query = station_name + "站", unless station_name already endswith "站".)
- Optional fallback query: normalized name + "火车站" (never uses "××站站").
- Use `--retry-empty-geo-csv` to only hit stations with empty lng/lat in `stations_geo.csv`;
  use `--regeocode-all` (with `--ignore-geocode-cache` for a true API refresh) to redo all.
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


def build_query(station_name: str) -> str:
    s = (station_name or "").strip()
    if not s:
        return s
    if s.endswith("站"):
        return s
    return s + "站"


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


def _has_wgs(row: dict[str, Any]) -> bool:
    return bool((row.get("WGS84_Lng") or "").strip()) and bool((row.get("WGS84_Lat") or "").strip())


def _has_bd(row: dict[str, Any]) -> bool:
    return bool((row.get("BD_Lng") or "").strip()) and bool((row.get("BD_Lat") or "").strip())


def _to_float_or_none(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Fill cnstation coords via Baidu.")
    ap.add_argument("--stations-csv", default="data/output/stations.csv")
    ap.add_argument("--cnstation-csv", default="data/output/cnstation.csv")
    ap.add_argument("--out-cnstation-csv", default="data/output/cnstation.completed.csv")
    ap.add_argument("--out-geo-csv", default="data/output/stations_geo.csv")
    ap.add_argument("--cache", default="data/cache/baidu_geocode_cache.json")
    ap.add_argument("--city", default="", help="Optional city constraint for Baidu.")
    ap.add_argument("--timeout", type=float, default=25.0)
    ap.add_argument("--sleep-min", type=float, default=0.15)
    ap.add_argument("--sleep-max", type=float, default=0.35)
    ap.add_argument("--baidu-retries", type=int, default=3)
    ap.add_argument("--max-keys", type=int, default=None, help="For testing: max missing canonical keys.")
    ap.add_argument(
        "--retry-empty-geo-csv",
        default=None,
        help="Only geocode canonical keys whose rows in this CSV have empty lng/lat (e.g. current stations_geo.csv).",
    )
    ap.add_argument(
        "--regeocode-all",
        action="store_true",
        help="Geocode every station in stations.csv (overwrites cnstation coords when Baidu returns a result).",
    )
    ap.add_argument(
        "--ignore-geocode-cache",
        action="store_true",
        help="Always call Baidu instead of reusing baidu_geocode_cache hits (still writes cache after each call).",
    )
    ap.add_argument("--dry-run", action="store_true", help="Only compute missing list, no Baidu call.")
    ap.add_argument("--baidu-ak", default=os.environ.get("BAIDU_MAP_AK", ""))
    args = ap.parse_args()

    if not args.baidu_ak and not args.dry_run:
        print("Missing BAIDU_MAP_AK env (server ak).", file=sys.stderr)
        sys.exit(1)

    stations_path = Path(args.stations_csv)
    cn_path = Path(args.cnstation_csv)
    if not stations_path.exists():
        raise FileNotFoundError(stations_path)
    if not cn_path.exists():
        raise FileNotFoundError(cn_path)

    # Load cnstation
    cn_fieldnames: list[str] = []
    cn_rows: list[dict[str, Any]] = []
    key_to_indices: dict[str, list[int]] = {}
    with open(cn_path, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        cn_fieldnames = list(r.fieldnames or [])
        for idx, row in enumerate(r):
            cn_rows.append(row)
            raw = (row.get("站名") or "").strip()
            if not raw:
                continue
            k = canonical_key(raw)
            key_to_indices.setdefault(k, []).append(idx)

    # Load stations (for stable ordering)
    stations_order: list[dict[str, str]] = []
    stations_keys: list[str] = []
    stations_unique_keys: list[str] = []
    seen_key: set[str] = set()
    with open(stations_path, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            name = (row.get("station_name") or "").strip()
            if not name:
                continue
            k = canonical_key(name)
            stations_order.append({"station_name": name, "key": k})
            stations_keys.append(k)
            if k not in seen_key:
                seen_key.add(k)
                stations_unique_keys.append(k)

    # Determine which keys are missing coords (need Baidu)
    missing_keys: list[str] = []
    key_to_station_name: dict[str, str] = {}  # for query/address only
    for item in stations_order:
        k = item["key"]
        if k in key_to_station_name:
            continue
        key_to_station_name[k] = item["station_name"]

    def _any_row_has_good_coords(key: str) -> bool:
        idxs = key_to_indices.get(key) or []
        for i in idxs:
            rr = cn_rows[i]
            if _has_wgs(rr) and _has_bd(rr):
                return True
        return False

    if args.regeocode_all:
        missing_keys = list(stations_unique_keys)
    elif args.retry_empty_geo_csv:
        geo_p = Path(args.retry_empty_geo_csv)
        if not geo_p.exists():
            raise FileNotFoundError(geo_p)
        need_retry: set[str] = set()
        with open(geo_p, encoding="utf-8", errors="ignore", newline="") as f:
            gr = csv.DictReader(f)
            for row in gr:
                lng = (row.get("lng") or "").strip()
                lat = (row.get("lat") or "").strip()
                if lng and lat:
                    continue
                nm = (row.get("station_name") or "").strip()
                if nm:
                    need_retry.add(canonical_key(nm))
        for k in stations_unique_keys:
            if k in need_retry:
                missing_keys.append(k)
    else:
        for k in stations_unique_keys:
            if not _any_row_has_good_coords(k):
                missing_keys.append(k)

    if args.max_keys is not None:
        missing_keys = missing_keys[: args.max_keys]

    if args.dry_run:
        out = Path("data/output/cnstation_missing_from_segments_baidu_dry_run.csv")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "canonical_key\n" + "\n".join(missing_keys) + "\n",
            encoding="utf-8",
        )
        print(f"Dry-run: missing keys={len(missing_keys)} written to {out}")
        return

    cache_path = Path(args.cache)
    cache = _load_cache(cache_path)
    session = requests.Session()

    # canonical key -> baidu result dict (includes query_used for stations_geo)
    baidu_coords: dict[str, dict[str, Any]] = {}

    retries = max(1, int(args.baidu_retries))

    def run_geocode_query(query: str) -> tuple[Optional[dict[str, Any]], Optional[Exception]]:
        cache_key = f"baidu:{query}"
        if not args.ignore_geocode_cache:
            cached = cache.get(cache_key)
            if isinstance(cached, dict) and cached.get("wgs_lng") is not None and cached.get("bd_lng") is not None:
                out = dict(cached)
                out["query_used"] = query
                return out, None

        res: Optional[dict[str, Any]] = None
        last_err: Optional[Exception] = None
        for attempt in range(retries):
            try:
                res = baidu_geocode_bd09_to_wgs84(
                    session=session,
                    ak=args.baidu_ak,
                    query=query,
                    timeout=args.timeout,
                    city=args.city,
                )
                break
            except requests.RequestException as e:
                last_err = e
                time.sleep((attempt + 1) * 0.5)

        if res is not None:
            cache[cache_key] = res
            out = dict(res)
            out["query_used"] = query
            return out, None

        cache[cache_key] = None
        return None, last_err

    for idx, k in enumerate(missing_keys):
        station_name = key_to_station_name.get(k, k)
        # 首轮：站名末尾无「站」则补「站」（如 三水南 → 三水南站）；已有「站」则不改
        q1 = build_query(station_name)
        # 次轮：规范化站名 + 「火车站」（应对「福海西」等仅「××站」无结果的情况）；避免「××站站」
        base = normalize_station_name(station_name)
        q2 = ""
        if base and not base.endswith("火车站"):
            q2 = base + "火车站"

        queries = [q1]
        if q2 and q2 != q1:
            queries.append(q2)

        got: Optional[dict[str, Any]] = None
        last_err: Optional[Exception] = None
        for qi, query in enumerate(queries):
            got, last_err = run_geocode_query(query)
            if got is not None:
                baidu_coords[k] = got
                break
            if qi < len(queries) - 1:
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))

        if got is None:
            reason = last_err if last_err is not None else "百度无有效坐标"
            print(f"[warn] {station_name} ({k}): {reason}", file=sys.stderr)

        if (idx + 1) % 20 == 0:
            _save_cache(cache_path, cache)

        time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    _save_cache(cache_path, cache)

    overwrite_cn = bool(args.regeocode_all)

    def _apply_coords_to_row(rr: dict[str, Any], coords: dict[str, Any]) -> None:
        def put(field: str, val: Any) -> None:
            if val is None:
                return
            cur = (rr.get(field) or "").strip()
            if not overwrite_cn and cur:
                return
            rr[field] = val

        if coords.get("gcj_lng") is not None:
            put("lng火星", coords["gcj_lng"])
        if coords.get("gcj_lat") is not None:
            put("lat火星", coords["gcj_lat"])
        if coords.get("wgs_lng") is not None:
            put("WGS84_Lng", coords["wgs_lng"])
        if coords.get("wgs_lat") is not None:
            put("WGS84_Lat", coords["wgs_lat"])
        if coords.get("bd_lng") is not None:
            put("BD_Lng", coords["bd_lng"])
        if coords.get("bd_lat") is not None:
            put("BD_Lat", coords["bd_lat"])
        addr = coords.get("address")
        if addr:
            put("车站地址", addr)

    # Update cnstation rows
    for k, coords in baidu_coords.items():
        idxs = key_to_indices.get(k) or []
        if not idxs:
            # append
            station_name = key_to_station_name.get(k, k)
            row = {fn: "" for fn in cn_fieldnames}
            row["站名"] = station_name
            _apply_coords_to_row(row, coords)
            cn_rows.append(row)
            key_to_indices.setdefault(k, []).append(len(cn_rows) - 1)
            continue

        for i in idxs:
            rr = cn_rows[i]
            if overwrite_cn:
                _apply_coords_to_row(rr, coords)
            else:
                if not (rr.get("lng火星") or "").strip() and coords.get("gcj_lng") is not None:
                    rr["lng火星"] = coords["gcj_lng"]
                if not (rr.get("lat火星") or "").strip() and coords.get("gcj_lat") is not None:
                    rr["lat火星"] = coords["gcj_lat"]
                if not (rr.get("WGS84_Lng") or "").strip() and coords.get("wgs_lng") is not None:
                    rr["WGS84_Lng"] = coords["wgs_lng"]
                if not (rr.get("WGS84_Lat") or "").strip() and coords.get("wgs_lat") is not None:
                    rr["WGS84_Lat"] = coords["wgs_lat"]
                if not (rr.get("BD_Lng") or "").strip() and coords.get("bd_lng") is not None:
                    rr["BD_Lng"] = coords["bd_lng"]
                if not (rr.get("BD_Lat") or "").strip() and coords.get("bd_lat") is not None:
                    rr["BD_Lat"] = coords["bd_lat"]
                if not (rr.get("车站地址") or "").strip() and coords.get("address"):
                    rr["车站地址"] = coords["address"]

    # Build a key->wgs coord lookup from updated cn_rows
    key_to_best_wgs: dict[str, dict[str, str]] = {}
    for k, idxs in key_to_indices.items():
        for i in idxs:
            rr = cn_rows[i]
            lng = _to_float_or_none(rr.get("WGS84_Lng"))
            lat = _to_float_or_none(rr.get("WGS84_Lat"))
            if lng is None or lat is None:
                continue
            # Keep first found
            if k not in key_to_best_wgs:
                key_to_best_wgs[k] = {
                    "lng": lng,
                    "lat": lat,
                    "address": (rr.get("车站地址") or "").strip(),
                }

    # stations_geo output for all station rows in stations.csv
    geo_out_rows: list[dict[str, Any]] = []
    for item in stations_order:
        name = item["station_name"]
        k = item["key"]
        if k in key_to_best_wgs:
            eg = key_to_best_wgs[k]
            geo_out_rows.append(
                {
                    "station_name": name,
                    "lng": eg["lng"],
                    "lat": eg["lat"],
                    "source": "cnstation",
                    "query": "",
                    "address": eg.get("address") or "",
                }
            )
        else:
            coords = baidu_coords.get(k) or {}
            geo_out_rows.append(
                {
                    "station_name": name,
                    "lng": coords.get("wgs_lng") or "",
                    "lat": coords.get("wgs_lat") or "",
                    "source": "baidu",
                    "query": coords.get("query_used") or build_query(name),
                    "address": coords.get("address") or "",
                }
            )

    Path(args.out_geo_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_geo_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["station_name", "lng", "lat", "source", "query", "address"])
        w.writeheader()
        w.writerows(geo_out_rows)

    # Write updated cnstation
    Path(args.out_cnstation_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_cnstation_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cn_fieldnames)
        w.writeheader()
        w.writerows(cn_rows)

    ok_geo = sum(1 for r in geo_out_rows if (str(r.get("lng") or "").strip()) and (str(r.get("lat") or "").strip()))
    print(
        f"Wrote: {args.out_cnstation_csv} (rows={len(cn_rows)}) · "
        f"{args.out_geo_csv} coords={ok_geo}/{len(geo_out_rows)}"
    )


if __name__ == "__main__":
    main()

