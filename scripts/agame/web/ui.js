/* AGame components. Pure presentation of computed values. */
"use strict";

/* ---------- copy catalog (exact empty-state strings; tested) ---------- */
const STR = {
  noRoute: "Route data unavailable",
  noVO2: "No cardio-fitness samples yet",
  noNutrition: "Nutrition not connected",
  noLeaderboard: "No leaderboard data connected",
  noPower: "Power meter not connected",
  noExercise: "No exercise details, so muscles are not inferred",
  sleepNotSynced: "Sleep not synced yet",
  noData: "No data yet",
  waiting: `Waiting for ${AGENT}'s first sync`,
  noGoals: "No goals set",
  noPlan: "Nothing planned",
  noCoachLLM: "Coach chat not connected",
  noMap: "Map provider not configured",
  companion: "Companion not connected",
  noClubs: "No clubs connected",
  noChallenges: "No challenges joined",
  noFeed: "No activity feed connected",
  noPrehab: "No prehab routines yet",
  noRecords: "No health records added",
  noWeight: "No weigh-ins yet",
  hrMax: "HR max not configured",
  edits: "Edits need connection",
};

/* ---------- provenance registry ---------- */
const PROV = {};
let provSeq = 0;
function prov(v, label) {
  if (!v || typeof v !== "object") return "";
  const id = "p" + (++provSeq);
  PROV[id] = { v, label };
  return `<button type="button" class="info-btn" data-prov="${id}" aria-label="Data details for ${esc(label || "value")}" title="Data details">${icon("info")}</button>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-prov]");
  if (!b) return;
  e.preventDefault(); e.stopPropagation();
  const { v, label } = PROV[b.dataset.prov] || {};
  if (!v) return;
  const rows = [["Value", isNum(v.v) ? fmt.n(v.v, Math.abs(v.v) < 10 && v.v % 1 ? 1 : 0) + (v.unit ? " " + v.unit : "") : (v.v === null || v.v === undefined ? "Unknown" : esc(String(v.v)))],
    ["Status", statusLabel(v.status)], ["Kind", kindLabel(v.kind)], ["As of", v.as_of ? fmt.dt(v.as_of) : "—"],
    ["Source", v.source || "—"], ["Method", v.method || "—"],
    ["Coverage", isNum(v.coverage) ? fmt.pct(v.coverage * 100) : "—"], ["Confidence", v.confidence || "—"], ["Note", v.note || "—"]];
  openSheet(label || "Data details", `<table class="tbl">${rows.map(([k, x]) => `<tr><th>${k}</th><td>${x}</td></tr>`).join("")}</table>
    <p class="cap" style="margin-top:12px">Computed once in Python at build time. Missing data is never shown as zero.</p>`);
});
function statusLabel(s) { return ({ ok: "Fresh", partial: "Partial", stale: "Stale", missing: "Missing", calibrating: "Calibrating" })[s] || s || "—"; }
function kindLabel(k) { return ({ observed: "Observed (HealthKit)", configured: "Configured", computed: "Computed", estimated: "Estimate", user_entered: "Entered by you" })[k] || k || "—"; }

/* ---------- primitives ---------- */
function empty(title, sub, extra = "") {
  return `<div class="empty" role="note"><b>${esc(title)}</b>${sub ? `<span class="cap">${esc(sub)}</span>` : ""}${extra}</div>`;
}
function stLine(v) {
  if (!v || !v.status || v.status === "ok") return "";
  const txt = v.status === "stale" ? `Last updated ${fmt.ago(v.as_of)}` : v.status === "partial" ? (v.note || "Partial data") :
    v.status === "calibrating" ? "Calibrating" : (v.note || "Missing");
  return `<div class="st-line ${v.status}"><span class="dot"></span>${esc(txt)}</div>`;
}
function val(v, d = 0, unit) {
  if (!v || !isNum(v.v)) return "—";
  return fmt.n(v.v, d) + (unit !== undefined ? unit : "");
}
function deltaHtml(x, d = 0, unit = "", betterHigher = true) {
  if (!isNum(x)) return `<span class="d flat-d">—</span>`;
  const good = betterHigher === null ? null : (x > 0) === betterHigher;
  const cls = x === 0 ? "flat-d" : good === null ? "flat-d" : good ? "up" : "down";
  return `<span class="d delta ${x > 0 ? "pos" : x < 0 ? "neg" : ""} ${cls}">${fmt.n(Math.abs(x), d)}${unit}</span>`;
}
function stat(k, v, unit, opts = {}) {
  const vv = v === null || v === undefined || v === "—" ? "—" : v;
  return `<div class="stat ${opts.cls || ""}"><span class="k">${esc(k)}</span><span class="v">${vv}${vv !== "—" && unit ? `<small>${esc(unit)}</small>` : ""}</span>${opts.d || ""}</div>`;
}
function badge(text, cls = "") { return `<span class="badge ${cls}">${esc(text)}</span>`; }
function estBadge(v) { return v && v.kind === "estimated" ? badge("Estimate", "est") : ""; }
function chips(name, options, current, cls = "") {
  return `<div class="chips" role="group" aria-label="${esc(name)}">${options.map(o => {
    const [id, label] = Array.isArray(o) ? o : [o, o];
    return `<button class="chip ${cls}" data-chip="${esc(name)}" data-val="${esc(id)}" aria-pressed="${id === current}">${esc(label)}</button>`;
  }).join("")}</div>`;
}
function seg(name, options, current) {
  return `<div class="seg" role="group" aria-label="${esc(name)}">${options.map(([id, label]) => `<button data-chip="${esc(name)}" data-val="${esc(id)}" aria-pressed="${id === current}">${esc(label)}</button>`).join("")}</div>`;
}
document.addEventListener("click", e => {
  const c = e.target.closest("[data-chip]");
  if (!c) return;
  uiSet("chip:" + c.dataset.chip, c.dataset.val);
  if (c.dataset.chip === "theme" && typeof applyTheme === "function") applyTheme();
  if (c.closest("#sheet")) { const fn = AG._sheetRefresh; if (fn) fn(); return; }
  rerender();
});
function chipVal(name, d) { return uiGet("chip:" + name, d); }
function tabs(name, options, current) {
  return `<div class="tabs" role="group" aria-label="${esc(name)}">${options.map(([id, label]) => `<button data-chip="${esc(name)}" data-val="${esc(id)}" aria-pressed="${id === current}">${esc(label)}</button>`).join("")}</div>`;
}
/* Card header: one title, one optional control on the right. Explanations live behind the info button. */
function cardHead(title, right = "", about = "") {
  return `<div class="card-h"><h3>${title}</h3>${right || about ? `<div class="r">${right}${about ? info(title.replace(/<[^>]+>/g, "").trim(), about) : ""}</div>` : ""}</div>`;
}
const INFO = {};
let infoSeq = 0;
function info(title, text) {
  const id = "i" + (++infoSeq);
  INFO[id] = { title, text };
  return `<button type="button" class="info-btn" data-info="${id}" aria-label="About ${esc(title)}">${icon("info")}</button>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-info]");
  if (!b || !INFO[b.dataset.info]) return;
  e.preventDefault(); e.stopPropagation();
  const { title, text } = INFO[b.dataset.info];
  openSheet(title, `<p class="small" style="margin:0;line-height:1.55">${text}</p>`);
});
function sectionTitle(t, link) { return `<div class="section-title"><h2>${esc(t)}</h2>${link || ""}</div>`; }
function bar(pct, color, marker) {
  const p = Math.max(0, Math.min(100, pct || 0));
  return `<div class="bar" role="img" aria-label="${fmt.n(p)} percent"><i style="width:${p}%;background:${color || "var(--accent)"}"></i>${isNum(marker) ? `<em style="left:calc(${Math.max(0, Math.min(100, marker))}% - 1px)"></em>` : ""}</div>`;
}

