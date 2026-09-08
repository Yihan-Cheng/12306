import re
from dataclasses import dataclass
from typing import Optional

_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


@dataclass(frozen=True)
class ParsedTime:
    minute_of_day: int  # 0..1439
    day_offset: int  # 0=当日,1=次日/隔日,2=第三日…
    minute_total: int  # day_offset*1440 + minute_of_day
    raw: str


def _detect_day_offset(s: str) -> int:
    """Longer / later-day labels first; 隔日 treated like 次日."""
    if "第五日" in s:
        return 4
    if "第四日" in s:
        return 3
    if "第三日" in s:
        return 2
    if "次日" in s or "隔日" in s:
        return 1
    if "当日" in s:
        return 0
    return 0


def parse_time_text(text: str) -> Optional[ParsedTime]:
    """
    Examples:
    - "14:33 (当日)"
    - "00:18 (次日)" / "次日08:20"
    - "04:50 (第三日)"
    - "----" / "-" -> None
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t or t in {"-", "—"}:
        return None
    if "----" in t:
        return None

    m = _TIME_RE.search(t)
    if not m:
        return None

    hh = int(m.group(1))
    mm = int(m.group(2))
    minute_of_day = hh * 60 + mm
    day_offset = _detect_day_offset(t)
    minute_total = day_offset * 1440 + minute_of_day
    return ParsedTime(minute_of_day=minute_of_day, day_offset=day_offset, minute_total=minute_total, raw=t)


def extract_time_tokens(cell_text: str) -> list[ParsedTime]:
    """
    Cell may contain multiple times, like:
    - "21:25 (当日) 21:40 (当日) 21:55 (当日)"
    """
    if cell_text is None:
        return []
    s = str(cell_text).strip()
    if not s or "----" in s or s in {"-", "—"}:
        return []

    results: list[ParsedTime] = []
    for m in _TIME_RE.finditer(s):
        start = max(0, m.start() - 14)
        end = min(len(s), m.end() + 14)
        window = s[start:end]
        pt = parse_time_text(window)
        if pt:
            results.append(pt)
    return results


def extract_time_tokens_from_text_cell(cell_text: str) -> list[ParsedTime]:
    """Alias for extract_time_tokens (same behaviour)."""
    return extract_time_tokens(cell_text)


def parse_duration_to_minutes(text: str) -> Optional[int]:
    """
    Examples:
    - "11小时41分钟", "4小时52分钟", "34分钟", "2小时"
    """
    if text is None:
        return None
    t = str(text).strip()
    if not t or ("小时" not in t and "分钟" not in t):
        return None

    hours = 0
    minutes = 0

    hm = re.search(r"(\d+)\s*小时", t)
    if hm:
        hours = int(hm.group(1))
    mm = re.search(r"(\d+)\s*分钟", t)
    if mm:
        minutes = int(mm.group(1))

    if hours == 0 and minutes == 0:
        return None
    return hours * 60 + minutes
