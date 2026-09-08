# -*- coding: utf-8 -*-
"""JR 风格 · 上海虹桥站大屏：全字段机械翻牌 + 站台状态联动 + 检票滚动条。"""
import json, pathlib

D = json.load(open('board_data.json', encoding='utf-8'))
T = D['trains']

def jdump(v):
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))

trains_js = jdump(T)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>JR-虹桥 · 上海虹桥站列车信息大屏</title>
<meta name="viewport" content="width=device-width,initial-scale=1" />
<style>
:root {
  --bg-1: #0A121E;
  --bg-2: #0D1A28;
  --bg-3: #112233;
  --border: #1A2838;
  --border-soft: #16253A;
  --text-1: #E9F1FB;
  --text-2: #9DB1C8;
  --text-mute: #55677F;
  --text-dim: #3A4A60;
  --cyan: #38D8FF;
  --green: #2BE8A5;
  --green-dim: #0C2A20;
  --green-line: #1A4A37;
  --amber: #FFB02E;
  --amber-dim: #2A1E0A;
  --amber-line: #4A3512;
  --rose: #FF4D6A;
  --rose-dim: #2A0F16;
  --rose-line: #4D1B26;
  --violet: #6C7BFF;
  --row-stripe: #0E1A28;
  /* JR 列车种别色（発標） */
  --kind-g: #17365C;  --kind-g-b: #102642;  /* 高速动车 G */
  --kind-d: #14453C;  --kind-d-b: #0D2E28;  /* 动车组 D */
  --kind-c: #2C2148;  --kind-c-b: #1E1733;  /* 城际动车 C */
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body {
  background: linear-gradient(160deg, #080E1A 0%, #05080F 100%);
  color: var(--text-1);
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif;
  -webkit-font-smoothing: antialiased;
  min-height: 100vh;
}
.app { max-width: 1600px; margin: 0 auto; padding: 28px; }

/* ================= 机械翻牌单元 ================= */
.sf {
  --sf-w: 13px; --sf-h: 22px; --sf-fs: 15px;
  --c-top-a: #24374E; --c-top-b: #1B2A3D;
  --c-bot-a: #1B2A3D; --c-bot-b: #131F2F;
  --sf-fg: #E9F1FB;
  position: relative; display: inline-block;
  width: var(--sf-w); height: var(--sf-h);
  perspective: 320px; vertical-align: middle;
  border-radius: 3px;
}
.sf[data-v=""] { opacity: .28; }
.sf-t, .sf-b {
  position: absolute; left: 0; right: 0; height: 50%;
  overflow: hidden; backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
.sf-t {
  top: 0; border-radius: 3px 3px 0 0; transform-origin: 50% 100%;
  background: linear-gradient(180deg, var(--c-top-a), var(--c-top-b));
}
.sf-b {
  bottom: 0; border-radius: 0 0 3px 3px; transform-origin: 50% 0%;
  background: linear-gradient(180deg, var(--c-bot-a), var(--c-bot-b));
}
.sf-t::before, .sf-b::before {
  content: attr(data-c);
  position: absolute; left: 0; right: 0;
  height: var(--sf-h); line-height: var(--sf-h);
  text-align: center;
  font-family: 'JetBrains Mono', 'SF Mono', monospace;
  font-size: var(--sf-fs); font-weight: 700;
  color: var(--sf-fg);
}
.sf-t::before { top: 0; }
.sf-b::before { top: calc(var(--sf-h) / -2); }
.sf::after {
  content: ''; position: absolute; left: 0; right: 0; top: 50%;
  height: 1px; margin-top: -.5px;
  background: rgba(0,0,0,.5); z-index: 3; pointer-events: none;
}
.sf-flip.sf-t { z-index: 4; animation: sfFT .17s cubic-bezier(.45,.05,.7,.4) both; }
.sf-flip.sf-b { z-index: 4; animation: sfFB .17s .17s cubic-bezier(.3,.55,.5,1) both; }
@keyframes sfFT { from { transform: rotateX(0deg); } to { transform: rotateX(-90deg); } }
@keyframes sfFB { from { transform: rotateX(90deg); } to { transform: rotateX(0deg); } }

/* 种别色变体 */
.sf.kind-G { --c-top-a: var(--kind-g); --c-top-b: var(--kind-g-b); --c-bot-a: var(--kind-g-b); --c-bot-b: #0C1C31; }
.sf.kind-D { --c-top-a: var(--kind-d); --c-top-b: var(--kind-d-b); --c-bot-a: var(--kind-d-b); --c-bot-b: #09221E; }
.sf.kind-C { --c-top-a: var(--kind-c); --c-top-b: var(--kind-c-b); --c-bot-a: var(--kind-c-b); --c-bot-b: #161129; }
.sf.sm { --sf-w: 12px; --sf-h: 20px; --sf-fs: 14px; }
.sf.lg { --sf-w: 14px; --sf-h: 24px; --sf-fs: 17px; }

.sf-group { display: inline-flex; gap: 2px; align-items: center; }

/* ================= 页头 ================= */
.header {
  display: flex; align-items: center; justify-content: space-between;
  height: 76px; margin-bottom: 16px;
}
.brand { display: flex; align-items: center; gap: 14px; }
.logo {
  width: 46px; height: 46px; border-radius: 13px;
  background: var(--bg-2); border: 1px solid #1E3450;
  display: flex; align-items: center; justify-content: center;
}
.brand-text h1 { font-size: 25px; font-weight: 700; letter-spacing: 1px; color: var(--text-1); }
.brand-text p {
  font-size: 10px; font-weight: 500; letter-spacing: 2.4px;
  color: var(--text-mute); margin-top: 4px; text-transform: uppercase;
}
.header-right { display: flex; align-items: center; gap: 20px; }

/* 大翻页时钟 */
.flap-clock { display: flex; align-items: center; gap: 5px; }
.flap-clock .sf { --sf-w: 42px; --sf-h: 62px; --sf-fs: 42px; border-radius: 7px; }
.flap-clock .sf-t { border-radius: 7px 7px 0 0; }
.flap-clock .sf-b { border-radius: 0 0 7px 7px; }
.flap-colon {
  font-family: 'JetBrains Mono', monospace;
  font-size: 30px; font-weight: 700; color: var(--text-mute);
  animation: blink 2s steps(1) infinite;
}
@keyframes blink { 0%,49% { opacity: 1; } 50%,100% { opacity: .35; } }
.date-col { text-align: right; }
.date-col div:first-child { font-size: 12px; color: var(--text-2); }
.date-col div:last-child { font-size: 11px; color: var(--text-mute); margin-top: 3px; }

/* ================= 指标区 ================= */
.stats {
  display: grid;
  grid-template-columns: 168px 300px 1.15fr 1fr;
  gap: 14px; margin-bottom: 16px;
}
.stat-card {
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 14px; padding: 13px 16px; height: 112px;
  display: flex; flex-direction: column;
  position: relative; overflow: hidden;
}
.stat-card::before {
  content: ""; position: absolute; inset: 0;
  background: radial-gradient(ellipse at top right, rgba(56,216,255,.05), transparent 60%);
  pointer-events: none;
}
.stat-label {
  display: flex; align-items: center; gap: 7px;
  font-size: 11px; color: var(--text-2); letter-spacing: .6px;
  margin-bottom: 8px; flex-shrink: 0;
}
.stat-dot { width: 6px; height: 6px; border-radius: 50%; }
.stat-sub { font-size: 11px; color: var(--text-mute); margin-top: auto; flex-shrink: 0; }
.stat-big {
  font-family: 'JetBrains Mono', monospace;
  font-size: 30px; font-weight: 700;
  letter-spacing: -.5px; color: var(--cyan);
  font-variant-numeric: tabular-nums; line-height: 1.05;
}

.next-body { display: flex; align-items: center; gap: 14px; }
.next-time {
  font-family: 'JetBrains Mono', monospace;
  font-size: 32px; font-weight: 700; color: var(--violet);
  font-variant-numeric: tabular-nums; letter-spacing: -.5px; line-height: 1;
}
.next-meta { display: flex; flex-direction: column; gap: 3px; }
.next-train {
  font-family: 'JetBrains Mono', monospace;
  font-size: 15px; font-weight: 600; color: var(--text-1);
}
.next-dest { font-size: 12px; color: var(--text-2); }

/* 正在检票 —— 横向无缝滚动 */
.check-viewport {
  position: relative; flex: 1; overflow: hidden;
  display: flex; align-items: center;
  -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 22px, #000 calc(100% - 22px), transparent 100%);
          mask-image: linear-gradient(90deg, transparent 0, #000 22px, #000 calc(100% - 22px), transparent 100%);
}
.check-track {
  display: flex; align-items: center; gap: 6px;
  white-space: nowrap; will-change: transform;
}
.check-track.scrolling {
  animation: marquee linear infinite;
  animation-duration: var(--dur, 32s);
}
.check-track.scrolling:hover { animation-play-state: paused; }
@keyframes marquee {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}
.check-item {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 0 9px; height: 24px; border-radius: 7px;
  background: var(--amber-dim); border: 1px solid var(--amber-line);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px; font-weight: 600; color: var(--amber);
  flex-shrink: 0;
}
.check-item .g { color: #C08A28; font-size: 11px; font-weight: 500; }
.check-empty { font-size: 12px; color: var(--text-mute); }

/* 站台实时状态图 */
.plat-count {
  margin-left: auto; font-family: 'JetBrains Mono', monospace;
  font-size: 11px; font-weight: 600; color: var(--cyan);
}
.plat-grid {
  display: grid; grid-template-columns: repeat(15, 1fr);
  gap: 4px; flex-shrink: 0;
}
.plat-cell {
  height: 16px; border-radius: 3px;
  background: #0C1622; border: 1px solid #152334;
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px; font-weight: 500; color: #2E4055;
  display: flex; align-items: center; justify-content: center;
  transition: background .35s ease, color .35s ease, border-color .35s ease, box-shadow .35s ease;
}
.plat-cell.st-准点  { background: #10394C; border-color: #1D6076; color: #7FE3FF; box-shadow: 0 0 7px rgba(56,216,255,.18) inset; }
.plat-cell.st-正在检票 { background: #3A2A0C; border-color: #6B4E14; color: #FFD27A; box-shadow: 0 0 7px rgba(255,176,46,.25) inset; }
.plat-cell.st-停止检票 { background: #3A1119; border-color: #6E1E2B; color: #FF8A9E; box-shadow: 0 0 7px rgba(255,77,106,.25) inset; }
.plat-legend {
  display: flex; gap: 10px; align-items: center;
  margin-top: auto; padding-top: 6px; flex-shrink: 0;
}
.plat-legend span {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 9px; color: var(--text-dim); letter-spacing: .3px;
}
.plat-legend i { width: 7px; height: 7px; border-radius: 2px; display: inline-block; }

/* ================= 大屏面板 ================= */
.panel {
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 16px; overflow: hidden; margin-bottom: 16px;
  box-shadow: 0 20px 60px -30px rgba(0,0,0,.8);
}
.panel-head {
  display: grid;
  grid-template-columns: 4px 172px 1fr 1fr 116px 116px 92px 118px 168px;
  align-items: center; height: 44px;
  padding: 0 24px; background: var(--bg-2);
  border-bottom: 1px solid var(--border-soft);
}
.panel-head .h { font-size: 11px; font-weight: 500; color: var(--text-mute); letter-spacing: 1px; }
.panel-head .h.col-from, .panel-head .h.col-to { padding-left: 20px; }
.panel-head .h.col-train { padding-left: 18px; }
.panel-head .h.center { text-align: center; }

.row {
  display: grid;
  grid-template-columns: 4px 172px 1fr 1fr 116px 116px 92px 118px 168px;
  align-items: center; height: 50px;
  padding: 0 24px;
  border-bottom: 1px solid rgba(255,255,255,0.02);
  transition: opacity .3s ease, transform .3s ease;
}
.row:nth-child(odd) { background: var(--row-stripe); }
.row:hover { background: #162840; }
.row.hidden { opacity: 0; transform: translateY(6px); pointer-events: none; }
.row .accent { width: 4px; height: 100%; align-self: stretch; border-radius: 2px; transition: background .3s ease; }
.row .cell { display: flex; flex-direction: column; }
.row .cell-train { padding-left: 18px; }
.row .cell-station { padding-left: 20px; }
.row .cell-center { display: flex; align-items: center; justify-content: center; }
.train-type { font-size: 10px; color: var(--text-dim); margin-top: 3px; letter-spacing: .3px; }
.station-name {
  font-size: 16px; font-weight: 500; color: #FFFFFF;
  letter-spacing: .5px;
}
.station-name.dim { color: var(--text-dim); }

.status-pill {
  display: inline-flex; align-items: center; gap: 7px;
  padding: 0 13px; height: 28px; border-radius: 14px;
  font-size: 13px; font-weight: 600; white-space: nowrap;
  transition: background .32s ease, color .32s ease, border-color .32s ease;
}
.status-pill .d { width: 6px; height: 6px; border-radius: 50%; transition: background .32s ease, box-shadow .32s ease; }
.status-pill.s-准点 { background: var(--green-dim); border: 1px solid var(--green-line); color: var(--green); }
.status-pill.s-准点 .d { background: var(--green); box-shadow: 0 0 6px var(--green); }
.status-pill.s-正在检票 { background: var(--amber-dim); border: 1px solid var(--amber-line); color: var(--amber); }
.status-pill.s-正在检票 .d { background: var(--amber); box-shadow: 0 0 8px var(--amber); animation: glow-amber 1.4s infinite; }
.status-pill.s-停止检票 { background: var(--rose-dim); border: 1px solid var(--rose-line); color: var(--rose); }
.status-pill.s-停止检票 .d { background: var(--rose); box-shadow: 0 0 8px var(--rose); animation: glow-rose .8s infinite; }
.status-pill.flip { animation: pillFlip .42s cubic-bezier(.3,.6,.4,1); }
@keyframes pillFlip { 0% { transform: rotateX(-88deg); opacity: .25; } 100% { transform: rotateX(0deg); opacity: 1; } }
@keyframes glow-amber { 0%,100% { box-shadow: 0 0 4px var(--amber); } 50% { box-shadow: 0 0 14px var(--amber); } }
@keyframes glow-rose { 0%,100% { box-shadow: 0 0 4px var(--rose); } 50% { box-shadow: 0 0 14px var(--rose); } }
.row .accent.s-准点 { background: var(--green); }
.row .accent.s-正在检票 { background: var(--amber); }
.row .accent.s-停止检票 { background: var(--rose); }

/* ================= 时间轴 ================= */
.timebar {
  background: var(--bg-1); border: 1px solid var(--border);
  border-radius: 16px; padding: 18px;
  display: flex; flex-direction: column; gap: 12px;
}
.control-row { display: flex; align-items: center; justify-content: space-between; }
.control-left { display: flex; align-items: center; gap: 14px; }
.play-btn {
  width: 36px; height: 36px; border-radius: 50%;
  background: var(--bg-2); border: 1px solid #24405C;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: var(--cyan);
  transition: background .2s, transform .1s;
}
.play-btn:hover { background: #1F3550; }
.play-btn:active { transform: scale(.95); }
.time-display {
  font-family: 'JetBrains Mono', monospace;
  font-size: 24px; font-weight: 700; color: var(--cyan);
  font-variant-numeric: tabular-nums; letter-spacing: .5px;
}
.hint { font-size: 11px; color: var(--text-mute); }
.control-right { display: flex; align-items: center; gap: 18px; }
.legend { display: flex; gap: 16px; }
.legend-item { display: flex; align-items: center; gap: 7px; font-size: 12px; font-weight: 500; color: var(--text-2); }
.legend-item .d { width: 8px; height: 8px; border-radius: 50%; }
.speed-grp {
  display: flex; gap: 4px; padding: 4px;
  background: var(--bg-2); border: 1px solid var(--border); border-radius: 12px;
}
.speed-chip {
  display: inline-flex; align-items: center; justify-content: center;
  height: 28px; padding: 0 14px; border-radius: 9px;
  cursor: pointer; font-family: 'JetBrains Mono', monospace;
  font-size: 12px; font-weight: 600; color: var(--text-mute);
  transition: background .15s, color .15s;
}
.speed-chip.active { background: #1C3B57; color: #9FD8F5; }
.speed-chip:hover:not(.active) { color: var(--text-2); }

.slider-area { display: flex; flex-direction: column; gap: 8px; }
.track-zone { position: relative; height: 26px; display: flex; align-items: center; }
.track { position: absolute; left: 0; right: 0; height: 6px; background: var(--bg-3); border-radius: 3px; border: 1px solid var(--border-soft); }
.track-fill {
  position: absolute; left: 0; height: 6px;
  background: linear-gradient(90deg, var(--cyan), var(--violet));
  border-radius: 3px; box-shadow: 0 0 12px rgba(56,216,255,.35);
  transition: width .12s linear;
}
input[type="range"].slider {
  position: absolute; inset: 0; width: 100%; height: 100%;
  -webkit-appearance: none; appearance: none; background: transparent; cursor: pointer; margin: 0;
}
input[type="range"].slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--cyan); border: 3px solid #071320;
  box-shadow: 0 0 0 1px rgba(56,216,255,.3), 0 0 16px rgba(56,216,255,.55);
  cursor: grab; transition: transform .1s;
}
input[type="range"].slider::-webkit-slider-thumb:active { transform: scale(1.15); cursor: grabbing; }
input[type="range"].slider::-moz-range-thumb {
  width: 18px; height: 18px; border-radius: 50%;
  background: var(--cyan); border: 3px solid #071320;
  box-shadow: 0 0 0 1px rgba(56,216,255,.3), 0 0 16px rgba(56,216,255,.55); cursor: grab;
}
.ticks { position: absolute; inset: 0; pointer-events: none; }
.tick { position: absolute; top: 21px; width: 1px; height: 5px; background: #22344A; }
.tick.t-now { background: #3E6480; }
.labels {
  display: flex; justify-content: space-between; align-items: center;
  height: 18px; font-family: 'JetBrains Mono', monospace;
  font-size: 10px; font-weight: 500; color: var(--text-mute);
}
.foot {
  margin-top: 16px; text-align: center; font-size: 10px;
  letter-spacing: 1.2px; color: var(--text-mute); text-transform: uppercase;
}
</style>
</head>
<body>
<div class="app">
  <header class="header">
    <div class="brand">
      <div class="logo">
        <svg width="46" height="46" viewBox="0 0 46 46" xmlns="http://www.w3.org/2000/svg">
          <circle cx="18" cy="18" r="3.2" fill="#38D8FF"/>
          <circle cx="28" cy="18" r="3.2" fill="#38D8FF"/>
          <rect x="13" y="26" width="20" height="4" rx="2" fill="#2BE8A5"/>
          <rect x="17" y="32" width="12" height="3" rx="1.5" fill="#1F3B52"/>
        </svg>
      </div>
      <div class="brand-text">
        <h1>上海虹桥站</h1>
        <p>JR-HONGQIAO &nbsp;·&nbsp; SHANGHAI</p>
      </div>
    </div>
    <div class="header-right">
      <div class="flap-clock" id="clock"></div>
      <div class="date-col">
        <div>2026年9月3日</div>
        <div>星期四</div>
      </div>
    </div>
  </header>

  <section class="stats">
    <div class="stat-card">
      <div class="stat-label"><span class="stat-dot" style="background:var(--cyan)"></span>在港车次</div>
      <div class="stat-big" id="kpi-board">31</div>
      <div class="stat-sub">未来 60 分钟内</div>
    </div>

    <div class="stat-card">
      <div class="stat-label"><span class="stat-dot" style="background:var(--violet)"></span>最近发车</div>
      <div class="next-body">
        <div class="next-time" id="kpi-next">18:09</div>
        <div class="next-meta">
          <div class="next-train" id="kpi-next-train">G298</div>
          <div class="next-dest" id="kpi-next-dest">开往 徐州东</div>
        </div>
      </div>
      <div class="stat-sub" id="kpi-next-gate">检票口 8A/B · 8 站台 · 还有 1 分钟</div>
    </div>

    <div class="stat-card">
      <div class="stat-label"><span class="stat-dot" style="background:var(--amber)"></span>正在检票<span class="plat-count" id="kpi-chk-n"></span></div>
      <div class="check-viewport"><div class="check-track" id="kpi-checking"></div></div>
    </div>

    <div class="stat-card">
      <div class="stat-label">
        <span class="stat-dot" style="background:var(--cyan)"></span>站台实时状态
        <span class="plat-count" id="kpi-plat">16/30</span>
      </div>
      <div class="plat-grid" id="plat-grid"></div>
      <div class="plat-legend">
        <span><i style="background:#10394C;border:1px solid #1D6076"></i>准点</span>
        <span><i style="background:#3A2A0C;border:1px solid #6B4E14"></i>检票中</span>
        <span><i style="background:#3A1119;border:1px solid #6E1E2B"></i>停止检票</span>
        <span><i style="background:#0C1622;border:1px solid #152334"></i>空闲</span>
      </div>
    </div>
  </section>

  <section class="panel">
    <div class="panel-head">
      <span></span>
      <span class="h col-train">车次 TRAIN</span>
      <span class="h col-from">始发站 FROM</span>
      <span class="h col-to">终到站 TO</span>
      <span class="h center">到点 ARR</span>
      <span class="h center">开点 DEP</span>
      <span class="h center">站台 PLAT.</span>
      <span class="h center">检票口 GATE</span>
      <span class="h center">状态 STATUS</span>
    </div>
    <div id="rows"></div>
  </section>

  <section class="timebar">
    <div class="control-row">
      <div class="control-left">
        <button class="play-btn" id="play-btn" aria-label="播放">
          <svg id="play-icon" width="14" height="14" viewBox="0 0 36 36" xmlns="http://www.w3.org/2000/svg">
            <path d="M14 11L25 18L14 25V11Z" fill="currentColor"/>
          </svg>
        </button>
        <span class="time-display" id="t-now">18:08</span>
        <span class="hint">拖动滑块同步刷新全站状态 · 或点击播放自动推进</span>
      </div>
      <div class="control-right">
        <div class="legend">
          <span class="legend-item"><span class="d" style="background:var(--green)"></span>准点</span>
          <span class="legend-item"><span class="d" style="background:var(--amber)"></span>正在检票</span>
          <span class="legend-item"><span class="d" style="background:var(--rose)"></span>停止检票</span>
        </div>
        <div class="speed-grp" id="speed-grp">
          <span class="speed-chip active" data-speed="1">1×</span>
          <span class="speed-chip" data-speed="4">4×</span>
          <span class="speed-chip" data-speed="16">16×</span>
        </div>
      </div>
    </div>
    <div class="slider-area">
      <div class="track-zone">
        <div class="track"></div>
        <div class="track-fill" id="track-fill"></div>
        <div class="ticks">
          <span class="tick" style="left:0%"></span>
          <span class="tick" style="left:16.67%"></span>
          <span class="tick" style="left:33.33%"></span>
          <span class="tick" style="left:50%"></span>
          <span class="tick t-now" style="left:66.67%"></span>
          <span class="tick" style="left:83.33%"></span>
          <span class="tick" style="left:calc(100% - 1px)"></span>
        </div>
        <input class="slider" id="slider" type="range" min="360" max="1440" step="1" value="1088" />
      </div>
      <div class="labels">
        <span>06:00</span><span>09:00</span><span>12:00</span>
        <span>15:00</span><span>18:00</span><span>21:00</span><span>24:00</span>
      </div>
    </div>
  </section>

  <div class="foot">JR-虹桥 · 上海虹桥站列车信息大屏 · 模拟实时调度</div>
</div>

<script>
const TRAINS = __TRAINS__;
const RANGE_START = 360, RANGE_END = 1440;
const LOOKAHEAD = 60, MAX_ROWS = 14, PLATFORMS = 30;
const FLIP_COOLDOWN = 620;   // 翻牌冷却：高速拖动时降级为直接更新，避免动画堆积

function fmt(m) {
  if (m == null) return '--:--';
  return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
}
function stateOf(t, now) {
  if (t.dm == null) return '准点';
  const dl = t.dm - now;
  if (dl <= 3) return '停止检票';
  if (dl <= 20) return '正在检票';
  return '准点';
}
function boardRows(now) {
  const out = [];
  for (const t of TRAINS) {
    if (t.dm != null) { if (now < t.dm && t.dm <= now + LOOKAHEAD) out.push(t); }
    else if (t.s <= now && now < t.s + 5) out.push(t);
  }
  out.sort((a, b) => (a.dm == null ? a.am : a.dm) - (b.dm == null ? b.am : b.dm));
  return out.slice(0, MAX_ROWS);
}
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ============ 翻牌单元 ============ */
function makeSF(kindCls, sizeCls) {
  const d = document.createElement('span');
  d.className = 'sf' + (kindCls ? ' ' + kindCls : '') + (sizeCls ? ' ' + sizeCls : '');
  d.dataset.v = '';
  const t = document.createElement('span'); t.className = 'sf-t';
  const b = document.createElement('span'); b.className = 'sf-b';
  d.appendChild(t); d.appendChild(b);
  return d;
}
function setSF(el, ch, delay, allowFlip) {
  if (el.dataset.v === ch) return;
  const prev = el.dataset.v;
  el.dataset.v = ch;
  const t = el.querySelector('.sf-t'), b = el.querySelector('.sf-b');
  if (el._tm) { clearTimeout(el._tm); el._tm = null; }
  el.querySelectorAll('.sf-flip').forEach(n => n.remove());
  if (!allowFlip || !prev) { t.dataset.c = ch; b.dataset.c = ch; return; }
  t.dataset.c = ch;        // 静态上半 = 新值（旧上半翻走后露出）
  b.dataset.c = prev;      // 静态下半 = 旧值（被新下半盖住）
  const ft = document.createElement('span'); ft.className = 'sf-flip sf-t'; ft.dataset.c = prev;
  const fb = document.createElement('span'); fb.className = 'sf-flip sf-b'; fb.dataset.c = ch;
  if (delay) { ft.style.animationDelay = delay + 'ms'; fb.style.animationDelay = (delay + 170) + 'ms'; }
  el.appendChild(ft); el.appendChild(fb);
  el._tm = setTimeout(() => {
    b.dataset.c = ch; ft.remove(); fb.remove(); el._tm = null;
  }, (delay || 0) + 380);
}
function makeGroup(n, kindCls, sizeCls) {
  const g = document.createElement('span');
  g.className = 'sf-group';
  const arr = [];
  for (let i = 0; i < n; i++) { const s = makeSF(kindCls, sizeCls); g.appendChild(s); arr.push(s); }
  return { g, arr };
}
function setGroup(g, str, allowFlip, step, base) {
  const s = String(str).padEnd(g.arr.length, ' ').slice(0, g.arr.length);
  for (let i = 0; i < g.arr.length; i++) {
    const ch = s[i] === ' ' ? '' : s[i];
    setSF(g.arr[i], ch, allowFlip ? (base + i * step) : 0, allowFlip);
  }
}
/* 种别色：按车次前缀判定列车等级（JR 発標 种别色） */
function kindOf(no) {
  const c = no.charAt(0).toUpperCase();
  if (c === 'G') return 'kind-G';
  if (c === 'D') return 'kind-D';
  if (c === 'C') return 'kind-C';
  return '';
}
function reKind(g, no) {
  const k = kindOf(no);
  g.arr.forEach(s => { s.classList.remove('kind-G', 'kind-D', 'kind-C'); if (k) s.classList.add(k); });
}

/* ============ 顶部大翻页时钟 ============ */
const clockRoot = document.getElementById('clock');
const clockSF = [];
const clockParts = [makeSF('', ''), makeSF('', ''), null, makeSF('', ''), makeSF('', '')];
clockParts.forEach((sf, i) => {
  if (!sf) {
    const c = document.createElement('span');
    c.className = 'flap-colon'; c.textContent = ':';
    clockRoot.appendChild(c); clockSF.push(null);
  } else { clockRoot.appendChild(sf); clockSF.push(sf); }
});

/* ============ 预建表格行 ============ */
const rowsWrap = document.getElementById('rows');
const rowEls = [];
for (let i = 0; i < MAX_ROWS; i++) {
  const el = document.createElement('div');
  el.className = 'row hidden';

  const accent = document.createElement('span'); accent.className = 'accent';
  const cTrain = document.createElement('div'); cTrain.className = 'cell cell-train';
  const gNo = makeGroup(5, '', 'sm');
  const typeEl = document.createElement('span'); typeEl.className = 'train-type';
  cTrain.appendChild(gNo.g); cTrain.appendChild(typeEl);

  const cFrom = document.createElement('div'); cFrom.className = 'cell cell-station';
  const fromEl = document.createElement('span'); fromEl.className = 'station-name';
  cFrom.appendChild(fromEl);

  const cTo = document.createElement('div'); cTo.className = 'cell cell-station';
  const toEl = document.createElement('span'); toEl.className = 'station-name';
  cTo.appendChild(toEl);

  const cArr = document.createElement('div'); cArr.className = 'cell-center';
  const gArr = makeGroup(5, '', ''); cArr.appendChild(gArr.g);
  const cDep = document.createElement('div'); cDep.className = 'cell-center';
  const gDep = makeGroup(5, '', 'lg'); cDep.appendChild(gDep.g);
  const cPlat = document.createElement('div'); cPlat.className = 'cell-center';
  const gPlat = makeGroup(2, '', 'lg'); cPlat.appendChild(gPlat.g);
  const cGate = document.createElement('div'); cGate.className = 'cell-center';
  const gGate = makeGroup(5, '', 'sm'); cGate.appendChild(gGate.g);

  const cStat = document.createElement('div'); cStat.className = 'cell-center';
  const pill = document.createElement('span'); pill.className = 'status-pill';
  const dot = document.createElement('span'); dot.className = 'd';
  const stTxt = document.createElement('span');
  pill.appendChild(dot); pill.appendChild(stTxt); cStat.appendChild(pill);

  el.append(accent, cTrain, cFrom, cTo, cArr, cDep, cPlat, cGate, cStat);
  rowsWrap.appendChild(el);
  rowEls.push({ el, accent, gNo, typeEl, fromEl, toEl, gArr, gDep, gPlat, gGate, pill, stTxt });
}

/* ============ 站台状态图 ============ */
const platGrid = document.getElementById('plat-grid');
const platCells = [];
for (let p = 1; p <= PLATFORMS; p++) {
  const c = document.createElement('div');
  c.className = 'plat-cell'; c.textContent = p;
  platGrid.appendChild(c); platCells.push(c);
}

/* ============ 渲染 ============ */
let lastFlipTs = 0;
let lastCheckKey = '';

function render(now, forceFlip) {
  const ts = performance.now();
  let allowFlip = !!forceFlip;
  if (!allowFlip && ts - lastFlipTs > FLIP_COOLDOWN) { allowFlip = true; }
  if (allowFlip) lastFlipTs = ts;

  /* 时钟翻页 */
  const s = fmt(now);
  setSF(clockSF[0], s[0], 0, allowFlip);
  setSF(clockSF[1], s[1], 40, allowFlip);
  setSF(clockSF[3], s[3], 80, allowFlip);
  setSF(clockSF[4], s[4], 120, allowFlip);
  document.getElementById('t-now').textContent = s;

  /* 表格 */
  const rows = boardRows(now);
  for (let i = 0; i < MAX_ROWS; i++) {
    const r = rowEls[i], t = rows[i];
    if (!t) {
      if (!r.el.classList.contains('hidden')) { r.el.classList.add('hidden'); r.el.dataset.no = ''; }
      continue;
    }
    const isNew = r.el.dataset.no !== t.n;
    r.el.dataset.no = t.n;
    r.el.classList.remove('hidden');
    const st = stateOf(t, now);
    const wave = allowFlip ? i * 26 : 0;

    reKind(r.gNo, t.n);
    setGroup(r.gNo, t.n, allowFlip, 22, wave);
    if (r.typeEl.textContent !== t.y) r.typeEl.textContent = t.y;
    if (r.fromEl.textContent !== t.o) r.fromEl.textContent = t.o;
    if (r.toEl.textContent !== t.g) r.toEl.textContent = t.g;
    setGroup(r.gArr, fmt(t.am), allowFlip, 20, wave + 60);
    setGroup(r.gDep, fmt(t.dm), allowFlip, 20, wave + 90);
    setGroup(r.gPlat, String(t.p), allowFlip, 30, wave + 120);
    setGroup(r.gGate, t.p + 'A/B', allowFlip, 20, wave + 140);
    r.toEl.classList.toggle('dim', t.dm == null);

    if (r.el.dataset.st !== st) {
      r.el.dataset.st = st;
      r.pill.className = 'status-pill s-' + st + (isNew ? '' : ' flip');
      r.stTxt.textContent = st;
      r.accent.className = 'accent s-' + st;
      if (!isNew) setTimeout(() => r.pill.classList.remove('flip'), 440);
    }
    if (isNew && allowFlip) {
      r.el.style.animation = 'none'; void r.el.offsetWidth;
      r.el.style.animation = '';
    }
  }

  /* 在港车次 */
  document.getElementById('kpi-board').textContent = rows.length;

  /* 最近发车 */
  const nt = rows.find(t => t.dm != null && t.dm > now) || null;
  if (nt) {
    document.getElementById('kpi-next').textContent = fmt(nt.dm);
    document.getElementById('kpi-next-train').textContent = nt.n;
    document.getElementById('kpi-next-dest').textContent = '开往 ' + nt.g;
    document.getElementById('kpi-next-gate').textContent =
      '检票口 ' + nt.p + 'A/B · ' + nt.p + ' 站台 · 还有 ' + (nt.dm - now) + ' 分钟';
  } else {
    document.getElementById('kpi-next').textContent = '--:--';
    document.getElementById('kpi-next-train').textContent = '——';
    document.getElementById('kpi-next-dest').textContent = '今日班次已结束';
    document.getElementById('kpi-next-gate').textContent = '';
  }

  /* 正在检票 —— 超 5 个则横向无缝滚动 */
  const checking = [];
  for (const t of TRAINS) {
    if (t.dm != null && t.dm > now && t.dm - now <= 20 && t.dm - now > 3) checking.push(t);
  }
  checking.sort((a, b) => a.dm - b.dm);
  const key = checking.map(t => t.n).join(',');
  if (key !== lastCheckKey) {
    lastCheckKey = key;
    const track = document.getElementById('kpi-checking');
    track.classList.remove('scrolling');
    track.style.animationDuration = '';
    if (!checking.length) {
      track.innerHTML = '<span class="check-empty">当前无检票车次</span>';
      document.getElementById('kpi-chk-n').textContent = '';
    } else {
      document.getElementById('kpi-chk-n').textContent = checking.length + ' 趟';
      const chips = checking.map(t =>
        '<span class="check-item">' + esc(t.n) + '<span class="g">' + t.p + 'A/B</span></span>').join('');
      track.innerHTML = chips + (checking.length > 5 ? chips : '');
      if (checking.length > 5) {
        requestAnimationFrame(() => {
          const half = track.scrollWidth / 2;
          track.style.setProperty('--dur', Math.max(14, half / 26).toFixed(1) + 's');
          track.classList.add('scrolling');
        });
      }
    }
  }

  /* 站台实时状态 —— 颜色与该站台当前列车状态严格对应 */
  const pstate = new Map(), ptrain = new Map();
  for (const t of TRAINS) {
    if (t.s <= now && now < t.e) { pstate.set(t.p, stateOf(t, now)); ptrain.set(t.p, t); }
  }
  for (let p = 1; p <= PLATFORMS; p++) {
    const c = platCells[p - 1], stt = pstate.get(p) || '';
    c.className = 'plat-cell' + (stt ? ' st-' + stt : '');
    const tr = ptrain.get(p);
    c.title = tr ? (p + ' 站台 · ' + tr.n + ' 开往' + tr.g + ' · ' + (stt || '空闲'))
                 : (p + ' 站台 · 空闲');
  }
  document.getElementById('kpi-plat').textContent = pstate.size + '/30';

  const frac = Math.max(0, Math.min(1, (now - RANGE_START) / (RANGE_END - RANGE_START)));
  document.getElementById('track-fill').style.width = (frac * 100) + '%';
  document.getElementById('slider').value = now;
}

/* ============ 交互 ============ */
const slider = document.getElementById('slider');
let rafId = null, pending = null;
function schedule(now) {
  pending = now;
  if (rafId) return;
  rafId = requestAnimationFrame(() => { rafId = null; if (pending != null) render(pending); });
}
slider.addEventListener('input', e => { stopPlay(); schedule(parseInt(e.target.value, 10)); });

const playBtn = document.getElementById('play-btn');
const playIcon = document.getElementById('play-icon');
let playTimer = null, playSpeed = 1;
function setIcon(on) {
  playIcon.innerHTML = on
    ? '<rect x="12" y="11" width="4" height="14" fill="currentColor"/><rect x="20" y="11" width="4" height="14" fill="currentColor"/>'
    : '<path d="M14 11L25 18L14 25V11Z" fill="currentColor"/>';
}
function startPlay() {
  playBtn.classList.add('playing'); setIcon(true);
  playTimer = setInterval(() => {
    let now = parseInt(slider.value, 10) + playSpeed;
    if (now > RANGE_END) now = RANGE_START;
    slider.value = now; schedule(now);
  }, 1000);
}
function stopPlay() {
  playBtn.classList.remove('playing'); setIcon(false);
  if (playTimer) { clearInterval(playTimer); playTimer = null; }
}
playBtn.addEventListener('click', () => { if (playTimer) stopPlay(); else startPlay(); });
document.querySelectorAll('.speed-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.speed-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    playSpeed = parseInt(chip.dataset.speed, 10);
    if (playTimer) { stopPlay(); startPlay(); }
  });
});

render(parseInt(slider.value, 10), true);
</script>
</body>
</html>
"""

HTML = HTML.replace('__TRAINS__', trains_js)
out = pathlib.Path('JR-虹桥_车站大屏.html')
out.write_text(HTML, encoding='utf-8')
print('wrote', out.name, len(HTML), 'bytes')
