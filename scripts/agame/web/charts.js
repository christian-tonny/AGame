/* AGame SVG charts: honest gaps (null breaks lines), tap/hover/keyboard inspection,
   accessible summaries and hidden data tables. Drawn at the container's real width. */
"use strict";
const CHART_SPECS = {};
let chartSeq = 0;
const toMs = x => (typeof x === "string" ? Date.parse(x.length === 10 ? x + "T12:00:00Z" : x) : x);

function chart(spec) {
  const id = spec.id || "ch" + (++chartSeq);
  CHART_SPECS[id] = spec;
  const h = spec.h || 170;
  return `<div class="chart" id="${id}" tabindex="0" role="img" aria-label="${esc(spec.label || "Chart")}" style="min-height:${h}px"></div>${dataTable(spec)}
    ${spec.legend !== false && spec.series && spec.series.length > 1 ? `<div class="chart-legend">${spec.series.filter(s => !s.noLegend).map(s => `<span><i style="background:${s.color}${s.dash ? ";background:repeating-linear-gradient(90deg," + s.color + " 0 4px,transparent 4px 7px)" : ""}"></i>${esc(s.name)}</span>`).join("")}${spec.band && spec.band.name ? `<span><i style="background:${spec.band.color || "var(--surface-3)"};height:8px"></i>${esc(spec.band.name)}</span>` : ""}</div>` : ""}
    ${spec.range ? `<div class="chart-range">${esc(spec.range)}</div>` : ""}`;
}

function dataTable(spec) {
  if (!spec.x || !spec.series) return "";
  const n = spec.x.length;
  const step = Math.max(1, Math.ceil(n / 40));
  const fx = spec.fmtX || (v => String(v));
  let rows = "";
  for (let i = 0; i < n; i += step) {
    rows += `<tr><th>${esc(fx(spec.x[i]))}</th>${spec.series.map(s => `<td>${s.values[i] === null || s.values[i] === undefined ? "no data" : esc((s.fmt || spec.fmtY || (v => fmt.n(v, 1)))(s.values[i]))}</td>`).join("")}</tr>`;
  }
  return `<table class="sr"><caption>${esc(spec.label || "Chart data")}</caption><tr><th>${esc(spec.xName || "x")}</th>${spec.series.map(s => `<th>${esc(s.name)}</th>`).join("")}</tr>${rows}</table>`;
}

function niceTicks(min, max, n = 4) {
  if (!isFinite(min) || !isFinite(max)) return [];
  if (min === max) { min -= 1; max += 1; }
  const span = max - min, raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || mag * 10;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
  return out;
}

function drawCharts(root) {
  $$(".chart[id]", root || document).forEach(el => {
    const s = CHART_SPECS[el.id];
    if (!s) return;
    const w = Math.max(240, Math.round(el.clientWidth || 320));
    let svg;
    try {
      svg = { line: lineSvg, bar: barSvg, hypno: hypnoSvg, curve: curveSvg, profile: profileSvg }[s.type || "line"](s, w);
    } catch (e) { console.error(e); svg = `<p class="cap">Chart unavailable</p>`; }
    el.innerHTML = svg;
    bindChart(el, s);
  });
}
let resizeT;
window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => drawCharts(), 150); });

function layout(s, w) {
  const h = s.h || 170;
  const padL = s.padL !== undefined ? s.padL : 34, padR = s.series && s.series.some(x => x.axis === "right") ? 34 : 8;
  return { w, h, padL, padR, padT: 8, padB: s.noX ? 6 : 20, iw: w - padL - padR, ih: h - 8 - (s.noX ? 6 : 20) };
}

