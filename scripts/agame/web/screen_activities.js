/* Activities list, activity detail (post-workout report), social */
"use strict";

AG.screens.activities = {
  title: "Activities",
  render() {
    const tab = chipVal("act-tab", "list");
    return `${seg("act-tab", [["list", "Activities"], ["social", "Social"]], tab)}<div style="margin-top:12px">${tab === "social" ? socialView() : activityList()}</div>`;
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
  rows.slice(0, 200).forEach(a => { const k = a.date.slice(0, 7); (groups[k] = groups[k] || []).push(a); });
  return `<div class="stack"><label class="sr" for="act-q">Search activities</label><input id="act-q" type="search" placeholder="Search activities" value="${esc(uiGet("act-q", ""))}" data-search>
    ${chips("act-fam", [["all", "All"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"], ["swim", "Swim"], ["other", "Other"]], fam)}
    ${chips("act-flt", [["any", "Any"], ["gps", "With map"], ["pr", "PRs"], ["planned", "Planned"], ["unplanned", "Unplanned"]], flt, "accent")}
    ${Object.keys(groups).length ? Object.entries(groups).map(([m, list]) => `<div>${sectionTitle(fmt.date(m + "-15", { month: "long", year: "numeric" }), `<span class="cap">${list.length}</span>`)}<div class="card tight"><div class="list">${list.map(feedCard).join("")}</div></div></div>`).join("") : empty("No activities match")}</div>`;
}
document.addEventListener("input", e => {
  if (e.target.matches("[data-search]")) { uiSet("act-q", e.target.value); clearTimeout(AG._sq); AG._sq = setTimeout(() => { rerender(); const el = $("#act-q"); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }, 250); }
});

function feedCard(a) {
  const det = D.activities.details[a.id];
  const prs = det && det.efforts ? det.efforts.filter(e => e.pr).length : 0;
  const statsRow = a.family === "run" || a.family === "walk" || a.family === "ride"
    ? `${stat("Distance", fmt.dist(a.distance_m))}${stat(a.family === "ride" ? "Speed" : "Pace", a.family === "ride" ? fmt.n(a.speed_kph, 1) + " km/h" : fmt.pace(a.pace_s_per_km))}${stat("Time", fmt.dur(a.moving_s || a.duration_s))}`
    : `${stat("Time", fmt.dur(a.duration_s))}${stat("Avg HR", isNum(a.avg_hr) ? fmt.n(a.avg_hr) : "—", isNum(a.avg_hr) ? "bpm" : "")}${stat("Load", a.load && isNum(a.load.v) ? fmt.n(a.load.v) : "—")}`;
  return `<a class="li" href="#/activity/${encodeURIComponent(a.id)}" style="align-items:flex-start">
    <span class="icon-dot" style="color:${sportColor(a.family)}">${sportIcon(a.family)}</span>
    <div class="grow"><div class="spread"><div class="t">${esc(a.name)}</div>${prs ? badge(prs + " PR", "accent") : a.planned ? badge(fmt.sport(a.planned.compliance || "planned"), a.planned.compliance === "as_planned" ? "ok" : "info") : ""}</div>
      <div class="s">${fmt.dow(a.date)} ${fmt.date(a.date)} · ${fmt.time(a.start)}${a.private ? " · private" : ""}</div>
      <div class="stats-grid s3" style="margin-top:8px">${statsRow}</div></div>
    ${det && det.map ? `<span class="hide-m">${routeThumb(det.map)}</span>` : ""}</a>`;
}

function socialView() {
  const S = D.social;
  return `<div class="cols"><div class="stack">
    <div class="card"><h3>${icon("social")} Feed</h3>${S.posts.length ? `<div class="list">${S.posts.map(p => `<div class="li"><div class="grow"><div class="t">${esc(p.title || "Post")}</div><div class="s">${esc(p.source)}</div></div></div>`).join("")}</div>` : empty(STR.noFeed, "Comparing with other runners comes later, on real data only. No names or ranks are ever generated.")}</div>
    <div class="card"><h3>Clubs</h3>${S.clubs.length ? `<div class="list">${S.clubs.map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.name || c.id)}</div><div class="s">${esc(c.source)}</div></div></div>`).join("")}</div>` : empty(STR.noClubs)}</div>
    <div class="card"><h3>Leaderboards</h3>${empty(STR.noLeaderboard, "Segment leaderboards render only from supplied participant data")}</div></div>
    <div class="stack"><div class="card"><h3>My challenges</h3>${S.own_challenges.length ? S.own_challenges.map(goalRow).join("") : empty(STR.noChallenges, "Distance, time or session goals for a period show here as personal challenges")}</div>
    <div class="card"><h3>Group challenges</h3>${S.challenges.length ? `<div class="list">${S.challenges.map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.name || c.id)}</div><div class="s">${esc(c.source)}</div></div></div>`).join("")}</div>` : empty(STR.noChallenges)}</div>
    <div class="card"><h3>Events & races</h3>${S.races.length ? `<div class="list">${S.races.map(r => `<div class="li"><span class="badge ${r.priority === "A" ? "accent" : ""}">${esc(r.priority || "")}</span><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })}${r.distance_m ? " · " + fmt.dist(r.distance_m) : ""}</div></div></div>`).join("")}</div>` : empty("No events added")}</div>
    <div class="card"><h3>Leaderboard integrity</h3><p class="small">${D.routes.integrity.checked} of your activities checked · ${D.routes.integrity.own.length} flagged</p>${D.routes.integrity.own.map(f => `<div class="li"><div class="grow"><div class="t">${fmt.date(f.date)}</div><div class="s">${esc(f.reason)}</div></div>${badge("Flagged", "warn")}</div>`).join("")}</div></div></div>`;
}

