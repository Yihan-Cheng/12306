/**
 * Phase 2: China rail map + 24h segment simulation (constant speed between stops).
 * Expects simulation.json or falls back to data/simulation_demo.json
 */

/* global L */

const DAY_MIN = 1440;

function formatClock(t) {
  const m = Math.floor(t % DAY_MIN);
  const h = Math.floor(m / 60);
  const min = m % 60;
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

/**
 * @returns {number|null} fraction along segment [0,1], or null if not running
 */
function segmentFraction(t, seg) {
  const dep = seg.dep;
  const arr = seg.arr;
  if (arr <= dep) return null;
  if (dep < DAY_MIN && arr <= DAY_MIN) {
    if (t >= dep && t < arr) return (t - dep) / (arr - dep);
    return null;
  }
  if (dep < DAY_MIN && arr > DAY_MIN) {
    if (t >= dep && t < DAY_MIN) return (t - dep) / (arr - dep);
    if (t < arr - DAY_MIN) return (t + DAY_MIN - dep) / (arr - dep);
    return null;
  }
  return null;
}

function interpolatePos(stations, seg, frac) {
  const a = stations[seg.from];
  const b = stations[seg.to];
  if (!a || !b) return null;
  const [latA, lngA] = a;
  const [latB, lngB] = b;
  return [latA + (latB - latA) * frac, lngA + (lngB - lngA) * frac];
}

/** 车次首字母 → 填充色、描边色（中国铁路常见字头） */
function trainColorStyle(trainNo) {
  const s = String(trainNo || "").trim().toUpperCase();
  const c = s.charAt(0);
  if (/[A-Z]/.test(c)) {
    switch (c) {
      case "G":
        return { fill: "#d62828", stroke: "#ffb3b3" };
      case "D":
        return { fill: "#f77f00", stroke: "#ffe0bf" };
      case "C":
        return { fill: "#e63946", stroke: "#ffc9cc" };
      case "K":
        return { fill: "#1d4ed8", stroke: "#bfdbfe" };
      case "T":
        return { fill: "#0d9488", stroke: "#99f6e4" };
      case "Z":
        return { fill: "#7c3aed", stroke: "#ddd6fe" };
      case "S":
        return { fill: "#059669", stroke: "#a7f3d0" };
      case "Y":
        return { fill: "#db2777", stroke: "#fbcfe8" };
      case "L":
        return { fill: "#92400e", stroke: "#fde68a" };
      case "F":
        return { fill: "#ea580c", stroke: "#fed7aa" };
      default:
        return { fill: "#64748b", stroke: "#cbd5e1" };
    }
  }
  if (/^\d/.test(s)) {
    return { fill: "#475569", stroke: "#94a3b8" };
  }
  return { fill: "#64748b", stroke: "#cbd5e1" };
}

function buildLegendHtml() {
  const items = [
    ["G", "#d62828"],
    ["D", "#f77f00"],
    ["C", "#e63946"],
    ["K", "#1d4ed8"],
    ["T", "#0d9488"],
    ["Z", "#7c3aed"],
    ["S", "#059669"],
    ["数字", "#475569"],
  ];
  return items
    .map(
      ([lab, col]) =>
        `<span class="sw" style="background:${col}" title="${lab}"></span>${lab}`,
    )
    .join("");
}

async function loadData() {
  const urls = ["data/simulation.json", "data/simulation_demo.json"];
  for (const url of urls) {
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) continue;
      const j = await r.json();
      if (j.stations && Object.keys(j.stations).length) return j;
    } catch {
      /* try next */
    }
  }
  throw new Error("No simulation data. Run phase2/prepare_simulation_data.py after geocoding.");
}

