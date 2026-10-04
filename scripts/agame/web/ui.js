/* AGame components. Pure presentation of computed values. */
"use strict";

/* ---------- copy catalog (exact empty-state strings; tested) ---------- */
const STR = {
  noRoute: "Route data unavailable",
  noVO2: "No cardio-fitness samples yet",
  noNutrition: "Nutrition not connected",
  noLeaderboard: "No leaderboard data connected",
  noPower: "Power meter not connected",
  noExercise: "No exercise details — muscles not inferred",
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
  return `<button class="prov" data-prov="${id}" aria-label="Data details for ${esc(label || "value")}" title="Data details">i</button>`;
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
  return `<button class="fresh ${st}" data-open="data-status" aria-label="Data freshness: ${esc(txt)}"><i></i>${esc(txt)}</button>`;
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
  const sym = f.direction === "helping" ? "↑" : f.direction === "hurting" ? "↓" : "·";
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
  return `<div class="insight ${cls}"><span class="spark" aria-hidden="true">${cls.includes("action") ? "!" : "✦"}</span><div><b>${esc(text)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</div></div>`;
}

/* ---------- goals ---------- */
function goalStatusBadge(s) {
  const m = { on_track: ["On track", "ok"], ahead: ["Ahead", "ok"], done: ["Done", "ok"], behind: ["Behind", "warn"], in_progress: ["In progress", "info"],
    insufficient: ["Need more data", ""], no_data: ["No data", ""], not_logged: ["Not logged", ""], no_effort: ["No effort yet", ""], active: ["Active", "ok"], start: ["Start", ""] };
  const [t, c] = m[s] || [s || "—", ""];
  return badge(t, c);
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
const MUSCLE_SHAPES = {
  front: [
    ["front_delts", "M27 44c-5 1-8 5-8 10l7 1 4-9z M73 44c5 1 8 5 8 10l-7 1-4-9z"],
    ["chest", "M31 46c5-2 12-2 18 0v12c-6 3-13 3-18 0z M51 46c6-2 13-2 18 0v12c-5 3-12 3-18 0z"],
    ["biceps", "M19 56l7 1-1 16-7-2z M81 56l-7 1 1 16 7-2z"],
    ["forearms", "M18 73l7 2-2 20-7-2z M82 73l-7 2 2 20 7-2z"],
    ["abs", "M42 61h16v34H42z"],
    ["obliques", "M33 62l8 1v30l-7-4z M67 62l-8 1v30l7-4z"],
    ["adductors", "M44 100l6 1-1 28-5-3z M56 100l-6 1 1 28 5-3z"],
    ["quads", "M33 99l10 2 1 30-9 7-4-18z M67 99l-10 2-1 30 9 7 4-18z"],
    ["calves", "M35 145l7 1-1 30-5 1z M65 145l-7 1 1 30 5 1z"],
    ["side_delts", "M22 47l-4 6 1 3 5-1z M78 47l4 6-1 3-5-1z"],
  ],
  back: [
    ["traps", "M38 38l12-3 12 3-5 12H43z"],
    ["rear_delts", "M27 44c-5 1-8 5-8 10l7 1 4-9z M73 44c5 1 8 5 8 10l-7 1-4-9z"],
    ["lats", "M32 52l11-2 2 26-9-4z M68 52l-11-2-2 26 9-4z"],
    ["triceps", "M19 56l7 1-1 16-7-2z M81 56l-7 1 1 16 7-2z"],
    ["lower_back", "M44 74h12v18H44z"],
    ["glutes", "M34 94c5-3 11-3 15 0v12c-5 3-11 3-15 0z M51 94c4-3 10-3 15 0v12c-4 3-10 3-15 0z"],
    ["hamstrings", "M34 109l10 1v28l-8 2z M66 109l-10 1v28l8 2z"],
    ["calves", "M35 145l8 1-1 26-6 2z M65 145l-8 1 1 26 6 2z"],
    ["forearms", "M18 73l7 2-2 20-7-2z M82 73l-7 2 2 20 7-2z"],
  ],
};
const BODY_OUTLINE = "M50 8c6 0 10 5 10 11s-4 11-10 11-10-5-10-11 4-11 10-11zM35 34h30c9 1 15 6 16 14l3 26 1 22-6 2-5-24-1 12 2 44-3 44h-8l-4-46-4 0-4 46h-8l-3-44 2-44-1-12-5 24-6-2 1-22 3-26c1-8 7-13 16-14z";
function muscleMap(groups, mode = "freshness", trained) {
  const cls = m => {
    if (trained) return trained.includes(m) ? "trained" : "no_data";
    const g = groups[m]; if (!g) return "no_data";
    return mode === "load" ? g.load_status : g.freshness;
  };
  const side = (name, shapes) => `<figure style="margin:0"><svg viewBox="0 0 100 190" role="img" aria-label="${name} muscle map">
    <defs><pattern id="hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="4" height="4" fill="var(--surface-3)"/><line x1="0" y1="0" x2="0" y2="4" stroke="var(--text-3)" stroke-width="1.5"/></pattern></defs>
    <path class="mm-base" d="${BODY_OUTLINE}"/>${shapes.map(([m, d]) => `<path class="mm ${cls(m)}" d="${d}"><title>${esc(fmt.sport(m))}: ${esc(fmt.sport(cls(m)))}</title></path>`).join("")}</svg>
    <figcaption class="cap" style="text-align:center">${name}</figcaption></figure>`;
  return `<div class="muscle-map">${side("Front", MUSCLE_SHAPES.front)}${side("Back", MUSCLE_SHAPES.back)}</div>`;
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