/* ---------------- activity detail ---------------- */
AG.screens.activity = {
  title: r => { const a = D.activities.list.find(x => x.id === r.arg); return a ? a.name : "Activity"; },
  parent: "#/activities", nav: "activities",
  render(r) {
    const a = D.activities.list.find(x => x.id === r.arg);
    if (!a) return empty("Activity not found", "It may be older than this snapshot");
    const det = D.activities.details[a.id];
    if (!det) return `<div class="card">${feedCard(a)}</div>${empty("Details not embedded", `Only the latest ${D.meta.detail_max_activities} activities carry full streams in this snapshot`)}`;
    const tab = chipVal("act-detail-tab", "summary");
    const head = `<div class="card"><div class="row"><span class="icon-dot" style="color:${sportColor(a.family)}">${sportIcon(a.family)}</span><div class="grow"><div class="cap">${fmt.dateLong(a.date)} · ${fmt.time(a.start)}${det.device ? " · " + esc(det.device) : ""}</div><div style="font-size:20px;font-weight:800">${esc(det.insights.headline)}</div></div></div></div>`;
    const tabs = seg("act-detail-tab", [["summary", "Summary"], ["analysis", "Analysis"], ["chat", "Chat"], ["planned", "Planned"]], tab);
    const body = { summary: actSummary, analysis: actAnalysis, chat: actChat, planned: actPlanned }[tab](a, det);
    return `<div class="stack">${head}<div>${tabs}</div>${body}</div>`;
  },
  after() { drawCharts(); },
};