function main() {
  const map = L.map("map", {
    preferCanvas: true,
    zoomControl: true,
    minZoom: 3,
    maxZoom: 12,
  }).setView([35.0, 105.0], 4);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
    maxZoom: 19,
  }).addTo(map);

  const edgeLayer = L.layerGroup().addTo(map);
  const stationLayer = L.layerGroup().addTo(map);
  const trainLayer = L.layerGroup().addTo(map);

  const elTime = document.getElementById("time-readout");
  const elSlider = document.getElementById("time-slider");
  const elPlay = document.getElementById("btn-play");
  const elSpeed = document.getElementById("speed");
  const elStats = document.getElementById("stats");
  const elMeta = document.getElementById("meta-line");
  const elLegend = document.getElementById("train-legend");

  let data = null;
  let t = 7 * 60; // start 07:00
  let playing = false;
  let speed = 1;
  let lastFrame = performance.now();
  /** Upper bound on simultaneous train dots (memory / canvas cost). Raise if needed. */
  const MAX_DRAW_CAP = 200000;
  /** Reused circle markers — avoid clearLayers + recreate every frame */
  const trainMarkerPool = [];
  /** Same list as drawn markers; used for pixel hit-test on hover */
  let lastDrawnPts = [];
  let hoverFrozen = false;
  const HOVER_PX = 14;
  const elTrainHover = document.getElementById("train-hover");

  function syncSlider() {
    elSlider.value = String(t);
    elTime.textContent = formatClock(t);
  }

  function renderStatic(stations, edges) {
    edgeLayer.clearLayers();
    stationLayer.clearLayers();
    const bounds = [];

    for (const e of edges) {
      L.polyline(e.coords, {
        color: "#3d6b5a",
        weight: 1,
        opacity: 0.35,
        interactive: false,
      }).addTo(edgeLayer);
      for (const c of e.coords) {
        bounds.push(c);
      }
    }

    for (const [name, ll] of Object.entries(stations)) {
      L.circleMarker(ll, {
        radius: 2,
        fillColor: "#8a9aa8",
        color: "#2a3542",
        weight: 0.5,
        opacity: 0.9,
        fillOpacity: 0.7,
      })
        .bindTooltip(name, { sticky: true, direction: "top" })
        .addTo(stationLayer);
      bounds.push(ll);
    }

    if (bounds.length) {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 7 });
    }
  }

  function ensureTrainMarkerPool(need) {
    const want = Math.min(Math.max(need, 0), MAX_DRAW_CAP);
    while (trainMarkerPool.length < want) {
      const m = L.circleMarker([0, 0], {
        radius: 3,
        fillColor: "#64748b",
        color: "#cbd5e1",
        weight: 0.6,
        opacity: 0,
        fillOpacity: 0,
        interactive: false,
      });
      m.addTo(trainLayer);
      trainMarkerPool.push(m);
    }
  }

  function renderTrains() {
    if (!data || !data.segments) return;

    const pts = [];
    for (const seg of data.segments) {
      const f = segmentFraction(t, seg);
      if (f == null) continue;
      const pos = interpolatePos(data.stations, seg, f);
      if (!pos) continue;
      pts.push({ pos, train: seg.train, from: seg.from, to: seg.to });
    }

    const n = Math.min(pts.length, MAX_DRAW_CAP);
    ensureTrainMarkerPool(n);
    lastDrawnPts = pts.slice(0, n);

    const poolLen = trainMarkerPool.length;
    for (let i = 0; i < poolLen; i += 1) {
      const m = trainMarkerPool[i];
      if (i < n) {
        const p = pts[i];
        const col = trainColorStyle(p.train);
        m.setLatLng(p.pos);
        m.setStyle({
          fillColor: col.fill,
          color: col.stroke,
          opacity: 1,
          fillOpacity: 0.92,
        });
      } else {
        m.setStyle({ opacity: 0, fillOpacity: 0 });
      }
    }

    const capped = pts.length > MAX_DRAW_CAP;
    elStats.textContent = `Active: ${pts.length} (draw ${n}${capped ? `, cap ${MAX_DRAW_CAP}` : ""}) · Stations: ${Object.keys(data.stations).length} · Segments: ${data.segments.length}`;
  }

  function pickTrainAtContainerPoint(containerPoint) {
    if (!lastDrawnPts.length) return null;
    let best = null;
    let bestD = HOVER_PX + 1;
    for (const p of lastDrawnPts) {
      const pt = map.latLngToContainerPoint(L.latLng(p.pos[0], p.pos[1]));
      const dx = pt.x - containerPoint.x;
      const dy = pt.y - containerPoint.y;
      const d = Math.hypot(dx, dy);
      if (d < bestD) {
        bestD = d;
        best = p;
      }
    }
    return bestD <= HOVER_PX ? best : null;
  }

  function setTrainHoverUI(picked) {
    if (!elTrainHover) return;
    if (!picked) {
      elTrainHover.hidden = true;
      elTrainHover.textContent = "";
      return;
    }
    elTrainHover.hidden = false;
    elTrainHover.innerHTML = `悬停暂停 · 车次 <kbd>${picked.train}</kbd>　${picked.from} → ${picked.to}`;
  }

  function onMapMouseMove(e) {
    if (!data) return;
    const cp =
      e.containerPoint != null
        ? e.containerPoint
        : e.originalEvent
          ? map.mouseEventToContainerPoint(e.originalEvent)
          : map.latLngToContainerPoint(e.latlng);
    const picked = pickTrainAtContainerPoint(cp);
    const nextFrozen = picked != null;
    if (nextFrozen !== hoverFrozen) {
      hoverFrozen = nextFrozen;
      map.getContainer().style.cursor = hoverFrozen ? "pointer" : "";
    }
    setTrainHoverUI(picked);
  }

  function onMapMouseOut() {
    hoverFrozen = false;
    map.getContainer().style.cursor = "";
    setTrainHoverUI(null);
  }

  function tick(now) {
    if (playing && !hoverFrozen) {
      // Clamp dt to avoid huge jumps (tab hidden / GC pause) which look like teleporting.
      const dt = Math.min(0.05, (now - lastFrame) / 1000);
      lastFrame = now;
      t = (t + speed * dt + DAY_MIN) % DAY_MIN;
      elSlider.value = String(t);
    } else {
      lastFrame = now;
    }
    elTime.textContent = formatClock(t);
    renderTrains();
    requestAnimationFrame(tick);
  }

  elSlider.addEventListener("input", () => {
    t = Number(elSlider.value);
    elTime.textContent = formatClock(t);
    lastFrame = performance.now();
  });

  elPlay.addEventListener("click", () => {
    playing = !playing;
    elPlay.textContent = playing ? "Pause" : "Play";
    elPlay.classList.toggle("primary", playing);
    lastFrame = performance.now();
  });

  elSpeed.addEventListener("change", () => {
    speed = Number(elSpeed.value);
  });

  loadData()
    .then((j) => {
      data = j;
      elMeta.textContent = j.meta
        ? `crawl: ${j.meta.crawl_date || "—"} · edges ${j.meta.edge_count ?? "—"} · segments ${j.meta.segment_count ?? j.segments?.length ?? "—"}`
        : "";
      elSlider.min = "0";
      elSlider.max = String(DAY_MIN - 0.01);
      elSlider.step = "0.25";
      elSlider.value = String(t);
      syncSlider();
      if (elLegend) elLegend.innerHTML = buildLegendHtml();
      renderStatic(j.stations, j.edges || []);
      renderTrains();
      map.on("mousemove", onMapMouseMove);
      map.on("mouseout", onMapMouseOut);
      requestAnimationFrame(tick);
    })
    .catch((e) => {
      elMeta.textContent = String(e.message);
    });
}

main();
