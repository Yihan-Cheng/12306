import csv
import os
import re
from typing import Optional


_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})")


def parse_hhmm(s: str) -> Optional[str]:
    if s is None:
        return None
    m = _HHMM_RE.search(str(s))
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    return f"{hh:02d}:{mm:02d}"


def duration_str(total_minutes: int) -> str:
    if total_minutes < 0:
        total_minutes = 0
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{h}小时{m}分钟"


def main():
    in_csv = "data/output/trains_segments.csv"
    out_csv = "data/output/trains.csv"
    if not os.path.exists(in_csv):
        raise FileNotFoundError(in_csv)

    earliest = {}
    latest = {}
    url_by_train = {}
    crawl_date_by_train = {}

    def to_int(x):
        return int(float(x))

    with open(in_csv, "r", encoding="utf-8", errors="ignore", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            train_no = row.get("train_no") or ""
            if not train_no:
                continue
            dep_total = row.get("segment_depart_minute_total")
            arr_total = row.get("segment_arrive_minute_total")
            if not dep_total or not arr_total:
                continue
            dep_total = to_int(dep_total)
            arr_total = to_int(arr_total)
            crawl_date = row.get("crawl_date", "")
            url = row.get("source_train_url", "")

            if train_no not in earliest or dep_total < earliest[train_no]["dep_total"]:
                earliest[train_no] = {
                    "dep_total": dep_total,
                    "departure_station": row.get("segment_from_station", ""),
                    "departure_time_str": row.get("segment_depart_time_str", ""),
                }
                url_by_train[train_no] = url
                crawl_date_by_train[train_no] = crawl_date

            if train_no not in latest or arr_total > latest[train_no]["arr_total"]:
                latest[train_no] = {
                    "arr_total": arr_total,
                    "arrival_station": row.get("segment_to_station", ""),
                    "arrival_time_str": row.get("segment_arrive_time_str", ""),
                }

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fieldnames = [
        "crawl_date",
        "train_no",
        "departure_station",
        "arrival_station",
        "departure_time",
        "arrival_time",
        "total_duration_minutes",
        "total_duration_str",
        "source_train_url",
    ]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for train_no in sorted(set(earliest.keys()) & set(latest.keys())):
            e = earliest[train_no]
            l = latest[train_no]
            total = l["arr_total"] - e["dep_total"]
            w.writerow(
                {
                    "crawl_date": crawl_date_by_train.get(train_no, ""),
                    "train_no": train_no,
                    "departure_station": e["departure_station"],
                    "arrival_station": l["arrival_station"],
                    "departure_time": parse_hhmm(e["departure_time_str"]) or "",
                    "arrival_time": parse_hhmm(l["arrival_time_str"]) or "",
                    "total_duration_minutes": total,
                    "total_duration_str": duration_str(total),
                    "source_train_url": url_by_train.get(train_no, ""),
                }
            )

    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()

import csv
import os
import re
from collections import defaultdict
from typing import Optional


_HHMM_RE = re.compile(r"(\d{1,2}):(\d{2})")


def parse_hhmm_from_time_str(s: str) -> Optional[str]:
    """
    Input example: "00:05 (当日)" / "01:01 (次日)".
    Output: "00:05"
    """
    if s is None:
        return None
    m = _HHMM_RE.search(str(s))
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2))
    return f"{hh:02d}:{mm:02d}"


def format_minutes_as_duration(total_minutes: int) -> str:
    if total_minutes < 0:
        total_minutes = 0
    hours = total_minutes // 60
    minutes = total_minutes % 60
    # Use simple Chinese duration string
    return f"{hours}小时{minutes}分钟"


def main():
    in_csv = "data/output/trains_segments.csv"
    out_csv = "data/output/trains.csv"

    if not os.path.exists(in_csv):
        raise FileNotFoundError(f"Missing input: {in_csv}")

    # Per train summary we need for Phase 2
    # earliest_depart: min segment_depart_minute_total
    # latest_arrive: max segment_arrive_minute_total
    earliest_depart = {}
    latest_arrive = {}
    source_url_by_train = {}

    def to_int(x):
        return int(float(x)) if x is not None and str(x).strip() != "" else None

    with open(in_csv, "r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            train_no = row.get("train_no") or ""
            if not train_no:
                continue

            dep_total = to_int(row.get("segment_depart_minute_total"))
            arr_total = to_int(row.get("segment_arrive_minute_total"))
            if dep_total is None or arr_total is None:
                continue

            depart_station = row.get("segment_from_station", "")
            arrival_station = row.get("segment_to_station", "")
            depart_time_str = row.get("segment_depart_time_str", "")
            arrival_time_str = row.get("segment_arrive_time_str", "")
            source_url = row.get("source_train_url", "")

            # earliest depart
            if train_no not in earliest_depart or dep_total < earliest_depart[train_no]["dep_total"]:
                earliest_depart[train_no] = {
                    "dep_total": dep_total,
                    "departure_station": depart_station,
                    "departure_time_str": depart_time_str,
                }
                source_url_by_train[train_no] = source_url

            # latest arrive
            if train_no not in latest_arrive or arr_total > latest_arrive[train_no]["arr_total"]:
                latest_arrive[train_no] = {
                    "arr_total": arr_total,
                    "arrival_station": arrival_station,
                    "arrival_time_str": arrival_time_str,
                }

    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    fieldnames = [
        "train_no",
        "departure_station",
        "arrival_station",
        "departure_time",
        "arrival_time",
        "total_duration_minutes",
        "total_duration_str",
        "source_train_url",
    ]

    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for train_no in sorted(set(earliest_depart.keys()) & set(latest_arrive.keys())):
            dep = earliest_depart[train_no]
            arr = latest_arrive[train_no]
            total_minutes = arr["arr_total"] - dep["dep_total"]

            departure_time = parse_hhmm_from_time_str(dep["departure_time_str"]) or ""
            arrival_time = parse_hhmm_from_time_str(arr["arrival_time_str"]) or ""

            writer.writerow(
                {
                    "train_no": train_no,
                    "departure_station": dep["departure_station"],
                    "arrival_station": arr["arrival_station"],
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "total_duration_minutes": total_minutes,
                    "total_duration_str": format_minutes_as_duration(total_minutes),
                    "source_train_url": source_url_by_train.get(train_no, ""),
                }
            )

    print(f"Derived {out_csv} from {in_csv}")


if __name__ == "__main__":
    main()

