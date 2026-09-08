"""
Rewrite numeric time columns in trains_segments.csv from 发车/到达文本
(修复 第三日/隔日 解析与跨日未标导致的 minute_total、duration 错误).

默认写出新文件；使用 --in-place 时先备份 .bak。
"""

from __future__ import annotations

import argparse
import csv
import shutil
from pathlib import Path

from phase1.segment_time import recompute_segment_times_from_strings

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(ROOT / "data/output/trains_segments.csv"))
    ap.add_argument(
        "--output",
        default=None,
        help="默认: input 同目录下 trains_segments.repaired.csv",
    )
    ap.add_argument("--in-place", action="store_true", help="覆盖 input，并写入 .bak 备份")
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        raise FileNotFoundError(inp)

    out = Path(args.output) if args.output else inp.with_name("trains_segments.repaired.csv")
    if args.in_place:
        bak = inp.with_suffix(inp.suffix + ".bak")
        shutil.copy2(inp, bak)
        out = inp
        print(f"Backup: {bak}")

    fixed = 0
    unchanged = 0
    failed = 0
    rows_out: list[dict[str, str]] = []
    fieldnames: list[str] = []

    with open(inp, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            new_t = recompute_segment_times_from_strings(row)
            if new_t is None:
                failed += 1
                rows_out.append(row)
                continue
            merged = dict(row)
            before = row.get("segment_duration_minutes")
            merged.update({k: str(v) for k, v in new_t.items()})
            if any(row.get(k) != merged.get(k) for k in new_t):
                fixed += 1
            else:
                unchanged += 1
            rows_out.append(merged)

    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)

    print(f"Wrote {out} rows={len(rows_out)}")
    print(f"  time fields updated from strings: {fixed}")
    print(f"  unchanged vs previous numbers: {unchanged}")
    print(f"  could not recompute (kept raw row): {failed}")


if __name__ == "__main__":
    main()
