import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import random
import sqlite3
import time
from typing import Optional
from urllib.robotparser import RobotFileParser
import urllib3

import requests

from .parsers import (
    BASE_URL,
    extract_province_links,
    extract_station_links_from_province,
    extract_train_candidates_from_station_page,
    extract_stops_from_train_detail,
)
from .time_utils import ParsedTime


ROOT_URL = f"{BASE_URL}/"


def crawl_date_str() -> str:
    return dt.date.today().isoformat()


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def robots_override_allows_all(path: str) -> bool:
    if not path or not os.path.exists(path):
        return True
    txt = open(path, "r", encoding="utf-8", errors="ignore").read()
    rp = RobotFileParser()
    rp.parse(txt.splitlines())
    return rp.can_fetch("*", "/")


def polite_sleep(sleep_min: float, sleep_max: float) -> None:
    if sleep_min <= 0 and sleep_max <= 0:
        return
    time.sleep(random.uniform(sleep_min, sleep_max))


def fetch_html(
    session: requests.Session,
    url: str,
    *,
    sleep_min: float,
    sleep_max: float,
    timeout_s: int,
    retries: int,
    verify_tls: bool,
) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (compatible; liecheba-scraper/phase1; +course)"}
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers, timeout=timeout_s, verify=verify_tls)
            if resp.status_code == 200:
                if resp.apparent_encoding:
                    resp.encoding = resp.apparent_encoding
                polite_sleep(sleep_min, sleep_max)
                return resp.text

            if resp.status_code in (429, 500, 502, 503, 504):
                backoff = (2**attempt) + random.random()
                time.sleep(backoff)
                continue
            resp.raise_for_status()
        except Exception as e:
            last_err = e
            backoff = (2**attempt) + random.random()
            time.sleep(backoff)
    raise RuntimeError(f"Failed to fetch {url}: {last_err}")


def html_cache_path(cache_dir: str, url: str) -> str:
    os.makedirs(cache_dir, exist_ok=True)
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    return os.path.join(cache_dir, f"{h}.html")


def get_cached_html(cache_dir: str, url: str) -> Optional[str]:
    path = html_cache_path(cache_dir, url)
    if os.path.exists(path):
        return open(path, "r", encoding="utf-8", errors="ignore").read()
    return None


def save_cached_html(cache_dir: str, url: str, html: str) -> None:
    path = html_cache_path(cache_dir, url)
    with open(path, "w", encoding="utf-8", errors="ignore") as f:
        f.write(html)


