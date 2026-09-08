"""
Build data/output/stations.csv from trains_segments.csv:
unique station names with how often they appear as segment start / end.
"""

import csv
import os
from collections import defaultdict

from phase1.parsers import normalize_station_name


def main():
    in_csv = "data/output/trains_segments.csv"
    out_csv = "data/output/stations.csv"
    if not os.path.exists(in_csv):
        raise FileNotFoundError(in_csv)

    as_from: dict[str, int] = defaultdict(int)
    as_to: dict[str, int] = defaultdict(int)

    with open(in_csv, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            a = normalize_station_name(row.get("segment_from_station") or "")
            b = normalize_station_name(row.get("segment_to_station") or "")
            if a:
                as_from[a] += 1
            if b:
                as_to[b] += 1

    names = sorted(set(as_from.keys()) | set(as_to.keys()))

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fieldnames = [
        "station_name",
        "segment_count_as_from",
        "segment_count_as_to",
        "segment_mentions_total",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for name in names:
            cf = as_from.get(name, 0)
            ct = as_to.get(name, 0)
            w.writerow(
                {
                    "station_name": name,
                    "segment_count_as_from": cf,
                    "segment_count_as_to": ct,
                    "segment_mentions_total": cf + ct,
                }
            )

    print(f"Wrote {out_csv} with {len(names)} stations")


if __name__ == "__main__":
    main()
