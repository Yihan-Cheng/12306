"""
Merge trains_segments + stations_geo → phase2/web/data/simulation.json for the map UI.

- Stations: WGS84 coordinates
- edges: unique undirected station pairs (for static polylines)
- segments: compact schedule for 24h animation (constant speed along great-circle)
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from phase1.parsers import normalize_station_name
from phase1.segment_time import implied_speed_kmh, recompute_segment_times_from_strings

ROOT = Path(__file__).resolve().parents[1]
WEB_DATA = ROOT / "phase2" / "web" / "data"
DEFAULT_MAX_IMPLIED_SPEED_KMH = 400.0


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    dp = math.radians(lat2 - lat1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments-csv", default=str(ROOT / "data/output/trains_segments.csv"))
    ap.add_argument("--geo-csv", default=str(ROOT / "data/output/stations_geo.csv"))
    ap.add_argument("--out-json", default=str(WEB_DATA / "simulation.json"))
    ap.add_argument("--crawl-date", default=None, help="Filter rows by crawl_date (optional).")
    ap.add_argument(
        "--max-segments",
        type=int,
        default=0,
        help="Max segment rows in JSON; 0 = no limit (may produce a very large file).",
    )
    ap.add_argument(
        "--max-edges",
        type=int,
        default=0,
        help="Max undirected edge polylines; 0 = no limit.",
    )
    ap.add_argument(
        "--max-implied-speed-kmh",
        type=float,
        default=DEFAULT_MAX_IMPLIED_SPEED_KMH,
        help="Skip segments whose great-circle distance / duration implies above this speed "
        "(guards bad coordinates or bad times). Default 400.",
    )
    ap.add_argument(
        "--coord-overrides-csv",
        default=str(ROOT / "data/config/station_coord_overrides.csv"),
        help="Optional CSV: station_name,lng,lat — overrides stations_geo when file exists.",
    )
    args = ap.parse_args()

    coords: dict[str, tuple[float, float]] = {}
    geo_path = Path(args.geo_csv)
    if geo_path.exists():
        with open(geo_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            for row in csv.DictReader(f):
                name = (row.get("station_name") or "").strip()
                if not name:
                    continue
                try:
                    lng = float(row.get("lng") or "")
                    lat = float(row.get("lat") or "")
                except ValueError:
                    continue
                coords[normalize_station_name(name)] = (lng, lat)

    ov_path = Path(args.coord_overrides_csv)
    if ov_path.exists():
        with open(ov_path, "r", encoding="utf-8", errors="ignore", newline="") as f:
            for row in csv.DictReader(f):
                name = (row.get("station_name") or "").strip()
                if not name:
                    continue
                try:
                    lng = float(row.get("lng") or "")
                    lat = float(row.get("lat") or "")
                except ValueError:
                    continue
                coords[normalize_station_name(name)] = (lng, lat)

    if not coords:
        print(
            f"No coordinates in {args.geo_csv}. Run: "
            f"python -m phase2.geocode_stations --provider nominatim"
        )
        return

    segments_out: list[dict[str, object]] = []
    edge_seen: set[tuple[str, str]] = set()
    edges_out: list[dict[str, object]] = []
    skipped_speed = 0

    if not Path(args.segments_csv).exists():
        print(f"Missing {args.segments_csv}")
        return

    with open(args.segments_csv, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if args.crawl_date and row.get("crawl_date") != args.crawl_date:
                continue
            a = normalize_station_name(row.get("segment_from_station") or "")
            b = normalize_station_name(row.get("segment_to_station") or "")
            if not a or not b or a not in coords or b not in coords:
                continue

            fixed = recompute_segment_times_from_strings(row)
            if fixed is not None:
                dep_abs = int(fixed["segment_depart_minute_total"])
                arr_abs = int(fixed["segment_arrive_minute_total"])
                dur = int(fixed["segment_duration_minutes"])
            else:
                try:
                    dep = int(row["segment_depart_minute_of_day"])
                    arr = int(row["segment_arrive_minute_of_day"])
                    d0 = int(row["segment_depart_day_offset"])
                    a0 = int(row["segment_arrive_day_offset"])
                    dur = int(row["segment_duration_minutes"])
                except (KeyError, ValueError):
                    continue
                dep_abs = d0 * 1440 + dep
                arr_abs = a0 * 1440 + arr

            if arr_abs <= dep_abs or dur <= 0:
                continue
            # Simulation UI uses minute-of-day 0..1440; skip segments that only start later
            if dep_abs >= 1440:
                continue

            lng_a, lat_a = coords[a]
            lng_b, lat_b = coords[b]
            dist_m = _haversine_m(lng_a, lat_a, lng_b, lat_b)
            v_kmh = implied_speed_kmh(dist_m, float(dur))
            if v_kmh > args.max_implied_speed_kmh:
                skipped_speed += 1
                continue

            pair = tuple(sorted((a, b)))
            if pair not in edge_seen and (args.max_edges <= 0 or len(edges_out) < args.max_edges):
                edge_seen.add(pair)
                edges_out.append(
                    {
                        "from": a,
                        "to": b,
                        "coords": [[lat_a, lng_a], [lat_b, lng_b]],
                    }
                )

            if args.max_segments > 0 and len(segments_out) >= args.max_segments:
                continue

            segments_out.append(
                {
                    "train": row.get("train_no", ""),
                    "from": a,
                    "to": b,
                    "dep": dep_abs,
                    "arr": arr_abs,
                    "dur": dur,
                    "dist_m": round(dist_m, 1),
                }
            )

    # Leaflet: [lat, lng]
    stations_payload = {k: [v[1], v[0]] for k, v in coords.items()}

    meta = {
        "segment_count": len(segments_out),
        "edge_count": len(edges_out),
        "station_count": len(stations_payload),
        "crawl_date": args.crawl_date or "",
    }

    payload = {"meta": meta, "stations": stations_payload, "edges": edges_out, "segments": segments_out}

    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(
        f"Wrote {args.out_json}: stations={len(stations_payload)} "
        f"edges={len(edges_out)} segments={len(segments_out)} "
        f"(skipped implied_speed>{args.max_implied_speed_kmh:g} km/h: {skipped_speed})"
    )


if __name__ == "__main__":
    main()
