/* Activities list, activity detail (post-workout report), social */
"use strict";

AG.screens.activities = {
  title: "Activities",
  render() {
    const S = D.social || {};
    const hasSocial = ["posts", "clubs", "challenges"].some(k => (S[k] || []).length);
    const tab = hasSocial ? chipVal("act-tab", "list") : "list";
    return `${hasSocial ? tabs("act-tab", [["list", "Yours"], ["social", "Social"]], tab) : ""}${tab === "social" ? socialView() : activityList()}`;
  },
};

function activityList() {
  const fam = chipVal("act-fam", "all");
  const flt = chipVal("act-flt", "any");
  const q = (uiGet("act-q", "") || "").toLowerCase();
  let rows = D.activities.list;
  if (fam !== "all") rows = rows.filter(a => a.family === fam);
  if (flt === "gps") rows = rows.filter(a => a.has_gps);
  if (flt === "pr") rows = rows.filter(a => (D.activities.details[a.id] || {}).efforts && D.activities.details[a.id].efforts.some(e => e.pr));
  if (flt === "planned") rows = rows.filter(a => a.planned);
  if (flt === "unplanned") rows = rows.filter(a => !a.planned);
  if (q) rows = rows.filter(a => (a.name + " " + a.sport + " " + a.date).toLowerCase().includes(q));
  if (!D.activities.list.length) return empty(STR.noData, `Workouts appear after ${AGENT} imports them from HealthKit`);
  const groups = {};
  const limit = AG.actLimit || 60;
  let shown = rows.slice(0, limit);
  if (shown.length < rows.length) { const m = shown[shown.length - 1].date.slice(0, 7); shown = rows.filter((a, i) => i < limit || a.date.slice(0, 7) === m); }
  shown.forEach(a => { const k = a.date.slice(0, 7); (groups[k] = groups[k] || []).push(a); });
  const more = shown.length < rows.length ? `<button type="button" class="btn secondary block" data-act-more>Show older</button>` : "";
  const months = Object.entries(groups);
  return `<div class="stack"><div class="toolbar"><label class="search">${icon("search")}<span class="sr">Search activities</span><input id="act-q" type="search" placeholder="Search activities" value="${esc(uiGet("act-q", ""))}" data-search></label>
    ${chips("act-fam", [["all", "All"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"], ["swim", "Swim"], ["other", "Other"]], fam)}
    <select data-select="act-flt" aria-label="Filter">${[["any", "Any activity"], ["gps", "With map"], ["pr", "With PRs"], ["planned", "Planned"], ["unplanned", "Unplanned"]].map(([v, l]) => `<option value="${v}" ${v === flt ? "selected" : ""}>${l}</option>`).join("")}</select></div>
    ${months.length ? months.map(([m, list], i) => `${sectionTitle(fmt.date(m + "-15", { month: "long", year: "numeric" }), `<span class="small muted">${list.length} ${list.length === 1 ? "activity" : "activities"}</span>`)}<div class="card"><div class="list">${list.map(feedCard).join("")}</div>${i === months.length - 1 ? more : ""}</div>`).join("") : empty("No activities match")}</div>`;
}
document.addEventListener("click", e => {
  if (e.target.closest("[data-act-more]")) { AG.actLimit = (AG.actLimit || 60) + 60; rerender(); }
});
document.addEventListener("change", e => {
  const sel = e.target.closest("[data-select]");
  if (sel) { uiSet("chip:" + sel.dataset.select, sel.value); rerender(); }
});
document.addEventListener("input", e => {
  if (e.target.matches("[data-search]")) { uiSet("act-q", e.target.value); clearTimeout(AG._sq); AG._sq = setTimeout(() => { rerender(); const el = $("#act-q"); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, 250); }
});

function feedCard(a) {
  const det = D.activities.details[a.id];
  const prs = det && det.efforts ? det.efforts.filter(e => e.pr).length : 0;
  const main = a.family === "run" || a.family === "walk" ? [fmt.dist(a.distance_m), fmt.pace(a.pace_s_per_km), fmt.dur(a.moving_s || a.duration_s)]
    : a.family === "ride" ? [fmt.dist(a.distance_m), fmt.n(a.speed_kph, 1) + " km/h", fmt.dur(a.moving_s || a.duration_s)]
    : [fmt.dur(a.duration_s), isNum(a.avg_hr) ? fmt.n(a.avg_hr) + " bpm" : ""];
  return `<a class="li act-row" href="#/activity/${encodeURIComponent(a.id)}"><span class="icon-dot round" style="color:${sportColor(a.family)}">${sportIcon(a.family)}</span>
    <div class="grow"><div class="tl-time">${fmt.dow(a.date)} ${fmt.date(a.date)} · ${fmt.time(a.start)}${a.private ? " · Private" : ""}</div><div class="t">${esc(a.name)}${prs ? ` ${badge(prs === 1 ? "PR" : prs + " PRs", "accent")}` : ""}</div>
    <div class="s">${main.filter(Boolean).join(" · ")}${a.load && isNum(a.load.v) ? ` · load ${fmt.n(a.load.v)}` : ""}</div></div><span class="go" aria-hidden="true">${icon("arrow")}</span></a>`;
}

function socialView() {
  const S = D.social;
  return `<div class="cols"><div class="stack">
    <div class="card">${cardHead("Feed")}${S.posts.length ? `<div class="list">${S.posts.map(p => `<div class="li"><div class="grow"><div class="t">${esc(p.title || "Post")}</div><div class="s">${esc(p.source)}</div></div></div>`).join("")}</div>` : empty(STR.noFeed, "Comparing with other runners comes later, on real data only. No names or ranks are ever generated.")}</div>
    <div class="card">${cardHead("Clubs")}${S.clubs.length ? `<div class="list">${S.clubs.map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.name || c.id)}</div><div class="s">${esc(c.source)}</div></div></div>`).join("")}</div>` : empty(STR.noClubs)}</div>
    <div class="card">${cardHead("Leaderboards")}${empty(STR.noLeaderboard, "Segment leaderboards render only from supplied participant data")}</div></div>
    <div class="stack"><div class="card">${cardHead("My challenges")}${S.own_challenges.length ? S.own_challenges.map(goalRow).join("") : empty(STR.noChallenges, "Distance, time or session goals for a period show here as personal challenges")}</div>
    <div class="card">${cardHead("Group challenges")}${S.challenges.length ? `<div class="list">${S.challenges.map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.name || c.id)}</div><div class="s">${esc(c.source)}</div></div></div>`).join("")}</div>` : empty(STR.noChallenges)}</div>
    <div class="card">${cardHead("Events & races")}${S.races.length ? `<div class="list">${S.races.map(r => `<div class="li"><span class="prio ${esc(r.priority || "")}">${esc(r.priority || "–")}</span><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })}${r.distance_m ? " · " + fmt.dist(r.distance_m) : ""}</div></div></div>`).join("")}</div>` : empty("No events added")}</div>
    <div class="card">${cardHead("Leaderboard integrity", `<span class="small muted">${D.routes.integrity.own.length} of ${D.routes.integrity.checked} flagged</span>`)}${D.routes.integrity.own.map(f => `<div class="li"><div class="grow"><div class="t">${fmt.date(f.date)}</div><div class="s">${esc(f.reason)}</div></div>${badge("Flagged", "warn")}</div>`).join("")}</div></div></div>`;
}