function actSummary(a, det) {
  const ins = det.insights;
  const row = det.row;
  const grid = a.family === "strength"
    ? `${stat("Elapsed", fmt.dur(a.duration_s))}${stat("Avg HR", isNum(a.avg_hr) ? fmt.n(a.avg_hr) : "—", "bpm")}${stat("Load", a.load && isNum(a.load.v) ? fmt.n(a.load.v) : "—")}${stat("Strain", isNum(a.strain) ? fmt.n(a.strain) + "%" : "—")}`
    : `${stat("Distance", fmt.dist(a.distance_m))}${stat("Moving time", fmt.dur(a.moving_s || a.duration_s))}${stat(a.family === "ride" ? "Speed" : "Pace", a.family === "ride" ? fmt.n(a.speed_kph, 1) + " km/h" : fmt.pace(a.pace_s_per_km))}${stat("Elevation", fmt.elev(a.elevation_gain_m))}
       ${stat("Avg HR", isNum(a.avg_hr) ? fmt.n(a.avg_hr) : "—", isNum(a.avg_hr) ? "bpm" : "")}${stat("Load", a.load && isNum(a.load.v) ? fmt.n(a.load.v) : "—")}${stat("Strain", isNum(a.strain) ? fmt.n(a.strain) + "%" : "—")}${stat("Calories", isNum(a.kcal) ? fmt.n(a.kcal) : "—")}`;
  const zones = det.zones;
  const ztot = zones ? zones.reduce((s, z) => s + z.s, 0) || 1 : 1;
  const p = det.planned;
  const sets = (D.strength.sessions || []).find(s => s.workout_id === a.id);
  const trained = sets && sets.muscles ? sets.muscles : null;
  return `<div class="cols"><div class="stack">
    <div class="card"><div class="stats-grid s4">${grid}</div>${a.load ? `<div class="spread" style="margin-top:8px">${estBadge(a.load)}<span class="cap">${esc(a.load.method === "trimp_stream" ? "Load from heart-rate stream" : a.load.method === "trimp_avg_hr" ? "Load from average HR (estimate)" : a.load.method === "session_rpe" ? "Load from RPE (estimate)" : a.load.note || "")}</span>${prov(a.load, "Load")}</div>` : ""}</div>
    ${p ? `<div class="card" style="background:${p.compliance === "as_planned" ? "color-mix(in srgb,var(--ok) 10%,var(--surface))" : "var(--surface)"}"><div class="spread"><h3 style="margin:0">Compliance</h3>${badge(fmt.sport(p.compliance || "planned"), p.compliance === "as_planned" ? "ok" : "warn")}</div>
      <table class="tbl" style="margin-top:8px"><tr><th></th><th class="r">Plan</th><th class="r">Actual</th></tr>
      <tr><td>Duration</td><td class="r">${fmt.dur(p.duration_s)}</td><td class="r">${fmt.dur(p.actual_duration_s)}</td></tr>
      <tr><td>Load</td><td class="r">${isNum(p.planned_load) ? fmt.n(p.planned_load) : "—"}</td><td class="r">${isNum(p.actual_load) ? fmt.n(p.actual_load) : "—"}</td></tr>
      ${p.distance_m || p.actual_distance_m ? `<tr><td>Distance</td><td class="r">${p.distance_m ? fmt.dist(p.distance_m) : "—"}</td><td class="r">${fmt.dist(p.actual_distance_m)}</td></tr>` : ""}</table></div>` : ""}
    ${ins.facts.length ? `<div class="card"><h3>${icon("coach")} Activity summary</h3>${ins.facts.map(f => `<div class="li"><div class="grow small">${esc(f.text)}</div></div>`).join("")}<p class="cap">Built only from this activity's measured data and your own history.</p></div>` : ""}
    <div class="card"><h3>Improvements</h3>${ins.improvements.length ? ins.improvements.map(i => insightCard(i.text, null)).join("") : `<p class="small muted">Solid execution — no flags from your data.</p>`}</div>
    ${trained ? `<div class="card"><h3>Muscles trained</h3>${muscleMap({}, "freshness", trained)}</div>` : a.family === "strength" ? `<div class="card">${empty(STR.noExercise, "Log sets in the Strength Builder to see trained muscles")}</div>` : ""}
    </div><div class="stack">
    <div class="card">${det.map ? mapSvg(det.map, { label: "Activity route" }) : empty(STR.noRoute, a.family === "strength" ? "Indoor session" : "No GPS samples")}</div>
    ${zones ? `<div class="card"><h3>Heart-rate zones</h3>${zones.map((z, i) => `<div class="row" style="gap:8px;margin:4px 0"><span class="small" style="width:28px">${z.name}</span><div class="bar thin" style="flex:1"><i style="width:${z.s / ztot * 100}%;background:var(--z${i + 1})"></i></div><span class="small num" style="width:52px;text-align:right">${fmt.mins(z.s)}</span></div>`).join("")}</div>` : ""}
    ${det.efforts && det.efforts.length ? `<div class="card"><h3>Best efforts</h3><div class="list">${det.efforts.map(e => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(e.distance_m)}</div></div><div class="r">${fmt.dur(e.time_s)} ${e.pr ? badge("PR", "accent") : e.rank ? badge("#" + e.rank, "") : ""}</div></div>`).join("")}</div></div>` : ""}
    ${det.matched ? `<div class="card"><h3>Matched runs</h3><p class="small">Rank ${det.matched.rank} of ${det.matched.count} on this ${det.matched.match_kind === "approximate" ? "distance (approximate match)" : "route"}</p>
      ${chart({ id: "matched", label: "Pace on matched runs", x: det.matched.rows.map(r => r.date), h: 140, invertY: true,
        series: [{ name: "Pace", color: "var(--accent)", values: det.matched.rows.map(r => r.pace_s_per_km), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.pace(v), fmtYAxis: v => fmt.pace(v, false) })}</div>` : ""}
    ${det.weather ? `<div class="card"><h3>Weather</h3><div class="stats-grid s3">${stat("Temp", fmt.temp(det.weather.temp_c))}${stat("Humidity", fmt.pct(det.weather.humidity_pct))}${stat("Wind", isNum(det.weather.wind_kph) ? fmt.n(det.weather.wind_kph) + " km/h" : "—")}</div><p class="cap">${esc(det.weather.conditions || "")} · from imported data${det.weather.source ? " (" + esc(det.weather.source) + ")" : ""}</p></div>` : ""}
    <div class="card"><h3>How did it feel?</h3>${rpeForm(a, det)}</div></div></div>`;
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
    <button class="btn" type="submit" ${AG.online ? "" : "disabled"}>Save</button>${offlineNote()}</form>`;
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
  try { await api("POST", "entries/load.annotations", body); toast("Saved · rebuilding"); setTimeout(() => location.reload(), 900); } catch (err) { toast(err.message); }
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
  const charts = metrics.map(([k, name, color, f, inv]) => `<div class="card"><div class="spread"><h3 style="margin:0">${esc(name)}</h3>${k === "gap_s_per_km" ? badge("Approximate", "est") : ""}</div>
    ${chart({ id: "an-" + k, label: name + " over the activity", x: xs, h: 130, invertY: !!inv, series: [{ name, color, values: s[k], area: k === "elev_m", areaOpacity: .18 }],
      fmtX: fx, fmtXAxis: fxa, fmtY: f, fmtYAxis: inv ? v => fmt.pace(v, false) : undefined,
      band: k === "hr" && det.zones ? { low: det.zones[1].low, high: det.zones[1].high, color: "color-mix(in srgb, var(--z2) 14%, transparent)", name: "Zone 2" } : null })}</div>`).join("");
  const sp = (IMPERIAL ? det.splits_mi : det.splits) || [];
  const fastest = Math.min(...sp.filter(x => !x.partial).map(x => x.pace_s_per_km).filter(isNum));
  const splits = sp.length ? `<div class="card"><div class="spread"><h3 style="margin:0">Splits</h3>${det.verdict ? `<span class="split-verdict ${det.verdict.verdict === "negative" ? "up" : det.verdict.verdict === "positive" ? "down" : "muted"}">${esc(det.verdict.verdict)} split</span>` : ""}</div>
    <table class="tbl" style="margin-top:6px"><tr><th>${IMPERIAL ? "Mi" : "Km"}</th><th>Pace</th><th></th><th class="r">Elev</th><th class="r">HR</th></tr>${sp.map(x => `<tr><td>${x.partial ? fmt.distNum(x.distance_m, 2) : x.n}</td><td>${fmt.pace(x.pace_s_per_km, false)}</td><td style="width:40%"><div class="pace-bar" style="width:${isNum(x.pace_s_per_km) ? Math.max(8, Math.min(100, fastest / x.pace_s_per_km * 100)) : 0}%"></div></td><td class="r">${isNum(x.elev_delta_m) ? fmt.signed(IMPERIAL ? x.elev_delta_m * 3.28 : x.elev_delta_m, 0) : "—"}</td><td class="r">${isNum(x.avg_hr) ? x.avg_hr : "—"}</td></tr>`).join("")}</table>
    ${det.verdict ? `<p class="cap">Second half ${fmt.signed(det.verdict.diff_pct, 1)}% vs first half.</p>` : ""}</div>` : "";
  const laps = det.laps.length ? `<div class="card"><h3>Laps</h3><table class="tbl"><tr><th>#</th><th class="r">Time</th><th class="r">Distance</th><th class="r">Pace</th><th class="r">HR</th></tr>${det.laps.map(l => `<tr><td>${l.n}</td><td class="r">${fmt.dur(l.time_s)}</td><td class="r">${fmt.dist(l.distance_m)}</td><td class="r">${fmt.pace(l.pace_s_per_km, false)}</td><td class="r">${l.avg_hr || "—"}</td></tr>`).join("")}</table></div>` : "";
  const iv = det.intervals.length ? `<div class="card"><h3>Intervals</h3><table class="tbl"><tr><th>Rep</th><th class="r">Time</th><th class="r">Distance</th><th class="r">Pace</th><th class="r">HR</th></tr>${det.intervals.map(l => `<tr><td>${l.n}</td><td class="r">${fmt.dur(l.time_s)}</td><td class="r">${fmt.dist(l.distance_m)}</td><td class="r">${fmt.pace(l.pace_s_per_km, false)}</td><td class="r">${l.avg_hr || "—"}</td></tr>`).join("")}</table><p class="cap">Detected from sustained pace above your threshold.</p></div>` : "";
  const seg = det.segments && det.segments.length ? `<div class="card"><h3>Multisport</h3><table class="tbl">${det.segments.map(sg => `<tr><td>${esc(fmt.sport(sg.sport))}</td><td class="r">${fmt.dur(sg.end_s - sg.start_s)}</td><td class="r">${fmt.dist(sg.distance_m)}</td></tr>`).join("")}</table></div>` : "";
  const curves = `${det.hr_curve ? `<div class="card"><h3>Heart-rate curve</h3>${chart({ id: "hrc", type: "curve", label: "Best average heart rate by duration", points: det.hr_curve, h: 140, name: "Best avg HR", color: "var(--bad)", fmtY: v => fmt.n(v) + " bpm" })}</div>` : ""}
    <div class="card"><h3>Power curve</h3>${det.power_curve ? chart({ id: "pwc", type: "curve", label: "Best average power by duration", points: det.power_curve, h: 140, name: "Best avg power", color: "var(--accent)", fmtY: v => fmt.n(v) + " W" }) : `<p class="small muted">${STR.noPower} — power curve omitted.</p>`}</div>`;
  const extra = `<div class="card"><div class="stats-grid s4">${stat("Efficiency factor", isNum(det.efficiency_factor) ? fmt.n(det.efficiency_factor, 2) : "—")}${stat("Intensity", isNum(det.intensity_pct) ? det.intensity_pct + "%" : "—")}${stat("HR drift", isNum(det.decoupling_pct) ? fmt.n(det.decoupling_pct, 1) + "%" : "—")}${stat("HR recovery", isNum(det.hr_recovery) ? det.hr_recovery + " bpm" : "—")}</div>
    <p class="cap">Efficiency = speed per heartbeat${det.gap ? " (grade-adjusted)" : ""}. Intensity vs ${esc(det.intensity_basis || "threshold")}. HR drift = first vs second half pace:HR.</p></div>`;
  const pz = det.pace_zones ? `<div class="card"><h3>Pace zones</h3>${det.pace_zones.map((z, i) => `<div class="row" style="gap:8px;margin:4px 0"><span class="small" style="width:28px">${z.name}</span><div class="bar thin" style="flex:1"><i style="width:${z.s / (det.pace_zones.reduce((t, x) => t + x.s, 0) || 1) * 100}%;background:var(--z${i + 1})"></i></div><span class="small num" style="width:52px;text-align:right">${fmt.mins(z.s)}</span></div>`).join("")}</div>` : "";
  return `<div class="cols"><div class="stack">${charts}</div><div class="stack">${extra}${splits}${laps}${iv}${seg}${pz}${curves}${det.map ? `<div class="card"><h3>Replay</h3>${flyover(det)}</div>` : ""}</div></div>`;
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
    <form class="composer" style="margin-top:12px" data-coach-form data-activity="${esc(a.id)}"><label class="sr" for="ac-q">Ask about this activity</label><textarea id="ac-q" name="q" placeholder="Ask about this activity" ${AG.online ? "" : "disabled"}></textarea><div class="spread"><span class="cap">Grounded in this activity's data</span><button class="btn sm" ${AG.online ? "" : "disabled"}>Ask</button></div></form></div>`;
}

function actPlanned(a, det) {
  const p = det.planned;
  if (!p) return `<div class="card">${empty("Unplanned", "No planned session matched this activity")}</div>`;
  return `<div class="card"><div class="spread"><div><div class="tag">${esc(p.label || p.type)}</div><b style="font-size:18px">${esc(p.title || p.label)}</b></div>${badge(fmt.sport(p.compliance), p.compliance === "as_planned" ? "ok" : "warn")}</div>
    ${p.objective ? `<p class="small muted">${esc(p.objective)}</p>` : ""}${stepList(p.steps)}
    <table class="tbl" style="margin-top:10px"><tr><th></th><th class="r">Plan</th><th class="r">Actual</th></tr><tr><td>Duration</td><td class="r">${fmt.dur(p.duration_s)}</td><td class="r">${fmt.dur(p.actual_duration_s)}</td></tr><tr><td>Load</td><td class="r">${isNum(p.planned_load) ? fmt.n(p.planned_load) : "—"}</td><td class="r">${isNum(p.actual_load) ? fmt.n(p.actual_load) : "—"}</td></tr></table></div>`;
}
