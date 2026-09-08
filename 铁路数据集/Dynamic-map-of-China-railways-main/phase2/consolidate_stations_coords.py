"""
Merge every project CSV/JSON coordinate source that can be aligned to
`data/output/stations.csv` into one wide table.

- stations_geo*.csv: match on `station_name` (exact, after strip).
- cnstation*.csv under data/output: match on canonical_key(站名) ==
  canonical_key(station_name from stations.csv).
- phase2/web/data/simulation.json: `stations` map name -> [lat, lng] WGS84.
- data/cache/baidu_geocode_cache.json: key `baidu:` + geocode query (name + 站 if needed).

Excludes name-only lists: cnstation_missing*, station_compare*.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from phase1.parsers import normalize_station_name

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data/output/stations_coords_merged.csv"


def canonical_key(name: str) -> str:
    t = normalize_station_name(name)
    while t.endswith("站"):
        t = t[:-1]
    return normalize_station_name(t)


def build_query(station_name: str) -> str:
    s = (station_name or "").strip()
    if not s:
        return s
    if s.endswith("站"):
        return s
    return s + "站"


def file_slug(path: Path) -> str:
    s = path.stem
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s)
    return s.strip("_") or path.name


def load_stations_order(path: Path) -> list[str]:
    out: list[str] = []
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            n = (row.get("station_name") or "").strip()
            if n:
                out.append(n)
    return out


def load_geo_csv(path: Path) -> dict[str, dict[str, str]]:
    """station_name -> all columns."""
    if not path.exists():
        return {}
    out: dict[str, dict[str, str]] = {}
    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "station_name" not in reader.fieldnames:
            return {}
        for row in reader:
            name = (row.get("station_name") or "").strip()
            if not name:
                continue
            out[name] = {k: (v if v is not None else "") for k, v in row.items()}
    return out


def load_cnstation_csv(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    """canonical_key -> row (prefer row with more coordinate fields filled). Returns (map, column names)."""
    if not path.exists():
        return {}, []
    rows_by_key: dict[str, dict[str, str]] = {}
    cols: list[str] = []

    def score(row: dict[str, str]) -> int:
        keys = ("WGS84_Lng", "WGS84_Lat", "BD_Lng", "BD_Lat", "lng火星", "lat火星")
        return sum(1 for k in keys if (row.get(k) or "").strip())

    with open(path, encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "站名" not in reader.fieldnames:
            return {}, list(reader.fieldnames or [])
        cols = list(reader.fieldnames)
        for row in reader:
            raw = (row.get("站名") or "").strip()
            if not raw:
                continue
            key = canonical_key(raw)
            clean = {k: (v if v is not None else "") for k, v in row.items()}
            prev = rows_by_key.get(key)
            if prev is None or score(clean) > score(prev):
                rows_by_key[key] = clean
    return rows_by_key, cols


def load_simulation_stations(path: Path) -> dict[str, tuple[str, str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    st = data.get("stations") or {}
    out: dict[str, tuple[str, str]] = {}
    if not isinstance(st, dict):
        return out
    for name, pair in st.items():
        if not isinstance(name, str) or not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        lat, lng = pair[0], pair[1]
        out[name.strip()] = (str(lng), str(lat))
    return out


def load_baidu_cache(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def should_skip_csv(path: Path) -> bool:
    name = path.name
    if name.startswith("station_compare"):
        return True
    if name.startswith("cnstation_missing"):
        return True
    return False


def discover_csv_sources(out_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for pattern in ("stations_geo*.csv", "cnstation*.csv"):
        paths.extend(sorted(out_dir.glob(pattern)))
    return [p for p in paths if p.is_file() and not should_skip_csv(p)]


def main() -> None:
    stations_path = ROOT / "data/output/stations.csv"
    names = load_stations_order(stations_path)
    if not names:
        print(f"No stations in {stations_path}")
        return

    fieldnames: list[str] = ["station_name", "canonical_key"]
    rows_out: list[dict[str, str]] = []

    # Preload all sources
    geo_sources: list[tuple[str, dict[str, dict[str, str]]]] = []
    cn_sources: list[tuple[str, dict[str, dict[str, str]], list[str]]] = []

    for path in discover_csv_sources(ROOT / "data/output"):
        slug = file_slug(path)
        if path.name.startswith("stations_geo"):
            geo_sources.append((slug, load_geo_csv(path)))
        elif path.name.startswith("cnstation"):
            mp, cols = load_cnstation_csv(path)
            cn_sources.append((slug, mp, cols))

    sim_path = ROOT / "phase2/web/data/simulation.json"
    sim_stations = load_simulation_stations(sim_path)
    cache_raw = load_baidu_cache(ROOT / "data/cache/baidu_geocode_cache.json")

    for slug, _ in geo_sources:
        for col in ("lng", "lat", "source", "query", "address"):
            fieldnames.append(f"{slug}__{col}")

    for slug, _mp, cols in cn_sources:
        for c in cols:
            fieldnames.append(f"{slug}__{c}")

    fieldnames.extend(["simulation_json__lng", "simulation_json__lat"])

    cache_fields = ("bd_lng", "bd_lat", "gcj_lng", "gcj_lat", "wgs_lng", "wgs_lat", "address")
    for c in cache_fields:
        fieldnames.append(f"baidu_geocode_cache__{c}")

    for name in names:
        ck = canonical_key(name)
        row: dict[str, str] = {"station_name": name, "canonical_key": ck}

        for slug, mp in geo_sources:
            g = mp.get(name)
            for col in ("lng", "lat", "source", "query", "address"):
                key = f"{slug}__{col}"
                row[key] = (g or {}).get(col, "") if g else ""

        for slug, mp, cols in cn_sources:
            cnr = mp.get(ck)
            for c in cols:
                row[f"{slug}__{c}"] = (cnr or {}).get(c, "") if cnr else ""

        slng, slat = sim_stations.get(name, ("", ""))
        row["simulation_json__lng"] = slng
        row["simulation_json__lat"] = slat

        cache_key = "baidu:" + build_query(name)
        ent = cache_raw.get(cache_key)
        if isinstance(ent, dict):
            for c in cache_fields:
                v = ent.get(c)
                row[f"baidu_geocode_cache__{c}"] = "" if v is None else str(v)
        else:
            for c in cache_fields:
                row[f"baidu_geocode_cache__{c}"] = ""

        rows_out.append(row)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_out)

    # Summary
    def has_wgs(r: dict[str, str], lng_key: str, lat_key: str) -> bool:
        return bool((r.get(lng_key) or "").strip() and (r.get(lat_key) or "").strip())

    main_geo = file_slug(ROOT / "data/output/stations_geo.csv")
    n_geo = sum(1 for r in rows_out if has_wgs(r, f"{main_geo}__lng", f"{main_geo}__lat"))
    n_sim = sum(1 for r in rows_out if has_wgs(r, "simulation_json__lng", "simulation_json__lat"))
    n_cache = sum(1 for r in rows_out if has_wgs(r, "baidu_geocode_cache__wgs_lng", "baidu_geocode_cache__wgs_lat"))

    print(f"Wrote {OUTPUT} rows={len(rows_out)} cols={len(fieldnames)}")
    print(f"  With WGS in {main_geo}: {n_geo}")
    print(f"  With WGS in simulation.json: {n_sim}")
    print(f"  With WGS in baidu cache: {n_cache}")


if __name__ == "__main__":
    main()
