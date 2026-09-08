"""
Estimate great-circle distance between segment endpoints (WGS84 from stations_geo.csv),
implied speed = dist / segment_duration_minutes, flag physically implausible rows.

Writes:
- data/output/segment_speed_anomalies_summary.txt
- data/output/segment_speed_anomalies_gt{threshold}kmh.csv
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path
from phase1.parsers import normalize_station_name
from phase1.segment_time import effective_duration_minutes
from phase2.prepare_simulation_data import _haversine_m

ROOT = Path(__file__).resolve().parents[1]


def load_coords(path: Path) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        for row in csv.DictReader(f):
            n = (row.get("station_name") or "").strip()
            if not n:
                continue
            try:
                lng, lat = float(row["lng"]), float(row["lat"])
            except (ValueError, KeyError):
                continue
            out[normalize_station_name(n)] = (lng, lat)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments-csv", default=str(ROOT / "data/output/trains_segments.csv"))
    ap.add_argument("--geo-csv", default=str(ROOT / "data/output/stations_geo.csv"))
    ap.add_argument("--threshold-kmh", type=float, default=2000.0)
    ap.add_argument("--also-report-kmh", type=float, default=350.0, help="Extra line in summary for rail-like cap.")
    args = ap.parse_args()

    coords = load_coords(Path(args.geo_csv))
    seg_path = Path(args.segments_csv)

    missing_coord = 0
    bad_dur = 0
    total = 0
    over_thresh: list[dict[str, object]] = []
    over_350 = 0
    dur_source = Counter()

    with open(seg_path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            a = normalize_station_name((row.get("segment_from_station") or "").strip())
            b = normalize_station_name((row.get("segment_to_station") or "").strip())
            ca, cb = coords.get(a), coords.get(b)
            if not ca or not cb:
                missing_coord += 1
                continue
            dur, dsrc = effective_duration_minutes(row)
            dur_source[dsrc] += 1
            if dur is None or dur <= 0:
                bad_dur += 1
                continue

            dist_m = _haversine_m(ca[0], ca[1], cb[0], cb[1])
            dist_km = dist_m / 1000.0
            v_kmh = dist_km / (dur / 60.0)
            if v_kmh > args.also_report_kmh:
                over_350 += 1
            if v_kmh > args.threshold_kmh:
                over_thresh.append(
                    {
                        "train_no": row.get("train_no", ""),
                        "from": row.get("segment_from_station", ""),
                        "to": row.get("segment_to_station", ""),
                        "duration_min": round(dur, 4),
                        "duration_source": dsrc,
                        "dist_km": round(dist_km, 2),
                        "speed_kmh": round(v_kmh, 1),
                        "dep_str": row.get("segment_depart_time_str", ""),
                        "arr_str": row.get("segment_arrive_time_str", ""),
                        "source_train_url": row.get("source_train_url", ""),
                    }
                )

    out_dir = ROOT / "data/output"
    out_dir.mkdir(parents=True, exist_ok=True)
    thresh_tag = str(int(args.threshold_kmh)) if args.threshold_kmh == int(args.threshold_kmh) else str(args.threshold_kmh).replace(".", "p")
    out_csv = out_dir / f"segment_speed_anomalies_gt{thresh_tag}kmh.csv"
    fields = [
        "train_no",
        "from",
        "to",
        "duration_min",
        "duration_source",
        "dist_km",
        "speed_kmh",
        "dep_str",
        "arr_str",
        "source_train_url",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in over_thresh:
            w.writerow(r)

    dur_bins = Counter()
    for r in over_thresh:
        d = float(r["duration_min"])
        if d <= 1:
            dur_bins["<=1min"] += 1
        elif d <= 5:
            dur_bins["1-5min"] += 1
        elif d <= 15:
            dur_bins["5-15min"] += 1
        else:
            dur_bins[">15min"] += 1

    by_train = Counter(str(r["train_no"]) for r in over_thresh)
    top_trains = by_train.most_common(15)

    lines = [
        f"segments 总行数: {total}",
        f"缺坐标跳过: {missing_coord}",
        f"时长无法得到或<=0 跳过: {bad_dur}",
        f"时长来源计数: {dict(dur_source)}",
        f"有效样本(可算速度): {total - missing_coord - bad_dur}",
        f" implied speed > {args.also_report_kmh:g} km/h: {over_350}",
        f" implied speed > {args.threshold_kmh:g} km/h: {len(over_thresh)}",
        f"  其中运行时间分布: {dict(dur_bins)}",
        f"  异常段最多的车次 (top 15): {top_trains}",
        f"明细 CSV: {out_csv}",
    ]
    summary_path = out_dir / "segment_speed_anomalies_summary.txt"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
