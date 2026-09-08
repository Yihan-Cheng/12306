import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .time_utils import ParsedTime, extract_time_tokens, parse_time_text


BASE_URL = "https://www.liecheba.com"

# Provinces on root look like: /beijing/
PROVINCE_RE = re.compile(r"^/([a-z]+(?:[a-z]+)*)/$", re.IGNORECASE)
# Station pages look like: /beijing/beijingxi.html
STATION_RE = re.compile(r"^/([a-z]+(?:[a-z]+)*)/([a-z0-9]+)\.html$", re.IGNORECASE)
# Train detail pages look like: /g332.html, /1461.html, /k216.html
TRAIN_DETAIL_RE = re.compile(r"^/([A-Za-z]*\d+)\.html$", re.IGNORECASE)

# Root page also contains non-province directories; exclude them.
_NON_PROVINCE_SLUGS = {"daishoudian", "zixun", "guoji"}


@dataclass(frozen=True)
class StationTimePair:
    arrival: Optional[ParsedTime]
    departure: Optional[ParsedTime]


@dataclass(frozen=True)
class TrainCandidateAtStation:
    train_no: str
    detail_url: str
    station_time_pair: StationTimePair


def _clean(s: str) -> str:
    """Strip, NBSP→space, collapse runs of Unicode whitespace (fixes e.g. 海  口东 vs 海口东)."""
    t = str(s).strip().replace("\u00a0", " ")
    return re.sub(r"\s+", " ", t).strip()


_CJK_RE = re.compile(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])")


def normalize_station_name(s: str) -> str:
    """
    Canonical station label: strip/NBSP/collapse whitespace, then drop spaces between
    Han characters (e.g. 海  口东 / 海 口东 -> 海口东).
    """
    t = _clean(s)
    while True:
        t2 = _CJK_RE.sub(r"\1\2", t)
        if t2 == t:
            return t
        t = t2


def extract_province_links(root_html: str) -> list[str]:
    soup = BeautifulSoup(root_html, "lxml")
    seen = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href_raw = a["href"]
        if not isinstance(href_raw, str):
            continue
        href = href_raw.strip()
        path = urlparse(href).path if href.startswith("http") else href
        m = PROVINCE_RE.match(path)
        if m:
            slug = (m.group(1) or "").lower()
            if slug in _NON_PROVINCE_SLUGS:
                continue
            full = urljoin(BASE_URL, path)
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out


def extract_station_links_from_province(province_html: str) -> list[str]:
    soup = BeautifulSoup(province_html, "lxml")
    seen = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href_raw = a["href"]
        if not isinstance(href_raw, str):
            continue
        href = href_raw.strip()
        path = urlparse(href).path if href.startswith("http") else href
        if STATION_RE.match(path):
            full = urljoin(BASE_URL, path)
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out


def _find_station_schedule_table(soup: BeautifulSoup):
    # The station page includes a table with headers: 车次 | 列车类型 | 始发站 | 经过站 | 终点站
    for table in soup.find_all("table"):
        header_row = None
        for tr in table.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if not cells:
                continue
            texts = [_clean(c.get_text(" ", strip=True)) for c in cells]
            if "经过站" in texts and any("车次" in x for x in texts):
                header_row = texts
                break
        if header_row:
            return table, header_row
    return None, None


def extract_train_candidates_from_station_page(station_html: str) -> list[TrainCandidateAtStation]:
    soup = BeautifulSoup(station_html, "lxml")
    table, header = _find_station_schedule_table(soup)
    if table is None or header is None:
        return []

    # Determine the column index of "经过站" in this table.
    passed_col_idx = header.index("经过站") if "经过站" in header else 3

    out: list[TrainCandidateAtStation] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds or passed_col_idx >= len(tds):
            continue

        # Find train detail link in this row.
        train_no = None
        detail_url = None
        for a in tr.find_all("a", href=True):
            href_raw = a["href"]
            if isinstance(href_raw, str):
                href = href_raw.strip()
                path = urlparse(href).path if href.startswith("http") else href
                m = TRAIN_DETAIL_RE.match(path)
                if m:
                    train_no = m.group(1).upper()
                    detail_url = urljoin(BASE_URL, path)
                    break
        if not train_no or not detail_url:
            continue

        passed_td = tds[passed_col_idx]
        times = extract_time_tokens(passed_td.get_text(" ", strip=True))
        arrival = times[0] if len(times) >= 1 else None
        departure = times[1] if len(times) >= 2 else None

        if arrival is None and departure is None:
            continue

        out.append(
            TrainCandidateAtStation(
                train_no=train_no,
                detail_url=detail_url,
                station_time_pair=StationTimePair(arrival=arrival, departure=departure),
            )
        )
    return out


@dataclass(frozen=True)
class StopRow:
    station_name: str
    arrive: Optional[ParsedTime]
    depart: Optional[ParsedTime]


def extract_stops_from_train_detail(train_detail_html: str) -> list[StopRow]:
    soup = BeautifulSoup(train_detail_html, "lxml")
    # The stop table headers include: 序号 | 车站 | 到达时间 | 发车时间 | 运行时间 | 停留时间
    table = None
    for t in soup.find_all("table"):
        header_text = " ".join(_clean(th.get_text(" ", strip=True)) for th in t.find_all("th"))
        if "车站" in header_text and "到达时间" in header_text and "发车时间" in header_text and "序号" in header_text:
            table = t
            break
    if table is None:
        return []

    # Build column mapping from the first header row.
    col_map: dict[str, int] = {}
    for tr in table.find_all("tr"):
        ths = tr.find_all("th")
        if ths:
            for idx, th in enumerate(ths):
                col_map[_clean(th.get_text(" ", strip=True))] = idx
            break

    station_col = col_map.get("车站", 1)
    arrive_col = col_map.get("到达时间", 2)
    depart_col = col_map.get("发车时间", 3)

    out: list[StopRow] = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        if station_col >= len(tds) or arrive_col >= len(tds) or depart_col >= len(tds):
            continue

        station_name = normalize_station_name(tds[station_col].get_text(" ", strip=True))
        arrive_raw = _clean(tds[arrive_col].get_text(" ", strip=True))
        depart_raw = _clean(tds[depart_col].get_text(" ", strip=True))

        arrive = parse_time_text(arrive_raw)
        depart = parse_time_text(depart_raw)
        if not station_name:
            continue
        out.append(StopRow(station_name=station_name, arrive=arrive, depart=depart))
    return out