/* ---------------- activity detail ---------------- */
const findAct = r => D.activities.list.find(x => x.id === r.arg);
AG.screens.activity = {
  title: r => { const a = findAct(r); return a ? a.name : "Activity"; },
  parent: "#/activities", nav: "activities", ownTitle: true,
  headRight(r) { const a = findAct(r); return a && D.activities.details[a.id] ? editBtn("act-edit", a.id, "Edit") : ""; },
  render(r) {
    const a = findAct(r);
    if (!a) return empty("Activity not found", "It may be older than this snapshot");
    const det = D.activities.details[a.id];
    if (!det) return `<h2 class="page-title">${esc(a.name)}</h2><div class="card">${feedCard(a)}</div>${empty("Details not embedded", `Only the latest ${D.meta.detail_max_activities} activities carry full streams in this snapshot`)}`;
    const tab = chipVal("act-detail-tab", "summary") === "chat" && !AG.llm ? "summary" : chipVal("act-detail-tab", "summary");
    const tags = [a.race ? badge("Race", "accent") : "", a.private ? badge("Private", "est") : ""].join("");
    const when = `${fmt.date(a.date, { weekday: "short", day: "numeric", month: "short", year: "numeric" })} · ${fmt.time(a.start)}${det.end ? "–" + fmt.time(det.end) : ""}`;
    const badgeIc = cls => `<span class="act-badge ${cls}" style="--c:${sportColor(a.family)}">${sportIcon(a.family)}</span>`;
    const hero = det.map ? `<div class="act-hero hide-d">${mapSvg(det.map, { label: "Activity route", w: 390, h: 300, cls: "hero-map", pad: { t: 72, r: 32, b: 44, l: 32 } })}${badgeIc("")}</div>` : "";
    const head = `<div class="act-head">${det.map ? badgeIc("inline hide-m") : badgeIc("inline")}<div class="grow"><h2 class="page-title">${esc(a.name)}</h2>
      <div class="act-meta"><span>${icon("calendar")}${when}</span>${det.device ? `<span>${icon("watch")}${esc(det.device)}</span>` : ""}</div>${tags ? `<div class="row" style="margin-top:8px">${tags}</div>` : ""}</div></div>`;
    const tb = tabs("act-detail-tab", [["summary", "Summary"], ["analysis", "Analysis"]].concat(AG.llm ? [["chat", "Chat"]] : [], [["planned", "Planned"]]), tab);
    const body = { summary: actSummary, analysis: actAnalysis, chat: actChat, planned: actPlanned }[tab](a, det);
    return `${hero}${head}${tb}${body}`;
  },
  after() { drawCharts(); },
};

