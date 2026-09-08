"""
Compare reference station list (e.g. cnstation.csv) vs segment-derived stations.csv.

Uses normalize_station_name(), then strips trailing 「站」 (possibly repeated) as a
looser match key for names like 三家店 vs 三家店站.

Writes:
  data/output/station_compare_summary.txt
  data/output/station_compare_only_in_cn.csv
  data/output/station_compare_only_in_segments.csv
  data/output/station_compare_ambiguous_keys.csv  (same key -> multiple raw names)
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from phase1.parsers import normalize_station_name


def canonical_key(name: str) -> str:
    t = normalize_station_name(name)
    while t.endswith("站"):
        t = t[:-1]
    return normalize_station_name(t)


def load_column(path: Path, column: str) -> list[str]:
    out: list[str] = []
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        if column not in (reader.fieldnames or []):
            raise SystemExit(f"{path}: missing column {column!r}, have {reader.fieldnames}")
        for row in reader:
            v = (row.get(column) or "").strip()
            if v:
                out.append(v)
    return out


def build_key_map(raw_names: list[str]) -> dict[str, set[str]]:
    """key -> set of raw display names seen."""
    m: dict[str, set[str]] = defaultdict(set)
    for raw in raw_names:
        k = canonical_key(raw)
        if not k:
            continue
        m[k].add(normalize_station_name(raw))
    return dict(m)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare cnstation vs stations.csv with 站-suffix normalization.")
    ap.add_argument("--cn", default="data/output/cnstation.csv", help="Reference CSV (column 站名)")
    ap.add_argument("--segments-stations", default="data/output/stations.csv", help="Derived stations.csv")
    ap.add_argument("--out-dir", default="data/output")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cn_raw = load_column(Path(args.cn), "站名")
    st_raw = load_column(Path(args.segments_stations), "station_name")

    cn_map = build_key_map(cn_raw)
    st_map = build_key_map(st_raw)

    keys_cn = set(cn_map.keys())
    keys_st = set(st_map.keys())
    both = keys_cn & keys_st
    only_cn = keys_cn - keys_st
    only_st = keys_st - keys_cn

    amb_rows: list[tuple[str, str, str]] = []
    for label, m in ("cnstation", cn_map), ("segments", st_map):
        for k, raws in m.items():
            if len(raws) > 1:
                amb_rows.append((label, k, " | ".join(sorted(raws))))

    amb_cn = sum(1 for _k, raws in cn_map.items() if len(raws) > 1)
    amb_st = sum(1 for _k, raws in st_map.items() if len(raws) > 1)

    summary_lines = [
        "=== Station table comparison ===",
        f"Reference: {args.cn}",
        f"Segment-derived: {args.segments_stations}",
        "",
        "Normalization: normalize_station_name() + strip trailing 「站」 for matching key.",
        "",
        f"Unique keys (cnstation): {len(keys_cn)}",
        f"Unique keys (segments):  {len(keys_st)}",
        f"Keys in both:            {len(both)}",
        f"Only in reference:       {len(only_cn)}",
        f"Only in segments:        {len(only_st)}",
        f"Ambiguous keys (same key, multiple raw names): cnstation={amb_cn} segments={amb_st}",
        "",
    ]

    (out_dir / "station_compare_summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    def write_key_csv(path: Path, keys: set[str], cn_m: dict, st_m: dict) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["canonical_key", "names_in_cnstation", "names_in_segments"])
            for k in sorted(keys):
                w.writerow(
                    [
                        k,
                        " | ".join(sorted(cn_m.get(k, set()))),
                        " | ".join(sorted(st_m.get(k, set()))),
                    ]
                )

    write_key_csv(out_dir / "station_compare_only_in_cn.csv", only_cn, cn_map, st_map)
    write_key_csv(out_dir / "station_compare_only_in_segments.csv", only_st, cn_map, st_map)

    with open(out_dir / "station_compare_ambiguous_keys.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["source", "canonical_key", "raw_name_variants"])
        for row in sorted(amb_rows, key=lambda x: (x[0], x[1])):
            w.writerow(row)

    print("\n".join(summary_lines))


if __name__ == "__main__":
    main()