def init_db(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS train_detail (
            train_no TEXT PRIMARY KEY,
            detail_url TEXT NOT NULL,
            status INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def get_status(conn: sqlite3.Connection, train_no: str) -> Optional[int]:
    cur = conn.execute("SELECT status FROM train_detail WHERE train_no=?", (train_no,))
    row = cur.fetchone()
    return None if row is None else int(row[0])


def upsert_status(conn: sqlite3.Connection, train_no: str, detail_url: str, status: int) -> None:
    conn.execute(
        """
        INSERT INTO train_detail(train_no, detail_url, status, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(train_no) DO UPDATE SET
          detail_url=excluded.detail_url,
          status=excluded.status,
          updated_at=excluded.updated_at
        """,
        (train_no, detail_url, status, now_iso()),
    )
    conn.commit()


def ensure_csv_writer(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    is_new = not os.path.exists(path) or os.path.getsize(path) == 0
    f = open(path, "a", newline="", encoding="utf-8")
    fieldnames = [
        "crawl_date",
        "train_no",
        "segment_from_station",
        "segment_to_station",
        "segment_depart_time_str",
        "segment_arrive_time_str",
        "segment_depart_minute_of_day",
        "segment_arrive_minute_of_day",
        "segment_depart_day_offset",
        "segment_arrive_day_offset",
        "segment_depart_minute_total",
        "segment_arrive_minute_total",
        "segment_duration_minutes",
        "source_train_url",
    ]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    if is_new:
        w.writeheader()
        f.flush()
    setattr(w, "_file", f)
    return w


def ensure_jsonl(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return open(path, "a", encoding="utf-8")


def write_segments(
    *,
    crawl_date: str,
    train_no: str,
    train_url: str,
    train_html: str,
    csv_writer,
    jsonl_f,
    day_offset_mode: str,
) -> int:
    stops = extract_stops_from_train_detail(train_html)
    if len(stops) < 2:
        return 0
    n = 0
    for i in range(len(stops) - 1):
        s1 = stops[i]
        s2 = stops[i + 1]
        if s1.depart is None or s2.arrive is None:
            continue
        depart: ParsedTime = s1.depart
        arrive: ParsedTime = s2.arrive

        if day_offset_mode == "zero":
            depart_day_offset = 0
            arrive_day_offset = 0
            depart_total = depart.minute_of_day
            arrive_total = arrive.minute_of_day
        else:
            depart_day_offset = depart.day_offset
            arrive_day_offset = arrive.day_offset
            depart_total = depart.minute_total
            arrive_total = arrive.minute_total

        row = {
            "crawl_date": crawl_date,
            "train_no": train_no,
            "segment_from_station": s1.station_name,
            "segment_to_station": s2.station_name,
            "segment_depart_time_str": depart.raw,
            "segment_arrive_time_str": arrive.raw,
            "segment_depart_minute_of_day": depart.minute_of_day,
            "segment_arrive_minute_of_day": arrive.minute_of_day,
            "segment_depart_day_offset": depart_day_offset,
            "segment_arrive_day_offset": arrive_day_offset,
            "segment_depart_minute_total": depart_total,
            "segment_arrive_minute_total": arrive_total,
            "segment_duration_minutes": arrive_total - depart_total,
            "source_train_url": train_url,
        }
        csv_writer.writerow(row)
        jsonl_f.write(json.dumps(row, ensure_ascii=False) + "\n")
        n += 1

    csv_writer._file.flush()  # type: ignore[attr-defined]
    jsonl_f.flush()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-train-detail-pages", type=int, default=-1)  # -1 => no limit
    ap.add_argument("--max-provinces", type=int, default=None)
    ap.add_argument("--max-stations-per-province", type=int, default=None)
    ap.add_argument("--sleep-min", type=float, default=0.8)
    ap.add_argument("--sleep-max", type=float, default=1.8)
    ap.add_argument("--timeout-s", type=int, default=12)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--db-path", type=str, default="data/cache/state.sqlite")
    ap.add_argument("--cache-html", action="store_true")
    ap.add_argument("--html-cache-dir", type=str, default="data/cache/html")
    ap.add_argument("--robots-override", type=str, default="config/robots_override.txt")
    ap.add_argument("--day-offset-mode", choices=["keep", "zero"], default="keep")
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="跳过 HTTPS 证书校验（当你的网络/VPN 出口导致 CERTIFICATE_VERIFY_FAILED 时使用）。",
    )
    args = ap.parse_args()

    if not robots_override_allows_all(args.robots_override):
        raise RuntimeError("robots_override does not allow crawling /. Please update config/robots_override.txt")

    conn = init_db(args.db_path)
    crawl_date = crawl_date_str()

    csv_writer = ensure_csv_writer("data/output/trains_segments.csv")
    jsonl_f = ensure_jsonl("data/output/trains_segments.jsonl")

    attempted = 0
    ok_pages = 0

    with requests.Session() as session:
        if args.insecure:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        root_html = fetch_html(
            session,
            ROOT_URL,
            sleep_min=args.sleep_min,
            sleep_max=args.sleep_max,
            timeout_s=args.timeout_s,
            retries=args.retries,
            verify_tls=not args.insecure,
        )
        provinces = extract_province_links(root_html)
        if args.max_provinces is not None:
            provinces = provinces[: args.max_provinces]

        for prov_url in provinces:
            try:
                prov_html = fetch_html(
                    session,
                    prov_url,
                    sleep_min=args.sleep_min,
                    sleep_max=args.sleep_max,
                    timeout_s=args.timeout_s,
                    retries=args.retries,
                    verify_tls=not args.insecure,
                )
            except Exception:
                continue

            station_urls = extract_station_links_from_province(prov_html)
            if args.max_stations_per_province is not None:
                station_urls = station_urls[: args.max_stations_per_province]

            for station_url in station_urls:
                if args.max_train_detail_pages >= 0 and attempted >= args.max_train_detail_pages:
                    break

                # station page -> candidates
                try:
                    if args.cache_html:
                        st_cached = get_cached_html(args.html_cache_dir, station_url)
                    else:
                        st_cached = None
                    if st_cached is None:
                        station_html = fetch_html(
                            session,
                            station_url,
                            sleep_min=args.sleep_min,
                            sleep_max=args.sleep_max,
                            timeout_s=args.timeout_s,
                            retries=args.retries,
                            verify_tls=not args.insecure,
                        )
                        if args.cache_html:
                            save_cached_html(args.html_cache_dir, station_url, station_html)
                    else:
                        station_html = st_cached
                except Exception:
                    continue

                candidates = extract_train_candidates_from_station_page(station_html)
                if not candidates:
                    continue

                # hour buckets by arrival/departure minute_of_day (0..23)
                hour_to_train: dict[int, dict[str, str]] = {}
                for c in candidates:
                    hrs = set()
                    if c.station_time_pair.arrival:
                        hrs.add(min(23, max(0, c.station_time_pair.arrival.minute_of_day // 60)))
                    if c.station_time_pair.departure:
                        hrs.add(min(23, max(0, c.station_time_pair.departure.minute_of_day // 60)))
                    for h in hrs:
                        hour_to_train.setdefault(h, {})
                        hour_to_train[h].setdefault(c.train_no, c.detail_url)

                for h in range(24):
                    if args.max_train_detail_pages >= 0 and attempted >= args.max_train_detail_pages:
                        break
                    bucket = hour_to_train.get(h)
                    if not bucket:
                        continue
                    for train_no in sorted(bucket.keys()):
                        if args.max_train_detail_pages >= 0 and attempted >= args.max_train_detail_pages:
                            break
                        train_url = bucket[train_no]

                        st = get_status(conn, train_no)
                        if st == 1:
                            continue

                        upsert_status(conn, train_no, train_url, status=0)
                        attempted += 1

                        try:
                            if args.cache_html:
                                tr_cached = get_cached_html(args.html_cache_dir, train_url)
                            else:
                                tr_cached = None
                            if tr_cached is None:
                                train_html = fetch_html(
                                    session,
                                    train_url,
                                    sleep_min=args.sleep_min,
                                    sleep_max=args.sleep_max,
                                    timeout_s=args.timeout_s,
                                    retries=args.retries,
                                    verify_tls=not args.insecure,
                                )
                                if args.cache_html:
                                    save_cached_html(args.html_cache_dir, train_url, train_html)
                            else:
                                train_html = tr_cached
                        except Exception:
                            upsert_status(conn, train_no, train_url, status=2)
                            continue

                        try:
                            rows = write_segments(
                                crawl_date=crawl_date,
                                train_no=train_no,
                                train_url=train_url,
                                train_html=train_html,
                                csv_writer=csv_writer,
                                jsonl_f=jsonl_f,
                                day_offset_mode=args.day_offset_mode,
                            )
                            if rows > 0:
                                ok_pages += 1
                                upsert_status(conn, train_no, train_url, status=1)
                            else:
                                upsert_status(conn, train_no, train_url, status=2)
                        except Exception:
                            upsert_status(conn, train_no, train_url, status=2)

    try:
        csv_writer._file.close()  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        jsonl_f.close()
    except Exception:
        pass

    print(f"Done. ok_train_pages={ok_pages}, attempted_train_pages={attempted}")


if __name__ == "__main__":
    main()

