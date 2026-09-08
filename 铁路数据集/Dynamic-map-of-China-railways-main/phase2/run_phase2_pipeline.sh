#!/usr/bin/env bash
# Phase 2: geocode → prepare JSON → serve web UI (no comments in body: safe to paste/run)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/venv/bin/python3"
if [[ ! -x "$PY" ]]; then
  echo "Missing venv: $PY" >&2
  exit 1
fi

if [[ "${SKIP_GEOCODE:-0}" != "1" ]]; then
  if [[ -z "${BAIDU_MAP_AK:-}" ]]; then
    echo "Set BAIDU_MAP_AK to your Baidu Maps server ak (https://lbsyun.baidu.com/apiconsole/key)" >&2
    exit 1
  fi
  "$PY" -m phase2.geocode_stations --provider baidu
else
  echo "SKIP_GEOCODE=1: skipping geocode_stations"
fi

"$PY" -m phase2.prepare_simulation_data
echo "Starting http://127.0.0.1:8765/ (Ctrl+C to stop)"
cd "${ROOT}/phase2/web"
exec python3 -m http.server 8765