const bstat = (k, v, u) => `<div class="bstat"><span class="k">${esc(k)}</span><span class="v">${v}${u && v !== "—" ? `<small>${esc(u)}</small>` : ""}</span></div>`;
function actStats(a) {
  const hr = isNum(a.avg_hr) ? fmt.n(a.avg_hr) : "—", mx = isNum(a.max_hr) ? fmt.n(a.max_hr) : "—", kc = isNum(a.kcal) ? fmt.n(a.kcal) : "—";
  if (a.family === "strength" || !isNum(a.distance_m)) return [bstat("Duration", fmt.dur(a.duration_s)), bstat("Avg HR", hr, "bpm"), bstat("Max HR", mx, "bpm"), bstat("Active energy", kc, "kcal")].join("");
  const speed = a.family === "ride" ? bstat("Avg speed", isNum(a.speed_kph) ? fmt.n(a.speed_kph, 1) : "—", "km/h") : bstat("Avg pace", fmt.pace(a.pace_s_per_km, false), fmt.paceUnit());
  return [bstat("Distance", fmt.distNum(a.distance_m, 2), fmt.distUnit()), bstat("Moving time", fmt.dur(a.moving_s || a.duration_s)), speed, bstat("Elevation gain", fmt.elev(a.elevation_gain_m)),
    bstat("Avg HR", hr, "bpm"), bstat("Max HR", mx, "bpm"), bstat("Active energy", kc, "kcal"), a.moving_s && fmt.dur(a.moving_s) !== fmt.dur(a.duration_s) ? bstat("Elapsed time", fmt.dur(a.duration_s)) : ""].join("");
}
function hrCard(a, det) {
  const s = det.series;
  if (!s || !s.hr || !s.hr.some(isNum)) return "";
  const z = det.zones || [];
  const t0 = Date.parse(a.start);
  const clock = v => fmt.time(new Date(t0 + v * 1000).toISOString());
  return `<div class="card">${cardHead(`${icon("heart")}Heart rate`)}
    ${chart({ id: "act-hr", label: "Heart rate over the activity", x: s.t, h: 190, series: [{ name: "Heart rate", values: s.hr, color: "var(--bad)", width: 2.2, area: true, areaOpacity: 0.18, vStops: z.length ? z.map((q, i) => ({ v: isNum(q.low) && isNum(q.high) ? (q.low + q.high) / 2 : q.high || q.low, color: `var(--z${i + 1})` })) : null }],
      refLines: z.slice(1).map((q, i) => ({ y: q.low, color: `color-mix(in srgb, var(--z${i + 2}) 70%, transparent)` })), yTickValues: z.slice(1).map(q => q.low),
      fmtX: v => clock(v), fmtXAxis: v => clock(v), fmtY: v => fmt.n(v) + " bpm", xTicks: 3 })}</div>`;
}
function zonesTable(zones, range, unitLabel) {
  const tot = zones.reduce((t, q) => t + (q.s || 0), 0) || 1;
  const rows = zones.map((q, i) => ({ q, i })).reverse().map(({ q, i }) => {
    const pct = (q.s || 0) / tot * 100;
    return `<div class="zrow ${q.s ? "" : "zero"}"><span class="zn">${i + 1}</span><span class="zbar"><i style="width:${Math.max(pct ? 3 : 0, pct)}%;background:var(--z${i + 1})"></i></span><span class="zp">${fmt.n(pct)}%</span><span class="zd">${fmt.dur(q.s || 0)}</span><span class="zr">${range(q)}</span></div>`;
  }).join("");
  return `<div class="ztable"><div class="zrow zh"><span class="zn">Zone</span><span class="zbar"></span><span class="zp">%</span><span class="zd">Time</span><span class="zr">${esc(unitLabel)}</span></div>${rows}</div>`;
}
function paceCell(p, fastest) {
  return `<span class="pcell"><i style="width:${isNum(p) && isNum(fastest) ? Math.max(30, Math.min(100, fastest / p * 100)) : 0}%"></i><b>${fmt.pace(p, false)}</b></span>`;
}
function splitsCard(det) {
  const sp = (IMPERIAL ? det.splits_mi : det.splits) || [];
  if (!sp.length) return "";
  const fastest = Math.min(...sp.filter(x => !x.partial).map(x => x.pace_s_per_km).filter(isNum));
  const v = det.verdict;
  return `<div class="card">${cardHead("Splits", v ? badge(`${fmt.sport(v.verdict)} split`, v.verdict === "negative" ? "ok" : v.verdict === "positive" ? "warn" : "est") : "")}
    <div class="stable"><div class="srow sh"><span>${IMPERIAL ? "Mi" : "Km"}</span><span>${fmt.paceUnit()}</span><span class="r">bpm</span><span class="r">Elev</span></div>
    ${sp.map(x => `<div class="srow"><span>${x.partial ? fmt.distNum(x.distance_m, 2) : x.n}</span>${paceCell(x.pace_s_per_km, fastest)}<span class="r hrv">${isNum(x.avg_hr) ? x.avg_hr : "—"}</span><span class="r muted">${isNum(x.elev_delta_m) ? fmt.signed(IMPERIAL ? x.elev_delta_m * 3.28 : x.elev_delta_m, 0) : "—"}</span></div>`).join("")}</div></div>`;
}
function intervalsCard(det) {
  if (!det.intervals || !det.intervals.length) return "";
  const fastest = Math.min(...det.intervals.map(x => x.pace_s_per_km).filter(isNum));
  return `<div class="card">${cardHead("Intervals", "", "Detected from sustained pace above your threshold.")}<div class="stable"><div class="srow sh iv"><span>Rep</span><span>Time</span><span>${fmt.distUnit()}</span><span>${fmt.paceUnit()}</span><span class="r">bpm</span></div>
    ${det.intervals.map(l => `<div class="srow iv"><span class="ivn">${icon("chevsup")}${l.n}</span><span>${fmt.dur(l.time_s)}</span><span class="muted">${fmt.distNum(l.distance_m, 2)}</span>${paceCell(l.pace_s_per_km, fastest)}<span class="r hrv">${l.avg_hr || "—"}</span></div>`).join("")}</div></div>`;
}

