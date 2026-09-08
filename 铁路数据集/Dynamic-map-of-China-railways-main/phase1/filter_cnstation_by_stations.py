"""
Keep only cnstation rows whose canonical key appears in stations.csv (segment-derived).

Uses the same key as compare_station_tables: normalize_station_name + strip trailing 「站」.

By default backs up the input to <input>.backup.csv then overwrites --out (default same as input).
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from phase1.parsers import normalize_station_name


def canonical_key(name: str) -> str:
    t = normalize_station_name(name)
    while t.endswith("站"):
        t = t[:-1]
    return normalize_station_name(t)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cn", default="data/output/cnstation.csv")
    ap.add_argument("--stations", default="data/output/stations.csv")
    ap.add_argument("--out", default=None, help="Default: same as --cn")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    cn_path = Path(args.cn)
    out_path = Path(args.out) if args.out else cn_path

    keys_st: set[str] = set()
    with open(args.stations, encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            n = (row.get("station_name") or "").strip()
            if n:
                keys_st.add(canonical_key(n))

    rows = []
    fieldnames: list[str] = []
    total_in = 0
    with open(cn_path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            name = (row.get("站名") or "").strip()
            if not name:
                continue
            total_in += 1
            if canonical_key(name) in keys_st:
                rows.append(row)

    if not args.no_backup and cn_path.resolve() == out_path.resolve():
        bak = cn_path.with_suffix(cn_path.suffix + ".backup.csv")
        shutil.copy2(cn_path, bak)
        print(f"Backup: {bak}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    print(f"Kept {len(rows)} / {total_in} rows (removed {total_in - len(rows)})")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