/* ---------- score ring (Bevel) ---------- */
function ringColor(kind) {
  return { strain: ["var(--strain)", "var(--strain-2)"], recovery: ["var(--recovery)", "var(--recovery-2)"], sleep: ["var(--sleep)", "var(--sleep-2)"], energy: ["var(--recovery)", "var(--recovery-2)"] }[kind] || ["var(--accent)", "var(--accent-2)"];
}
let ringSeq = 0;
function ring(kind, v, opts = {}) {
  const value = v && isNum(v.v) ? v.v : null;
  const r = 42, C = 2 * Math.PI * r;
  const pct = value === null ? 0 : Math.max(0, Math.min(100, value)) / 100;
  const [c1, c2] = ringColor(kind);
  const id = "rg" + (++ringSeq);
  const stale = v && (v.status === "stale");
  return `<div class="ring ${opts.lg ? "lg" : ""} ${stale ? "is-stale" : ""}" role="img" aria-label="${esc(opts.label || kind)} ${value === null ? "unknown" : fmt.n(value) + " percent"}${stale ? ", stale" : ""}">
    <svg viewBox="0 0 100 100"><defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${c1}"/><stop offset="1" stop-color="${c2}"/></linearGradient></defs>
      <circle cx="50" cy="50" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="8"/>
      ${value === null ? "" : `<circle class="ring-arc" cx="50" cy="50" r="${r}" fill="none" stroke="url(#${id})" stroke-width="8" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"/>`}
    </svg>
    <div class="val"><b>${value === null ? "—" : fmt.n(value)}${value === null ? "" : "<small>%</small>"}</b><span>${esc(opts.sub || "")}</span></div></div>`;
}

/* ---------- freshness chip ---------- */
function freshChip() {
  const ds = D.meta.data_status;
  const st = ds.overall;
  const txt = ds.last_sync ? `Updated ${fmt.time(ds.last_sync)}${st === "partial" ? " · partial" : st === "stale" ? " · stale" : ""}` : "No sync yet";
  return `<button class="fresh-ic ${st}" data-open="data-status" aria-label="Data freshness: ${esc(txt)}" title="${esc(txt)}">${icon(st === "ok" ? "cloud-check" : "refresh")}</button>`;
}
document.addEventListener("click", e => {
  const o = e.target.closest("[data-open]");
  if (!o) return;
  const fn = AG.sheets && AG.sheets[o.dataset.open];
  if (fn) { e.preventDefault(); fn(o.dataset.arg); }
});
AG.sheets = {};
AG.sheets["data-status"] = function () {
  const ds = D.meta.data_status;
  const rows = Object.entries(ds.domains).map(([k, v]) => `<div class="li"><div class="grow"><div class="t">${esc(fmt.sport(k))}</div>
    <div class="s">${v.as_of ? "Latest sample " + fmt.dt(v.as_of) : "No samples"}${v.note ? " · " + esc(v.note) : ""}</div></div>
    ${badge(statusLabel(v.status), v.status === "ok" ? "ok" : v.status === "partial" ? "warn" : v.status === "missing" ? "" : "bad")}</div>`).join("");
  openSheet("Data freshness", `<p class="small muted">Build for ${fmt.dateLong(D.meta.build_date)} · last sync ${ds.last_sync ? fmt.dt(ds.last_sync) : "never"}.
    ${ds.sleep_missing ? "<b>Last night's sleep has not synced yet.</b>" : ""}</p><div class="list">${rows}</div>
    <p class="cap" style="margin-top:12px">Source of truth: Apple HealthKit, imported each morning by ${esc(AGENT)}. Stale values stay visible with their timestamp; missing values are never shown as zero.</p>`);
};

/* ---------- factor & insight rows ---------- */
function factorRow(f) {
  const sym = icon(f.direction === "helping" ? "up" : f.direction === "hurting" ? "down" : "minus");
  let detail = "";
  if (f.baseline !== undefined && f.baseline !== null) detail = `usual ${fmt.n(f.baseline, 1)} ${f.unit || ""}`;
  else if (f.need) detail = `need ${fmt.hm(f.need)}`;
  let r;
  if (f.id === "sleep" || f.id === "sleep_debt") r = fmt.hm(f.value);
  else if (typeof f.value === "number") r = fmt.n(f.value, Math.abs(f.value) < 10 && f.value % 1 ? 1 : 0) + (f.unit && f.unit !== "%" ? " " + f.unit : f.unit || "");
  else r = esc(fmt.sport(String(f.value)));
  const dirTxt = f.direction === "helping" ? "Helping" : f.direction === "hurting" ? "Hurting" : "Neutral";
  return `<div class="factor ${f.direction}"><span class="ic" aria-hidden="true">${sym}</span><div class="grow"><div class="t">${esc(f.label)}</div>
    <div class="s">${dirTxt}${detail ? " · " + esc(detail) : ""}${f.stale ? " · stale" : ""}</div></div><span class="r">${r}</span></div>`;
}
function insightCard(text, sub, cls = "") {
  return `<div class="insight ${cls}"><span class="spark" aria-hidden="true">${icon(cls.includes("action") ? "alert" : "sparkles")}</span><div><b>${esc(text)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</div></div>`;
}

/* ---------- goals ---------- */
function goalStatusBadge(s) {
  const m = { on_track: ["On track", "ok"], ahead: ["Ahead", "ok"], done: ["Done", "ok"], behind: ["Behind", "warn"], in_progress: ["", ""],
    insufficient: ["Need more data", ""], no_data: ["No data", ""], not_logged: ["Not logged", ""], no_effort: ["No effort yet", ""], active: ["", ""], start: ["", ""] };
  const [t, c] = m[s] || [s || "", ""];
  return t ? badge(t, c) : "";
}
function goalValue(g, v) {
  if (!isNum(v)) return "—";
  if (g.type === "distance") return fmt.dist(v);
  if (g.type === "time" || g.type === "record") return fmt.dur(v);
  if (g.type === "elevation") return fmt.elev(v);
  if (g.type === "body_weight" || g.type === "strength") return fmt.kg(v);
  if (g.unit === "g") return fmt.n(v) + " g";
  return fmt.n(v) + (g.unit ? " " + g.unit : "");
}
function goalRow(g, opts = {}) {
  let pct = g.progress_pct, marker = isNum(g.elapsed_frac) && g.partial && !["body_weight", "record", "strength", "nutrition", "streak"].includes(g.type) ? g.elapsed_frac * 100 : null;
  let right = `${goalValue(g, g.actual)}${isNum(g.target) ? ` <span class="faint">/ ${goalValue(g, g.target)}</span>` : ""}`;
  let sub = "";
  if (g.type === "nutrition") { pct = g.adherence_pct; right = isNum(g.actual) ? `${fmt.n(g.actual)} g avg` : "—"; sub = isNum(g.days_logged) && g.days_logged ? `${g.days_hit}/${g.days_logged} days at ${fmt.n(g.target)} g` : STR.noNutrition; }
  if (g.type === "streak") { pct = null; right = `${fmt.n(g.actual)} weeks`; sub = `Longest ${fmt.n(g.longest)} weeks`; }
  if (g.type === "body_weight" && g.trajectory) {
    const t = g.trajectory; sub = isNum(t.actual_kg_per_week) ? `${fmt.signed(t.actual_kg_per_week, 2)} ${fmt.wUnit()}/wk · need ${fmt.signed(t.required_kg_per_week, 2)}` : "Need more weigh-ins";
  }
  if (g.type === "record") { pct = isNum(g.actual) && isNum(g.target) ? Math.min(100, g.target / g.actual * 100) : 0; sub = g.best_effort ? `Best ${fmt.dur(g.actual)} on ${fmt.date(g.best_effort.date)}` : "No qualifying effort yet"; }
  if (!sub && g.end) sub = g.end === D.meta.build_date ? "Ends today" : g.end > D.meta.build_date ? `Ends ${fmt.date(g.end)}` : `Ended ${fmt.date(g.end)}`;
  return `<div class="goal-row"><div class="spread"><b>${esc(g.title)}</b><span class="row">${goalStatusBadge(g.status_label)}${opts.edit ? editBtn("goal-edit", g.id) : ""}</span></div>
    ${pct === null || pct === undefined ? "" : bar(pct, "var(--accent)", marker)}
    <div class="spread small"><span class="muted">${esc(sub)}</span><span class="num">${right}</span></div></div>`;
}

/* ---------- activity row ---------- */
function activityRow(a) {
  const main = a.family === "run" || a.family === "walk" ? `${fmt.dist(a.distance_m)} · ${fmt.pace(a.pace_s_per_km)}` :
    a.family === "ride" ? `${fmt.dist(a.distance_m)} · ${fmt.n(a.speed_kph, 1)} km/h` : fmt.mins(a.duration_s);
  return `<a class="li" href="#/activity/${encodeURIComponent(a.id)}"><span class="icon-dot" style="color:${sportColor(a.family)}">${sportIcon(a.family)}</span>
    <div class="grow"><div class="t">${esc(a.name)}</div><div class="s">${fmt.dow(a.date)} ${fmt.date(a.date)} · ${fmt.time(a.start)} · ${main}</div></div>
    <div class="r">${a.load && isNum(a.load.v) ? fmt.n(a.load.v) : "—"}<div class="cap">load</div></div></a>`;
}

/* ---------- maps (privacy already applied in Python) ---------- */
function project(lines, w, h, pad = 10) {
  const pts = lines.flat();
  if (!pts.length) return null;
  const lat0 = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const kx = Math.cos(lat0 * Math.PI / 180);
  const xs = pts.map(p => p[1] * kx), ys = pts.map(p => -p[0]);
  const minx = Math.min(...xs), maxx = Math.max(...xs), miny = Math.min(...ys), maxy = Math.max(...ys);
  const sc = Math.min((w - 2 * pad) / ((maxx - minx) || 1e-6), (h - 2 * pad) / ((maxy - miny) || 1e-6));
  const ox = (w - (maxx - minx) * sc) / 2, oy = (h - (maxy - miny) * sc) / 2;
  return p => [ox + (p[1] * kx - minx) * sc, oy + (-p[0] - miny) * sc];
}
function mapSvg(lines, opts = {}) {
  if (!lines || !lines.length) return empty(STR.noRoute, opts.sub || "No GPS track for this activity");
  const w = opts.w || 320, h = opts.h || 200;
  const pr = project(lines, w, h, opts.pad || 14);
  const grid = [];
  for (let i = 1; i < 8; i++) grid.push(`<line class="gridl" x1="${i * w / 8}" y1="0" x2="${i * w / 8}" y2="${h}"/>`);
  for (let i = 1; i < 5; i++) grid.push(`<line class="gridl" x1="0" y1="${i * h / 5}" x2="${w}" y2="${i * h / 5}"/>`);
  const paths = lines.map(l => `<polyline class="trace" points="${l.map(p => pr(p).map(n => n.toFixed(1)).join(",")).join(" ")}"/>`).join("");
  const first = pr(lines[0][0]), last = pr(lines[lines.length - 1][lines[lines.length - 1].length - 1]);
  return `<div class="map ${opts.cls || ""}" role="img" aria-label="${esc(opts.label || "Route map")}"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet">${opts.noGrid ? "" : grid.join("")}${paths}
    ${opts.noEnds ? "" : `<circle cx="${first[0]}" cy="${first[1]}" r="4.5" fill="var(--ok)" stroke="var(--surface)" stroke-width="2"/><circle cx="${last[0]}" cy="${last[1]}" r="4.5" fill="var(--text)" stroke="var(--surface)" stroke-width="2"/>`}</svg>
    <span class="attrib">Privacy zones applied${D.routes && D.routes.tiles ? "" : " · no map tiles"}</span></div>`;
}
function routeThumb(lines) {
  if (!lines || !lines.length) return `<div class="route-thumb"></div>`;
  const pr = project(lines, 72, 72, 8);
  return `<div class="route-thumb" aria-hidden="true"><svg viewBox="0 0 72 72">${lines.map(l => `<polyline fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round" points="${l.map(p => pr(p).map(n => n.toFixed(1)).join(",")).join(" ")}"/>`).join("")}</svg></div>`;
}
function surfaceBar(s) {
  if (!s) return "";
  return `<div class="surface-bar" role="img" aria-label="Surface: ${fmt.n(s.paved_pct)}% paved, ${fmt.n(s.unpaved_pct)}% unpaved"><i style="width:${s.paved_pct || 0}%;background:var(--text-2)"></i><i style="width:${s.unpaved_pct || 0}%;background:var(--accent)"></i><i style="width:${s.unknown_pct || 0}%;background:var(--surface-3)"></i></div>
    <div class="legend" style="margin-top:6px"><span><i style="background:var(--text-2)"></i>${fmt.n(s.paved_pct)}% paved</span><span><i style="background:var(--accent)"></i>${fmt.n(s.unpaved_pct)}% unpaved</span><span><i style="background:var(--surface-3)"></i>${fmt.n(s.unknown_pct)}% unknown</span></div>`;
}

/* ---------- muscle map (front/back) ---------- */
/* Anatomy polygons from react-body-highlighter (MIT, github.com/giavinh79/react-body-highlighter), 100x200 viewBox. */
const BODY = {"front":[{"m":"chest","p":["51.8 41.6 51 55.1 58 58 67.8 55.5 70.6 47.3 62 41.6","29.8 46.5 31.4 55.5 40.8 58 48.2 55.1 47.8 42 37.6 42"]},{"m":"obliques","p":["68.6 63.3 67.3 57.1 58.8 59.6 60 64.1 60.4 83.3 65.7 78.8 66.5 69.8","33.9 78.4 33.1 71.8 31 63.3 32.2 57.1 40.8 59.2 39.2 63.3 39.2 83.7"]},{"m":"abs","p":["56.3 59.2 58 64.1 58.4 78 58.4 92.7 56.3 98.4 55.1 104.1 51.4 107.8 51 84.5 50.6 67.3 51 57.1","43.7 58.8 48.6 57.1 49 67.3 48.6 84.5 48.2 107.3 44.5 103.7 40.8 91.4 40.8 78.4 41.2 64.5"]},{"m":"biceps","p":["16.7 68.2 18 71.4 22.9 66.1 29 53.9 27.8 49.4 20.4 55.9","71.4 49.4 70.2 54.7 76.3 66.1 81.6 71.8 82.9 69 78.8 55.5"]},{"m":"triceps","p":["69.4 55.5 69.4 61.6 75.9 72.7 77.6 70.2 75.5 67.3","22.4 69.4 29.8 55.5 29.8 60.8 22.9 73.1"]},{"m":"neck","p":["55.5 23.7 50.6 33.5 50.6 39.2 61.6 40 70.6 44.9 69.4 36.7 63.3 35.1 58.4 30.6","29 44.9 30.2 37.1 36.3 35.1 41.2 30.2 44.5 24.5 49 33.9 48.6 39.2 38 39.6"]},{"m":"front_deltoids","p":["78.4 53.1 79.6 47.8 79.2 41.2 75.9 38 71 36.3 72.2 42.9 71.4 47.3","28.2 47.3 21.2 53.1 20 47.8 20.4 40.8 24.5 37.1 28.6 37.1 26.9 43.3"]},{"m":"head","p":["42.4 2.9 40 11.8 42 19.6 46.1 23.3 49.8 25.3 54.7 22.4 57.6 19.2 59.2 10.2 57.1 2.4 49.8 0"]},{"m":"abductors","p":["52.7 110.2 54.3 124.9 60 110.2 62 100 64.9 94.3 60 92.7 56.7 104.5","47.8 110.6 44.9 125.3 42 115.9 40.4 113.1 39.6 107.3 38 102.4 34.7 93.9 39.6 92.2 41.6 99.2 43.7 105.3"]},{"m":"quadriceps","p":["34.7 98.8 37.1 108.2 37.1 127.8 34.3 137.1 31 132.7 29.4 120 28.2 111.4 29.4 100.8 32.2 94.7","63.3 105.7 64.5 100 66.9 94.7 70.2 101.2 71 111.8 68.2 133.1 65.3 137.6 62.4 128.6 62 111.4","38.8 129.4 38.4 112.2 41.2 118.4 44.5 129.4 42.9 135.1 40 146.1 36.3 146.5 35.5 140","59.6 145.7 55.5 129 60.8 113.9 61.2 130.2 64.1 139.6 62.9 146.5","32.7 138.4 26.5 145.7 25.7 136.7 25.7 127.3 26.9 114.3 29.4 133.5","71.8 113.1 73.9 124.1 73.9 140.4 72.7 145.7 66.5 138.4 70.2 133.5"]},{"m":"knees","p":["33.9 140 34.7 143.3 35.5 147.3 36.3 151 35.1 156.7 29.8 156.7 27.3 152.7 27.3 147.3 30.2 144.1","65.7 140 72.2 147.8 72.2 152.2 69.8 157.1 64.9 156.7 62.9 151"]},{"m":"calves","p":["71.4 160.4 73.5 153.5 76.7 161.2 79.6 167.8 78.4 187.8 79.6 195.5 74.7 195.5","24.9 194.7 27.8 164.9 28.2 160.4 26.1 154.3 24.9 157.6 22.4 161.6 20.8 167.8 22 188.2 20.8 195.5","72.7 195.1 69.8 159.2 65.3 158.4 64.1 162.4 64.1 165.3 65.7 177.1","35.5 158.4 35.9 162.4 35.9 166.9 35.1 172.2 35.1 176.7 32.2 182 30.6 187.3 26.9 194.7 27.3 187.8 28.2 180.4 28.6 175.5 29 169.8 29.8 164.1 30.2 158.8"]},{"m":"forearm","p":["6.1 88.6 10.2 75.1 14.7 70.2 16.3 74.3 19.2 73.5 4.5 97.6 0 100","84.5 69.8 83.3 73.5 80 73.1 95.1 98.4 100 100.4 93.5 89.4 89.8 76.3","77.6 72.2 77.6 77.6 80.4 84.1 85.3 89.8 92.2 101.2 94.7 99.6","6.9 101.2 13.5 90.6 18.8 84.1 21.6 77.1 21.2 71.8 4.9 98.8"]}],"back":[{"m":"head","p":["50.6 0 46 0.9 40.9 5.5 40.4 12.8 45.1 20 55.7 20 59.1 13.6 59.6 4.7 55.7 1.3"]},{"m":"trapezius","p":["44.7 21.7 47.7 21.7 47.2 38.3 47.7 64.7 38.3 53.2 35.3 40.9 31.1 36.6 39.1 33.2 43.8 27.2","52.3 21.7 55.7 21.7 56.6 27.2 60.9 32.8 68.9 36.6 64.7 40.4 61.7 53.2 52.3 64.7 53.2 38.3"]},{"m":"back_deltoids","p":["29.4 37 23 39.1 17.4 44.3 18.3 53.6 24.3 49.4 27.2 46.4","71.1 37 78.3 39.6 82.6 44.7 81.7 53.6 74.9 48.9 72.3 45.1"]},{"m":"upper_back","p":["31.1 38.7 28.1 48.9 28.5 55.3 34 75.3 47.2 71.1 47.2 66.4 36.6 54 33.6 41.3","68.9 38.7 71.9 49.4 71.5 56.2 66 75.3 52.8 71.1 52.8 66.4 63.4 54.5 66.4 41.7"]},{"m":"triceps","p":["26.8 49.8 17.9 55.7 14.5 72.3 16.6 81.7 21.7 63.8 26.8 55.7","73.6 50.2 82.1 55.7 86 73.2 83.4 82.1 77.9 63 73.2 55.7","26.8 58.3 26.8 68.5 23 75.3 19.1 77.4 22.6 65.5","72.8 58.3 77 64.7 80.4 77.4 76.6 75.3 72.8 68.9"]},{"m":"lower_back","p":["47.7 72.8 34.5 77 35.3 83.4 49.4 102.1 46.8 83","52.3 72.8 65.5 77 64.7 83.4 50.6 102.1 53.2 83.8"]},{"m":"forearm","p":["86.4 75.7 91.1 83.4 93.2 94 100 106.4 96.2 104.3 88.1 89.4 84.3 83.8","13.6 75.7 8.9 83.8 6.8 93.6 0 106.4 3.8 104.3 12.3 88.5 15.7 83","81.3 79.6 77.4 77.9 79.1 84.7 91.1 103.8 93.2 108.9 94.5 104.7","18.7 79.6 22.1 77.9 20.9 84.3 9.4 103 6.8 108.5 5.1 104.7"]},{"m":"gluteal","p":["44.7 99.6 30.2 108.5 29.8 118.7 31.5 126 47.2 121.3 49.4 114.9","55.3 99.1 51.1 114.5 52.3 120.9 68.1 126 69.8 119.1 69.4 108.5"]},{"m":"abductor","p":["48.1 123 44.7 123 41.3 125.5 45.1 144.3 48.5 135.7 48.9 129.4","51.9 122.6 55.7 123.4 59.1 126 54.9 144.3 51.9 136.2 51.1 129.4"]},{"m":"hamstring","p":["28.9 122.1 31.1 129.4 36.6 126 35.3 135.3 34.5 150.2 29.4 158.3 28.9 146.8 27.7 141.3 27.2 131.5","71.5 121.7 69.4 128.9 63.8 126 65.5 136.6 66.4 150.2 71.1 158.3 71.5 147.7 72.8 142.1 73.6 131.9","38.7 125.5 44.3 146 40.4 166.8 36.2 152.8 37 135.3","61.7 125.5 63.4 136.2 64.3 153.2 60 166.8 56.2 146.4"]},{"m":"knees","p":["34.5 153.2 31.1 159.1 33.6 166.4 37.4 162.6","66.4 153.6 63 163 66.8 166.4 69.4 159.1"]},{"m":"calves","p":["29.4 160.4 28.5 167.2 24.7 179.6 23.8 192.8 25.5 197 28.5 193.2 29.8 180 31.9 171.1 31.9 166.8","37.4 165.1 35.3 167.7 33.2 171.9 31.1 180.4 30.2 191.9 34 200 38.7 190.6 39.1 168.9","63 165.1 61.3 168.5 61.7 190.6 66.4 199.6 70.6 191.9 68.9 179.6 66.8 170.2","70.6 160.4 72.3 168.5 75.7 179.1 76.6 192.8 74.5 196.6 72.3 193.6 70.6 179.6 68.1 168.1"]},{"m":"left_soleus","p":["28.5 195.7 30.2 195.7 33.6 201.7 30.6 220 28.5 213.6 26.8 198.3"]},{"m":"right_soleus","p":["69.8 195.7 71.9 195.7 73.6 198.3 71.9 213.2 70.2 219.6 67.2 202.1"]}]};
const BODY_REGIONS = {"chest":["chest"],"obliques":["obliques"],"abs":["abs"],"biceps":["biceps"],"triceps":["triceps"],"front_deltoids":["front_delts","side_delts"],"abductors":["adductors"],"abductor":["adductors"],"quadriceps":["quads"],"calves":["calves"],"left_soleus":["calves"],"right_soleus":["calves"],"forearm":["forearms"],"trapezius":["traps"],"back_deltoids":["rear_delts","side_delts"],"upper_back":["lats"],"lower_back":["lower_back"],"gluteal":["glutes"],"hamstring":["hamstrings"]};
const MM_RANK = ["no_data", "detraining", "calibrating", "approximate", "recovered", "maintaining", "productive", "trained", "fatigued", "overtraining", "depleted"];
function muscleMap(groups, mode = "freshness", trained) {
  const state = m => {
    if (trained) return trained.includes(m) ? "trained" : "no_data";
    const g = groups[m]; if (!g) return "no_data";
    return (mode === "load" ? g.load_status : g.freshness) || "no_data";
  };
  const region = r => (BODY_REGIONS[r] || []).map(state).sort((a, b) => MM_RANK.indexOf(b) - MM_RANK.indexOf(a))[0];
  const side = (name, parts) => `<figure style="margin:0"><svg viewBox="-2 -2 104 204" role="img" aria-label="${name} muscle map">
    <defs><pattern id="hatch" width="3" height="3" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3" height="3" fill="var(--surface-3)"/><line x1="0" y1="0" x2="0" y2="3" stroke="var(--text-3)" stroke-width="1"/></pattern></defs>
    ${parts.map(({ m, p }) => { const st = BODY_REGIONS[m] ? region(m) : null; const label = (BODY_REGIONS[m] || []).map(x => fmt.sport(x)).join(", ");
      return p.map(pts => `<polygon class="mm ${st ? esc(st) : "mm-base"}" points="${pts}">${st ? `<title>${esc(label)}: ${esc(fmt.sport(st))}</title>` : ""}</polygon>`).join(""); }).join("")}</svg>
    <figcaption class="cap" style="text-align:center;margin-top:6px">${name}</figcaption></figure>`;
  return `<div class="muscle-map">${side("Front", BODY.front)}${side("Back", BODY.back)}</div>`;
}

/* ---------- workout steps (Bevel step list) ---------- */
function targetText(t) {
  if (!t) return "";
  if (t.metric === "hr") return `HR ${isNum(t.low) ? t.low : ""}${isNum(t.low) && isNum(t.high) ? "–" : isNum(t.high) ? "<" : ""}${isNum(t.high) ? t.high : ""} bpm`;
  if (t.metric === "pace") return `Pace ${fmt.pace(t.low, false)}–${fmt.pace(t.high)}`;
  if (t.metric === "power") return `Power ${t.low}–${t.high} W`;
  if (t.metric === "zone") return `Zone ${t.zone}`;
  if (t.metric === "rpe") return `RPE ${t.low}–${t.high}`;
  return "Open goal";
}
function stepList(steps) {
  if (!steps || !steps.length) return "";
  const one = s => `<div class="li"><div class="grow"><div class="t">${esc(s.label || fmt.sport(s.kind))}</div><div class="s">${s.duration_s ? fmt.mins(s.duration_s) : s.distance_m ? fmt.dist(s.distance_m) : ""}</div></div><span class="small muted">${esc(targetText(s.target))}</span></div>`;
  return `<div class="list">${steps.map(s => s.kind === "repeat" ? `<div class="li"><div class="grow"><div class="t">Repeat ×${s.repeat}</div></div></div><div style="padding-left:14px;border-left:2px solid var(--line-2)">${(s.steps || []).map(one).join("")}</div>` : one(s)).join("")}</div>`;
}

/* ---------- toasts & edits (server only) ---------- */
function toast(msg, action) {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
  t.innerHTML = `<span>${esc(msg)}</span>${action ? `<button type="button">${esc(action.label)}</button>` : ""}`;
  if (action) t.querySelector("button").onclick = () => { t.classList.remove("on"); action.run(); };
  t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), action ? 7000 : 2600);
}
/* One place for every write: call the API, remember an undo hint across the reload, rebuild view. */
async function save(method, path, body, msg = "Saved") {
  try {
    const r = await api(method, path, body);
    try { sessionStorage.setItem("agame:undo", msg); } catch (e) { /* private mode */ }
    closeSheet(true);
    toast(msg + " · rebuilding");
    setTimeout(() => location.reload(), 700);
    return r;
  } catch (err) { toast(err.message); throw err; }
}
const act = (name, body, msg) => save("POST", "actions/" + name, body, msg);
async function undoLast() {
  try { await api("POST", "undo", {}); try { sessionStorage.setItem("agame:undo", ""); } catch (e) { } toast("Undone · rebuilding"); setTimeout(() => location.reload(), 700); }
  catch (err) { toast(err.message); }
}
function undoToastOnBoot() {
  let m = null;
  try { m = sessionStorage.getItem("agame:undo"); sessionStorage.removeItem("agame:undo"); } catch (e) { return; }
  if (m && AG.online) toast(m, { label: "Undo", run: undoLast });
}
function confirmSheet(title, text, label, run) {
  openSheet(title, `<p class="small">${esc(text)}</p><div class="row" style="margin-top:12px"><button class="btn danger" id="cf-yes">${esc(label)}</button><button class="btn secondary" data-close>Cancel</button></div>`,
    { after: sh => { $("#cf-yes", sh).onclick = run; $$("[data-close]", sh).forEach(b => b.onclick = () => closeSheet()); } });
}

/* Local <input> values <-> ISO with offset (the browser's own zone; Python re-reads it in the profile zone). */
function isoToInput(iso, kind = "datetime-local") {
  if (!iso) return "";
  if (kind === "date") return iso.slice(0, 10);
  const d = new Date(iso); const p = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
function inputToIso(v) {
  if (!v) return null;
  const d = new Date(v); const off = -d.getTimezoneOffset(); const p = n => String(Math.floor(Math.abs(n))).padStart(2, "0");
  return `${v.length === 16 ? v + ":00" : v}${off >= 0 ? "+" : "-"}${p(off / 60)}:${p(off % 60)}`;
}
function nowInput() { return isoToInput(new Date().toISOString()); }

/* Generic form sheet. fields: [{name,label,type,value,options,step,min,max,required,hint,full,placeholder}] */
function fieldHtml(f) {
  const v = f.value === null || f.value === undefined ? "" : f.value;
  const req = f.required ? "required" : "";
  const attrs = `name="${esc(f.name)}" ${req} ${f.step ? `step="${f.step}"` : ""} ${isNum(f.min) ? `min="${f.min}"` : ""} ${isNum(f.max) ? `max="${f.max}"` : ""} ${f.placeholder ? `placeholder="${esc(f.placeholder)}"` : ""}`;
  let input;
  if (f.type === "select") input = `<select ${attrs}>${(f.options || []).map(o => { const [ov, ol] = Array.isArray(o) ? o : [o, o]; return `<option value="${esc(ov)}" ${String(ov) === String(v) ? "selected" : ""}>${esc(ol)}</option>`; }).join("")}</select>`;
  else if (f.type === "textarea") input = `<textarea ${attrs} rows="${f.rows || 3}">${esc(v)}</textarea>`;
  else if (f.type === "checkbox") return `<label class="check ${f.full ? "full" : ""}"><input type="checkbox" name="${esc(f.name)}" ${v ? "checked" : ""}> <span>${esc(f.label)}</span></label>`;
  else if (f.type === "html") return `<div class="${f.full ? "full" : ""}">${f.html}</div>`;
  else input = `<input type="${f.type || "text"}" ${f.type === "number" ? 'inputmode="decimal"' : ""} value="${esc(v)}" ${attrs}>`;
  return `<label class="${f.full ? "full" : ""}">${esc(f.label)}${input}${f.hint ? `<span class="cap">${esc(f.hint)}</span>` : ""}</label>`;
}
function readForm(form, fields) {
  const out = {};
  fields.forEach(f => {
    if (f.type === "html") return;
    const el = form.elements[f.name];
    if (!el) return;
    if (f.type === "checkbox") out[f.name] = el.checked;
    else if (f.type === "number") out[f.name] = el.value === "" ? null : +el.value;
    else out[f.name] = el.value === "" ? null : el.value;
  });
  return out;
}
function formSheet(title, fields, onSubmit, opts = {}) {
  const body = `${opts.intro ? `<p class="small muted">${opts.intro}</p>` : ""}<form class="form grid-form" id="fs-form" novalidate>${fields.map(fieldHtml).join("")}
    <div class="full row wrap" style="margin-top:6px"><button class="btn" type="submit" ${AG.online ? "" : "disabled"}>${esc(opts.submit || "Save")}</button>
    ${opts.danger ? `<button class="btn danger" type="button" id="fs-danger" ${AG.online ? "" : "disabled"}>${esc(opts.danger.label)}</button>` : ""}
    ${(opts.extra || []).map((x, i) => `<button class="btn secondary" type="button" data-fs-extra="${i}" ${AG.online ? "" : "disabled"}>${esc(x.label)}</button>`).join("")}</div>
    ${offlineNote()}</form>${opts.after || ""}`;
  return openSheet(title, body, { after: sh => {
    const form = $("#fs-form", sh);
    $("input,select,textarea", form) && $("input,select,textarea", form).setAttribute("data-autofocus", "");
    form.onsubmit = async e => {
      e.preventDefault();
      if (!form.reportValidity()) return;
      try { await onSubmit(readForm(form, fields), form); } catch (err) { /* toast already shown */ }
    };
    if (opts.danger) $("#fs-danger", sh).onclick = () => opts.danger.run(readForm(form, fields));
    $$("[data-fs-extra]", sh).forEach(b => b.onclick = () => opts.extra[+b.dataset.fsExtra].run(readForm(form, fields), form));
    if (opts.bind) opts.bind(sh, form);
  } });
}
function editBtn(sheet, arg, label = "Edit") {
  return AG.online ? `<button class="btn sm secondary" type="button" data-open="${esc(sheet)}" ${arg !== undefined ? `data-arg="${esc(arg)}"` : ""}>${esc(label)}</button>` : "";
}