function actSummary(a, det) {
  const ins = det.insights;
  const p = det.planned;
  const sets = (D.strength.sessions || []).find(x => x.workout_id === a.id);
  const trained = sets && sets.muscles ? sets.muscles : null;
  const rc = det.race;
  const race = rc ? `<div class="card">${cardHead("Race" + (rc.race_name ? " · " + esc(rc.race_name) : ""), rc.splits_verdict ? badge(fmt.sport(rc.splits_verdict.verdict) + " split", rc.splits_verdict.verdict === "negative" ? "ok" : "est") : "", rc.prediction ? `The prediction uses your ${fmt.distLabel(rc.prediction.source.distance_m)} on ${fmt.date(rc.prediction.source.date)}, from efforts before race day only.` : "")}
    <div class="stats-grid s3">${stat("Finish", fmt.dur(rc.finish_s))}${stat("Pace", fmt.pace(rc.pace_s_per_km))}${stat("Distance", fmt.dist(rc.distance_m))}</div>
    <table class="tbl" style="margin-top:8px"><tr><th></th><th class="r">Time</th><th class="r">Pace</th><th class="r">Δ</th></tr>
    ${rc.goal_time_s ? `<tr><td>Your goal</td><td class="r">${fmt.dur(rc.goal_time_s)}</td><td class="r">${fmt.pace(rc.planned_pace_s_per_km)}</td><td class="r">${fmt.signed(rc.vs_goal_s, 0)} s</td></tr>` : ""}
    ${rc.prediction ? `<tr><td>Prediction</td><td class="r">${fmt.dur(rc.prediction.time_s)}</td><td class="r">${fmt.pace(rc.prediction.pace_s_per_km)}</td><td class="r">${fmt.signed(rc.vs_prediction_s, 0)} s</td></tr>` : ""}</table></div>` : "";
  const strain = `<div class="card act-strain">${ring("strain", { v: a.strain, status: "ok" }, { label: "Activity strain", sm: true })}<div class="grow"><div class="t">Activity strain</div><div class="s">Load ${a.load && isNum(a.load.v) ? fmt.n(a.load.v) : "—"}${a.load && a.load.kind === "estimated" ? " · estimate" : ""}</div></div>${a.load ? info("Load", "", a.load) : ""}</div>`;
  const stats = `<div class="card"><div class="bstats">${actStats(a)}</div></div>`;
  const plan = p ? `<div class="card">${cardHead("Plan vs actual", badge(fmt.sport(p.compliance || "planned"), p.compliance === "as_planned" ? "ok" : "warn"))}
      <table class="tbl"><tr><th></th><th class="r">Plan</th><th class="r">Actual</th></tr>
      <tr><td>Duration</td><td class="r">${fmt.dur(p.duration_s)}</td><td class="r">${fmt.dur(p.actual_duration_s)}</td></tr>
      <tr><td>Load</td><td class="r">${isNum(p.planned_load) ? fmt.n(p.planned_load) : "—"}</td><td class="r">${isNum(p.actual_load) ? fmt.n(p.actual_load) : "—"}</td></tr>
      ${p.distance_m || p.actual_distance_m ? `<tr><td>Distance</td><td class="r">${p.distance_m ? fmt.dist(p.distance_m) : "—"}</td><td class="r">${fmt.dist(p.actual_distance_m)}</td></tr>` : ""}</table></div>` : "";
  const notes = ins.facts.length || ins.improvements.length ? `<div class="card">${cardHead("What stood out")}<div class="list">${ins.facts.map(f => `<div class="li"><div class="grow small">${esc(f.text)}</div></div>`).join("")}${ins.improvements.map(i => `<div class="li"><span class="spark-dot">${icon("sparkles")}</span><div class="grow small" style="font-weight:600">${esc(i.text)}</div></div>`).join("")}</div></div>` : "";
  const zones = det.zones ? `<div class="card">${cardHead(`${icon("hrec")}Heart-rate zones`)}${zonesTable(det.zones, q => !q.low ? `<${q.high}` : `${q.low}–${q.high}`, "bpm")}</div>` : "";
  const efforts = det.efforts && det.efforts.length ? `<div class="card">${cardHead("Best efforts")}<div class="list">${det.efforts.map(e => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(e.distance_m)}</div></div><div class="r">${fmt.dur(e.time_s)} ${e.pr ? badge("PR", "accent") : e.rank ? badge("#" + e.rank, "") : ""}</div></div>`).join("")}</div></div>` : "";
  const matched = det.matched ? `<div class="card">${cardHead("Matched runs", `<span class="small muted">${det.matched.rank} of ${det.matched.count}${det.matched.match_kind === "approximate" ? " · approximate" : ""}</span>`)}
      ${chart({ id: "matched", label: "Pace on matched runs", x: det.matched.rows.map(r => r.date), h: 140, invertY: true,
        series: [{ name: "Pace", color: "var(--accent)", values: det.matched.rows.map(r => r.pace_s_per_km), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.pace(v), fmtYAxis: v => fmt.pace(v, false) })}</div>` : "";
  const weather = det.weather ? `<div class="card">${cardHead("Weather", det.weather.conditions ? `<span class="small muted">${esc(det.weather.conditions)}</span>` : "")}<div class="bstats three">${bstat("Temp", fmt.temp(det.weather.temp_c))}${bstat("Humidity", fmt.pct(det.weather.humidity_pct))}${bstat("Wind", isNum(det.weather.wind_kph) ? fmt.n(det.weather.wind_kph) : "—", "km/h")}</div></div>` : "";
  const muscles = trained ? `<div class="card">${cardHead("Muscles trained")}${muscleMap({}, "freshness", trained)}</div>` : a.family === "strength" ? `<div class="card">${empty(STR.noExercise, "Log sets in the Strength Builder to see trained muscles")}</div>` : "";
  const map = `<div class="card map-card hide-m">${det.map ? mapSvg(det.map, { label: "Activity route", w: 560, h: 340, pad: 28 }) : empty(STR.noRoute, a.family === "strength" ? "Indoor session" : "No GPS samples")}</div>`;
  const rpe = `<div class="card">${cardHead("Perceived effort")}${rpeForm(a, det)}</div>`;
  const hr = hrCard(a, det) || (det.has_samples === false && a.family !== "strength" ? `<div class="card">${cardHead(`${icon("heart")}Heart rate`)}${empty("No heart-rate samples", "Zones, the heart-rate chart and best efforts need the workout's samples")}</div>` : "");
  const o = (n, html) => html ? `<div class="o" style="order:${n}">${html}</div>` : "";
  return `<div class="flow2"><div class="flow-a">${o(0, map)}${o(3, hr)}${o(4, zones)}${o(5, splitsCard(det))}${o(6, intervalsCard(det))}${o(10, muscles)}</div>
    <div class="flow-b">${o(1, race)}${o(1, strain)}${o(2, stats)}${o(7, plan)}${o(8, notes)}${o(9, efforts)}${o(11, matched)}${o(12, rpe)}${o(13, weather)}</div></div>`;
}

function rpeForm(a, det) {
  const ann = det.annotation || {};
  const desc = ["", "Very easy", "Easy", "Moderate", "Somewhat hard", "Hard", "Hard+", "Very hard", "Very hard+", "Max effort", "Max"];
  const faces = [["1", "Terrible"], ["2", "Not great"], ["3", "OK"], ["4", "Great"], ["5", "Amazing"]];
  const rpe = ann.rpe || 5;
  return `<form class="form" data-rpe-form="${esc(a.id)}">
    <label>Perceived exertion (RPE) <input type="range" min="1" max="10" step="1" name="rpe" value="${rpe}" aria-valuetext="${rpe} ${desc[rpe]}"><span class="small"><b>${ann.rpe || "—"}</b> ${esc(ann.rpe ? desc[ann.rpe] : "not logged")}</span></label>
    <div><div class="small muted" style="margin-bottom:6px">Feel</div><div class="rpe-faces">${faces.map(([v, l]) => `<button type="button" data-feel="${v}" aria-pressed="${String(ann.feel) === v}">${l}</button>`).join("")}</div></div>
    <label>Comment <textarea name="comment" rows="2" placeholder="How the session went">${esc(ann.comment || "")}</textarea></label>
    <label class="row" style="flex-direction:row;align-items:center"><input type="checkbox" name="private" ${ann.private ? "checked" : ""} style="width:auto"> Private</label>
    ${AG.online ? `<div class="actions" style="margin-top:0"><button class="btn" type="submit">Save</button></div>` : ""}</form>`;
}
document.addEventListener("click", e => {
  const f = e.target.closest("[data-feel]");
  if (f) { $$("[data-feel]", f.parentElement).forEach(b => b.setAttribute("aria-pressed", "false")); f.setAttribute("aria-pressed", "true"); }
});
document.addEventListener("submit", async e => {
  const form = e.target.closest("[data-rpe-form]");
  if (!form) return;
  e.preventDefault();
  const feel = $("[data-feel][aria-pressed=true]", form);
  const body = { workout_id: form.dataset.rpeForm, rpe: +form.rpe.value, feel: feel ? +feel.dataset.feel : null, comment: form.comment.value || null, private: form.private.checked };
  try { await save("POST", "entries/load.annotations", body, "Saved"); } catch (err) { /* shown */ }
});

function actAnalysis(a, det) {
  const s = det.series;
  if (!s) return empty("No sample streams for this activity", "Charts need second-by-second data from HealthKit");
  const xs = s.dist_m && s.dist_m.some(isNum) ? s.dist_m : s.t;
  const byDist = xs === s.dist_m;
  const fx = v => byDist ? fmt.dist(v) : fmt.dur(v);
  const fxa = v => byDist ? fmt.distNum(v, 1) : fmt.dur(v);
  const metrics = [
    ["pace_s_per_km", "Pace", "var(--info)", v => fmt.pace(v), true], ["gap_s_per_km", "Grade-adjusted pace", "var(--prior)", v => fmt.pace(v), true],
    ["hr", "Heart rate", "var(--bad)", v => fmt.n(v) + " bpm"], ["elev_m", "Elevation", "var(--text-2)", v => fmt.elev(v)],
    ["cadence", "Cadence", "#b06cff", v => fmt.n(v) + " spm"], ["power_w", "Power", "var(--accent)", v => fmt.n(v) + " W"],
    ["gct_ms", "Ground contact", "var(--warn)", v => fmt.n(v) + " ms"], ["vo_cm", "Vertical oscillation", "var(--warn)", v => fmt.n(v, 1) + " cm"],
    ["stride_m", "Stride length", "var(--warn)", v => fmt.n(v, 2) + " m"], ["temp_c", "Temperature", "var(--warn)", v => fmt.temp(v)],
  ].filter(m => s[m[0]] && s[m[0]].some(isNum));
  const charts = metrics.map(([k, name, color, f, inv]) => `<div class="card">${cardHead(esc(name), k === "gap_s_per_km" ? badge("Approximate", "est") : "")}
    ${chart({ id: "an-" + k, label: name + " over the activity", x: xs, h: 130, invertY: !!inv, series: [{ name, color, values: s[k], area: k === "elev_m", areaOpacity: .18 }],
      fmtX: fx, fmtXAxis: fxa, fmtY: f, fmtYAxis: inv ? v => fmt.pace(v, false) : undefined,
      band: k === "hr" && det.zones ? { low: det.zones[1].low, high: det.zones[1].high, color: "color-mix(in srgb, var(--z2) 14%, transparent)", name: "Zone 2" } : null })}</div>`).join("");
  const laps = det.laps.length ? `<div class="card">${cardHead("Laps")}<table class="tbl"><tr><th>#</th><th class="r">Time</th><th class="r">Distance</th><th class="r">Pace</th><th class="r">HR</th></tr>${det.laps.map(l => `<tr><td>${l.n}</td><td class="r">${fmt.dur(l.time_s)}</td><td class="r">${fmt.dist(l.distance_m)}</td><td class="r">${fmt.pace(l.pace_s_per_km, false)}</td><td class="r">${l.avg_hr || "—"}</td></tr>`).join("")}</table></div>` : "";
  const seg = det.segments && det.segments.length ? `<div class="card">${cardHead("Multisport")}<table class="tbl">${det.segments.map(sg => `<tr><td>${esc(fmt.sport(sg.sport))}</td><td class="r">${fmt.dur(sg.end_s - sg.start_s)}</td><td class="r">${fmt.dist(sg.distance_m)}</td></tr>`).join("")}</table></div>` : "";
  const curves = `${det.hr_curve ? `<div class="card">${cardHead("Heart-rate curve")}${chart({ id: "hrc", type: "curve", label: "Best average heart rate by duration", points: det.hr_curve, h: 140, name: "Best avg HR", color: "var(--bad)", fmtY: v => fmt.n(v) + " bpm" })}</div>` : ""}
    ${det.power_curve ? `<div class="card">${cardHead("Power curve")}${chart({ id: "pwc", type: "curve", label: "Best average power by duration", points: det.power_curve, h: 140, name: "Best avg power", color: "var(--accent)", fmtY: v => fmt.n(v) + " W" })}</div>` : ""}`;
  const extra = `<div class="card">${cardHead("Efficiency", "", `Efficiency factor is speed per heartbeat${det.gap ? ", grade-adjusted" : ""}. Intensity compares with your ${esc(det.intensity_basis || "threshold")}. HR drift compares the pace-to-heart-rate ratio of the first and second half.`)}<div class="stats-grid s4">${stat("Efficiency", isNum(det.efficiency_factor) ? fmt.n(det.efficiency_factor, 2) : "—")}${stat("Intensity", isNum(det.intensity_pct) ? det.intensity_pct + "%" : "—")}${stat("HR drift", isNum(det.decoupling_pct) ? fmt.n(det.decoupling_pct, 1) + "%" : "—")}${stat("HR recovery", isNum(det.hr_recovery) ? det.hr_recovery + " bpm" : "—")}</div>
</div>`;
  const pz = det.pace_zones ? `<div class="card">${cardHead("Pace zones")}${det.pace_zones.map((z, i) => `<div class="row" style="gap:8px;margin:4px 0"><span class="small" style="width:28px">${z.name}</span><div class="bar thin" style="flex:1"><i style="width:${z.s / (det.pace_zones.reduce((t, x) => t + x.s, 0) || 1) * 100}%;background:var(--z${i + 1})"></i></div><span class="small num" style="width:52px;text-align:right">${fmt.mins(z.s)}</span></div>`).join("")}</div>` : "";
  return `<div class="cols"><div class="stack">${charts}</div><div class="stack">${extra}${laps}${seg}${pz}${curves}${det.map ? `<div class="card">${cardHead("Replay")}${flyover(det)}</div>` : ""}</div></div>`;
}

function flyover(det) {
  const id = "fly" + Math.random().toString(36).slice(2, 7);
  setTimeout(() => {
    const host = document.getElementById(id);
    if (!host) return;
    const svgEl = host.querySelector("svg");
    const lines = det.map;
    const pts = lines.flat();
    const pr = project(lines, 320, 200, 14);
    const dot = host.querySelector(".fly-dot"), lab = host.querySelector(".fly-lab");
    const s = det.series;
    let i = 0, timer = null;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = () => {
      const p = pr(pts[i]);
      dot.setAttribute("cx", p[0]); dot.setAttribute("cy", p[1]);
      const k = Math.round(i / pts.length * (s.t.length - 1));
      lab.textContent = `${fmt.dur(s.t[k])} · ${s.dist_m ? fmt.dist(s.dist_m[k]) : ""}${s.hr && isNum(s.hr[k]) ? " · " + s.hr[k] + " bpm" : ""}`;
      i++;
      if (i >= pts.length) { clearInterval(timer); timer = null; i = 0; }
    };
    host.querySelector("button").onclick = () => {
      if (reduce) { i = pts.length - 1; step(); return; }
      if (timer) { clearInterval(timer); timer = null; return; }
      timer = setInterval(step, 30);
    };
    step();
  }, 0);
  return `<div id="${id}">${mapSvg(det.map, { label: "Activity replay", noEnds: true }).replace("</svg>", `<circle class="fly-dot" r="6" fill="var(--accent)" stroke="#fff" stroke-width="2"/></svg>`)}
    <div class="spread" style="margin-top:8px"><span class="small fly-lab"></span><button class="btn sm secondary" type="button">Play / pause</button></div></div>`;
}

function actChat(a, det) {
  return `<div class="card">${AG.llm ? "" : empty(STR.noCoachLLM, "Set AGAME_LLM_PROVIDER on your server to ask questions about this activity. Answers use only AGame's computed data.")}
    <div class="chat" style="margin-top:12px">${det.insights.facts.map(f => `<div class="msg coach">${esc(f.text)}</div>`).join("")}${det.insights.improvements.map(f => `<div class="msg coach">${esc(f.text)}</div>`).join("")}</div>
    <form class="composer" style="margin-top:14px" data-coach-form data-activity="${esc(a.id)}"><label class="sr" for="ac-q">Ask about this activity</label><div class="composer-row"><textarea id="ac-q" name="q" rows="1" placeholder="Ask about this activity" ${AG.online ? "" : "disabled"}></textarea><button class="send" aria-label="Ask" ${AG.online ? "" : "disabled"}>${icon("up")}</button></div></form></div>`;
}

function actPlanned(a, det) {
  const p = det.planned;
  if (!p) return `<div class="card">${empty("Unplanned", "No planned session matched this activity")}</div>`;
  return `<div class="card">${cardHead(esc(p.title || p.label), badge(fmt.sport(p.compliance), p.compliance === "as_planned" ? "ok" : "warn"))}
    ${p.objective ? `<p class="small muted">${esc(p.objective)}</p>` : ""}${stepList(p.steps)}
    <table class="tbl" style="margin-top:10px"><tr><th></th><th class="r">Plan</th><th class="r">Actual</th></tr><tr><td>Duration</td><td class="r">${fmt.dur(p.duration_s)}</td><td class="r">${fmt.dur(p.actual_duration_s)}</td></tr><tr><td>Load</td><td class="r">${isNum(p.planned_load) ? fmt.n(p.planned_load) : "—"}</td><td class="r">${isNum(p.actual_load) ? fmt.n(p.actual_load) : "—"}</td></tr></table></div>`;
}