function yScale(vals, s, L, axis) {
  let lo = Infinity, hi = -Infinity;
  vals.forEach(v => { if (isNum(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); } });
  if (axis !== "right" && s.band) {
    const b = s.band;
    (Array.isArray(b.low) ? b.low : [b.low]).forEach(v => isNum(v) && (lo = Math.min(lo, v)));
    (Array.isArray(b.high) ? b.high : [b.high]).forEach(v => isNum(v) && (hi = Math.max(hi, v)));
  }
  (s.refLines || []).forEach(r => { if (isNum(r.y) && (r.axis || "left") === (axis || "left")) { lo = Math.min(lo, r.y); hi = Math.max(hi, r.y); } });
  if (axis !== "right") { if (isNum(s.yMin)) lo = s.yMin; if (isNum(s.yMax)) hi = s.yMax; }
  if (!isFinite(lo)) { lo = 0; hi = 1; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08;
  if (!(axis !== "right" && isNum(s.yMin))) lo -= pad;
  if (!(axis !== "right" && isNum(s.yMax))) hi += pad;
  if (s.zeroBase && axis !== "right") lo = Math.min(0, lo);
  const inv = axis === "right" ? false : !!s.invertY;
  const f = v => L.padT + (inv ? (v - lo) / (hi - lo) : (hi - v) / (hi - lo)) * L.ih;
  f.lo = lo; f.hi = hi;
  return f;
}

function xScale(xs, L) {
  const ms = xs.map(toMs);
  const lo = Math.min(...ms), hi = Math.max(...ms);
  const f = i => L.padL + (hi === lo ? L.iw / 2 : (ms[i] - lo) / (hi - lo) * L.iw);
  f.ms = ms; f.lo = lo; f.hi = hi;
  return f;
}

function pathFor(xs, vals, X, Y, gapMs, from = 0, to = vals.length - 1) {
  let d = "", pen = false;
  for (let i = from; i <= to; i++) {
    const v = vals[i];
    if (!isNum(v)) { pen = false; continue; }
    if (pen && gapMs && X.ms[i] - X.ms[i - 1] > gapMs) pen = false;
    d += (pen ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1);
    pen = true;
  }
  return d;
}

function axes(s, L, Y, X, Yr) {
  let g = `<g class="grid">`;
  const ticks = niceTicks(Y.lo, Y.hi, s.yTicks || 4);
  const tstep = ticks.length > 1 ? Math.abs(ticks[1] - ticks[0]) : 1;
  const fy = s.fmtYAxis || (v => fmt.n(v, tstep < 1 ? (tstep < 0.1 ? 2 : 1) : 0));
  ticks.forEach(t => { const y = Y(t); if (y >= L.padT - 1 && y <= L.padT + L.ih + 1) g += `<line x1="${L.padL}" x2="${L.w - L.padR}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}"/>`; });
  g += `</g><g class="axis">`;
  ticks.forEach(t => { const y = Y(t); if (y >= L.padT - 1 && y <= L.padT + L.ih + 1) g += `<text x="${L.padL - 5}" y="${(y + 3).toFixed(1)}" text-anchor="end">${esc(fy(t))}</text>`; });
  if (Yr) niceTicks(Yr.lo, Yr.hi, 4).forEach(t => { const y = Yr(t); if (y >= L.padT && y <= L.padT + L.ih) g += `<text x="${L.w - L.padR + 5}" y="${(y + 3).toFixed(1)}">${esc((s.fmtYRight || (v => fmt.n(v)))(t))}</text>`; });
  if (!s.noX && X) {
    const n = s.x.length;
    const want = Math.max(2, Math.min(s.xTicks || 5, Math.floor(L.iw / 64)));
    const fx = s.fmtXAxis || s.fmtX || (v => String(v));
    let last = -1e9;
    for (let k = 0; k < want; k++) {
      const i = Math.round(k * (n - 1) / Math.max(1, want - 1));
      const x = X(i);
      if (x - last < 40) continue;
      last = x;
      g += `<text x="${x.toFixed(1)}" y="${L.h - 5}" text-anchor="${k === 0 ? "start" : k === want - 1 ? "end" : "middle"}">${esc(fx(s.x[i]))}</text>`;
    }
  }
  return g + "</g>";
}

function lineSvg(s, w) {
  const L = layout(s, w);
  const X = xScale(s.x, L);
  const left = s.series.filter(x => x.axis !== "right"), right = s.series.filter(x => x.axis === "right");
  const Y = yScale(left.flatMap(x => x.values), s, L);
  const Yr = right.length ? yScale(right.flatMap(x => x.values), s, L, "right") : null;
  let body = "";
  if (s.band) {
    const b = s.band;
    if (Array.isArray(b.low)) {
      let top = "", bot = "";
      for (let i = 0; i < s.x.length; i++) if (isNum(b.low[i]) && isNum(b.high[i])) { top += (top ? "L" : "M") + X(i).toFixed(1) + " " + Y(b.high[i]).toFixed(1); }
      for (let i = s.x.length - 1; i >= 0; i--) if (isNum(b.low[i]) && isNum(b.high[i])) { bot += "L" + X(i).toFixed(1) + " " + Y(b.low[i]).toFixed(1); }
      if (top) body += `<path d="${top}${bot}Z" fill="${b.color || "var(--surface-3)"}" opacity="${b.opacity || 0.6}"/>`;
    } else if (isNum(b.low) && isNum(b.high)) {
      const y1 = Y(b.high), y2 = Y(b.low);
      body += `<rect x="${L.padL}" y="${Math.min(y1, y2).toFixed(1)}" width="${L.iw}" height="${Math.abs(y2 - y1).toFixed(1)}" fill="${b.color || "var(--surface-3)"}" opacity="${b.opacity || 0.55}"/>`;
    }
  }
  if (isNum(s.hatchFrom) && s.hatchFrom < s.x.length) {
    const x0 = X(s.hatchFrom);
    body += `<defs><pattern id="h-${esc(s.id || "x")}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="var(--line-2)" stroke-width="2"/></pattern></defs>
      <rect x="${x0.toFixed(1)}" y="${L.padT}" width="${(L.w - L.padR - x0).toFixed(1)}" height="${L.ih}" fill="url(#h-${esc(s.id || "x")})" opacity=".5"/>
      <text x="${(x0 + 4).toFixed(1)}" y="${L.padT + 10}" fill="var(--text-3)" font-size="10">${esc(s.hatchLabel || "Projection")}</text>`;
  }
  (s.refLines || []).forEach(r => { const YY = r.axis === "right" ? Yr : Y; const y = YY(r.y); body += `<line x1="${L.padL}" x2="${L.w - L.padR}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${r.color || "var(--text-3)"}" stroke-dasharray="4 3"/>${r.label ? `<text x="${L.w - L.padR - 2}" y="${(y - 3).toFixed(1)}" text-anchor="end" fill="${r.color || "var(--text-3)"}" font-size="10">${esc(r.label)}</text>` : ""}`; });
  s.series.forEach(se => {
    const YY = se.axis === "right" ? Yr : Y;
    const n = se.values.length;
    if (se.area) {
      const base = YY(Math.max(YY.lo, Math.min(YY.hi, se.areaBase !== undefined ? se.areaBase : YY.lo)));
      let d = "", start = null, last = null;
      for (let i = 0; i < n; i++) {
        const v = se.values[i];
        if (!isNum(v)) { if (start !== null) { d += `L${X(last).toFixed(1)} ${base.toFixed(1)}L${X(start).toFixed(1)} ${base.toFixed(1)}Z`; start = null; } continue; }
        if (start === null) { start = i; d += `M${X(i).toFixed(1)} ${YY(v).toFixed(1)}`; } else d += `L${X(i).toFixed(1)} ${YY(v).toFixed(1)}`;
        last = i;
      }
      if (start !== null) d += `L${X(last).toFixed(1)} ${base.toFixed(1)}L${X(start).toFixed(1)} ${base.toFixed(1)}Z`;
      body += `<path d="${d}" fill="${se.color}" opacity="${se.areaOpacity || 0.22}"/>`;
    }
    if (isNum(se.dashFrom)) {
      body += `<path d="${pathFor(s.x, se.values, X, YY, s.gapMs, 0, se.dashFrom)}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2}" stroke-linejoin="round"/>`;
      body += `<path d="${pathFor(s.x, se.values, X, YY, s.gapMs, se.dashFrom, n - 1)}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2}" stroke-dasharray="5 4"/>`;
    } else if (!se.noLine) {
      body += `<path d="${pathFor(s.x, se.values, X, YY, s.gapMs)}" fill="none" stroke="${se.color}" stroke-width="${se.width || 2}" stroke-linejoin="round" stroke-linecap="round" ${se.dash ? 'stroke-dasharray="5 4"' : ""}/>`;
    }
    if (se.dots) {
      for (let i = 0; i < n; i++) if (isNum(se.values[i])) body += `<circle cx="${X(i).toFixed(1)}" cy="${YY(se.values[i]).toFixed(1)}" r="${se.dotR || 2.6}" fill="${se.color}"/>`;
    }
  });
  return `<svg viewBox="0 0 ${L.w} ${L.h}" width="${L.w}" height="${L.h}">${axes(s, L, Y, X, Yr)}${body}
    <line class="xh" x1="0" x2="0" y1="${L.padT}" y2="${L.padT + L.ih}" visibility="hidden"/><g class="hl"></g>
    <rect class="hit" x="${L.padL}" y="0" width="${L.iw}" height="${L.h}"/></svg>`;
}

function barSvg(s, w) {
  const L = layout(s, w);
  const n = s.x.length;
  const sums = s.stacked ? s.x.map((_, i) => s.series.reduce((a, se) => a + (isNum(se.values[i]) ? se.values[i] : 0), 0)) : s.series.flatMap(x => x.values);
  const Y = yScale(sums.concat(s.zeroBase === false ? [] : [0]), Object.assign({}, s, { zeroBase: true }), L);
  const bw = L.iw / n;
  const X = i => L.padL + bw * (i + 0.5);
  X.ms = s.x.map((_, i) => i);
  let body = "";
  if (s.band && isNum(s.band.low)) {
    const y1 = Y(s.band.high), y2 = Y(s.band.low);
    body += `<rect x="${L.padL}" y="${Math.min(y1, y2).toFixed(1)}" width="${L.iw}" height="${Math.abs(y2 - y1).toFixed(1)}" fill="${s.band.color || "var(--surface-3)"}" opacity=".7"/>`;
  }
  const inner = Math.max(2, bw * (s.barWidth || 0.62));
  for (let i = 0; i < n; i++) {
    let acc = 0;
    s.series.forEach((se, k) => {
      const v = se.values[i];
      if (!isNum(v)) {
        if (!s.stacked && se.missingMark !== false) body += `<rect x="${(X(i) - inner / 2).toFixed(1)}" y="${(Y(0) - 2).toFixed(1)}" width="${inner.toFixed(1)}" height="2" fill="var(--line-2)"/>`;
        return;
      }
      const w2 = s.stacked ? inner : inner / s.series.length;
      const x0 = s.stacked ? X(i) - inner / 2 : X(i) - inner / 2 + k * w2;
      const y0 = s.stacked ? Y(acc + v) : Y(Math.max(0, v));
      const y1 = s.stacked ? Y(acc) : Y(Math.min(0, v));
      const col = typeof se.color === "function" ? se.color(i, v) : se.color;
      body += `<rect x="${x0.toFixed(1)}" y="${Math.min(y0, y1).toFixed(1)}" width="${Math.max(1, w2 - (s.stacked ? 0 : 1)).toFixed(1)}" height="${Math.max(1, Math.abs(y1 - y0)).toFixed(1)}" rx="${Math.min(3, w2 / 3).toFixed(1)}" fill="${col}" ${s.partialIndex === i ? 'opacity=".55"' : ""}/>`;
      if (s.stacked) acc += v;
    });
  }
  (s.refLines || []).forEach(r => { const y = Y(r.y); body += `<line x1="${L.padL}" x2="${L.w - L.padR}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${r.color || "var(--text-3)"}" stroke-dasharray="4 3"/>`; });
  const Xax = Object.assign(i => X(i), { ms: X.ms });
  return `<svg viewBox="0 0 ${L.w} ${L.h}" width="${L.w}" height="${L.h}">${axes(s, L, Y, Xax)}${body}<line class="xh" x1="0" x2="0" y1="${L.padT}" y2="${L.padT + L.ih}" visibility="hidden"/><g class="hl"></g><rect class="hit" x="${L.padL}" y="0" width="${L.iw}" height="${L.h}"/></svg>`;
}

const STAGE_ROW = { awake: 0, rem: 1, core: 2, deep: 3, asleep_unspecified: 2 };
const STAGE_COLOR = { awake: "var(--st-awake)", rem: "var(--st-rem)", core: "var(--st-core)", deep: "var(--st-deep)", asleep_unspecified: "var(--st-core)" };
function hypnoSvg(s, w) {
  const L = { w, h: s.h || 150, padL: 44, padR: 6, padT: 6, padB: 18 };
  L.iw = L.w - L.padL - L.padR; L.ih = L.h - L.padT - L.padB;
  const t0 = Date.parse(s.start), t1 = Date.parse(s.end);
  const X = t => L.padL + (t - t0) / (t1 - t0) * L.iw;
  const rh = L.ih / 4;
  let g = "";
  ["Awake", "REM", "Core", "Deep"].forEach((lab, i) => { g += `<text x="${L.padL - 6}" y="${(L.padT + rh * i + rh / 2 + 3).toFixed(1)}" text-anchor="end" fill="var(--text-3)" font-size="10">${lab}</text><line x1="${L.padL}" x2="${L.w - L.padR}" y1="${(L.padT + rh * (i + 1)).toFixed(1)}" y2="${(L.padT + rh * (i + 1)).toFixed(1)}" stroke="var(--line)"/>`; });
  s.segments.forEach(seg => {
    const r = STAGE_ROW[seg.stage];
    if (r === undefined) return;
    const a = X(Date.parse(seg.start)), b = X(Date.parse(seg.end));
    g += `<rect x="${a.toFixed(1)}" y="${(L.padT + rh * r + 2).toFixed(1)}" width="${Math.max(1, b - a).toFixed(1)}" height="${(rh - 4).toFixed(1)}" rx="2" fill="${STAGE_COLOR[seg.stage]}"/>`;
  });
  g += `<text x="${L.padL}" y="${L.h - 4}" fill="var(--text-3)" font-size="10">${esc(fmt.time(s.start))}</text><text x="${L.w - L.padR}" y="${L.h - 4}" text-anchor="end" fill="var(--text-3)" font-size="10">${esc(fmt.time(s.end))}</text>`;
  s._X = X; s._t0 = t0; s._t1 = t1; s._L = L;
  return `<svg viewBox="0 0 ${L.w} ${L.h}" width="${L.w}" height="${L.h}">${g}<line class="xh" x1="0" x2="0" y1="${L.padT}" y2="${L.padT + L.ih}" visibility="hidden"/><rect class="hit" x="${L.padL}" y="0" width="${L.iw}" height="${L.h}"/></svg>`;
}

function curveSvg(s, w) {
  const xs = s.points.map(p => Math.log(p.s));
  const spec = Object.assign({}, s, { x: xs, series: [{ name: s.name || "Best", color: s.color || "var(--accent)", values: s.points.map(p => p.v), dots: true, width: 2.2 }],
    fmtX: v => durLabel(Math.round(Math.exp(v))), fmtXAxis: v => durLabel(Math.round(Math.exp(v))) });
  CHART_SPECS[s._id || ""] = spec;
  s.x = xs; s.series = spec.series; s.fmtX = spec.fmtX;
  return lineSvg(spec, w);
}
function durLabel(sec) { return sec < 60 ? sec + "s" : sec < 3600 ? Math.round(sec / 60) + "m" : (sec / 3600).toFixed(sec % 3600 ? 1 : 0) + "h"; }

function profileSvg(s, w) {
  const spec = Object.assign({}, s, { x: s.points.map(p => p.d), series: [{ name: "Elevation", color: "var(--text-2)", values: s.points.map(p => p.e), area: true, areaOpacity: 0.25 }],
    fmtX: v => fmt.dist(v), fmtXAxis: v => fmt.distNum(v, 1), fmtY: v => fmt.elev(v), fmtYAxis: v => fmt.n(IMPERIAL ? v * 3.28084 : v) });
  s.x = spec.x; s.series = spec.series; s.fmtX = spec.fmtX; s.fmtY = spec.fmtY;
  return lineSvg(spec, w);
}

function bindChart(el, s) {
  const svg = el.querySelector("svg");
  if (!svg) return;
  const hit = svg.querySelector(".hit"), xh = svg.querySelector(".xh");
  if (!hit) return;
  const vb = svg.viewBox.baseVal;
  let idx = null;
  const n = s.type === "hypno" ? 0 : (s.x || []).length;
  function locate(clientX) {
    const r = svg.getBoundingClientRect();
    const x = (clientX - r.left) * vb.width / r.width;
    if (s.type === "hypno") return x;
    const L = layout(s, vb.width);
    if (s.type === "bar") return Math.max(0, Math.min(n - 1, Math.floor((x - L.padL) / (L.iw / n))));
    const X = xScale(s.x, L);
    let best = 0, bd = 1e9;
    for (let i = 0; i < n; i++) { const d = Math.abs(X(i) - x); if (d < bd) { bd = d; best = i; } }
    return best;
  }
  function show(i, cx, cy) {
    if (s.type === "hypno") {
      const t = s._t0 + (i - s._L.padL) / s._L.iw * (s._t1 - s._t0);
      const seg = s.segments.find(g => Date.parse(g.start) <= t && t <= Date.parse(g.end));
      xh.setAttribute("x1", i); xh.setAttribute("x2", i); xh.setAttribute("visibility", "visible");
      showTip(cx, cy, seg ? `<b>${esc(fmt.sport(seg.stage))}</b><br><span class="k">${fmt.time(seg.start)}–${fmt.time(seg.end)} · ${fmt.hm((Date.parse(seg.end) - Date.parse(seg.start)) / 60000)}</span>` : `<span class="k">${fmt.time(new Date(t).toISOString())}</span>`);
      return;
    }
    idx = i;
    const L = layout(s, vb.width);
    const x = s.type === "bar" ? L.padL + (L.iw / n) * (i + 0.5) : xScale(s.x, L)(i);
    xh.setAttribute("x1", x); xh.setAttribute("x2", x); xh.setAttribute("visibility", "visible");
    const fx = s.fmtX || (v => String(v));
    const rows = s.series.map(se => {
      const v = se.values[i];
      const f = se.fmt || s.fmtY || (q => fmt.n(q, 1));
      return `<div><span style="color:${se.color}">●</span> ${esc(se.name)}: <b>${v === null || v === undefined ? "no data" : esc(f(v))}</b></div>`;
    }).join("");
    const extra = s.tipExtra ? s.tipExtra(i) : "";
    let px = cx, py = cy;
    if (px === undefined) { const r = svg.getBoundingClientRect(); px = r.left + x * r.width / vb.width; py = r.top + 20; }
    showTip(px, py, `<div class="k">${esc(fx(s.x[i]))}</div>${rows}${extra}`);
  }
  hit.addEventListener("pointermove", e => show(locate(e.clientX), e.clientX, e.clientY));
  hit.addEventListener("pointerdown", e => show(locate(e.clientX), e.clientX, e.clientY));
  hit.addEventListener("pointerleave", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
  if (s.onPick) hit.addEventListener("click", e => { const i = locate(e.clientX); s.onPick(i); });
  el.addEventListener("keydown", e => {
    if (s.type === "hypno" || !n) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      idx = idx === null ? n - 1 : Math.max(0, Math.min(n - 1, idx + (e.key === "ArrowRight" ? 1 : -1)));
      show(idx);
    }
    if (e.key === "Enter" && s.onPick && idx !== null) s.onPick(idx);
  });
  el.addEventListener("blur", () => { xh.setAttribute("visibility", "hidden"); hideTip(); });
}

/* ---------- small helpers ---------- */
function sparkline(values, color, h = 28) {
  const vs = values.filter(isNum);
  if (vs.length < 2) return "";
  const lo = Math.min(...vs), hi = Math.max(...vs), w = 100;
  let d = "", pen = false;
  values.forEach((v, i) => { if (!isNum(v)) { pen = false; return; } const x = i / (values.length - 1) * w, y = h - 2 - (hi === lo ? 0.5 : (v - lo) / (hi - lo)) * (h - 4); d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); pen = true; });
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" style="width:100%;height:${h}px" aria-hidden="true"><path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>`;
}
const RANGES = [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["12m", "1Y"], ["24m", "2Y"]];
const RANGES_DWMY = [["7", "W"], ["30", "M"], ["90", "3M"], ["365", "Y"], ["all", "All"]];
function rangeDays(r) { return { "1m": 30, "3m": 91, "6m": 183, "12m": 365, "24m": 730, "7": 7, "30": 30, "90": 90, "365": 365, all: 100000 }[r] || 90; }
function sliceDays(rows, days, key = "date") {
  if (days >= 100000) return rows;
  const end = Date.parse(D.meta.build_date + "T12:00:00Z");
  return rows.filter(r => end - toMs(r[key]) <= days * 86400000);
}
function rangeLabel(rows, key = "date") {
  if (!rows.length) return "";
  return `${fmt.date(rows[0][key], { day: "numeric", month: "short", year: "numeric" })} – ${fmt.date(rows[rows.length - 1][key], { day: "numeric", month: "short", year: "numeric" })}`;
}
