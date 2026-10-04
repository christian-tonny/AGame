/* Training: fitness/freshness, training log, progress, plan & calendar, zones, records, recaps, weekly review */
"use strict";

function toast(msg) {
  let t = $("#toast");
  if (!t) { t = document.createElement("div"); t.id = "toast"; t.className = "tip"; t.setAttribute("role", "status"); t.style.cssText = "left:50%;bottom:90px;top:auto;transform:translateX(-50%)"; document.body.appendChild(t); }
  t.textContent = msg; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 2600);
}

const TRAINING_TABS = [["fitness", "Fitness"], ["log", "Log"], ["progress", "Progress"], ["plan", "Plan"], ["zones", "Zones"], ["records", "Records"], ["recaps", "Recaps"], ["review", "Weekly review"]];

AG.screens.training = {
  title: "Training",
  render(r) {
    const tab = r.params.tab || chipVal("training-tab", "fitness");
    if (r.params.tab) uiSet("chip:training-tab", r.params.tab);
    const body = { fitness: trFitness, log: trLog, progress: trProgress, plan: trPlan, zones: trZones, records: trRecords, recaps: trRecaps, review: trReview }[tab] || trFitness;
    return `${chips("training-tab", TRAINING_TABS, tab)}<div style="margin-top:12px">${body()}</div>`;
  },
  after() { drawCharts(); bindWeekDnD(); },
};

function trFitness() {
  const p = D.training.pmc;
  if (!p.series.length) return empty("Fitness & Freshness needs training history", p.reason || "Import workouts with heart rate to start");
  const rng = chipVal("pmc-range", "3m");
  const rows = sliceDays(p.series, rangeDays(rng));
  const fc = (D.training.forecast.series || []);
  const all = rows.concat(fc.map(f => Object.assign({ forecast: true }, f)));
  const dashFrom = rows.length - 1;
  const st = D.training.status;
  const ot = D.today.overtraining || {};
  const we = D.training.weekly_effort;
  const weeks = (we.weeks || []).filter(w => w.load !== null || w.partial);
  const cand = D.training.threshold_candidates || [];
  const prop = D.plans.pace_proposal;
  const statusTxt = { productive: "Fitness rising with manageable fatigue", maintaining: "Steady fitness", fatigued: "Fatigue well above fitness", overreaching: "Very high fatigue", detraining: "Fitness declining", calibrating: "Needs 42 days of history" };
  return `<div class="cols c21"><div class="stack"><div class="card">
      <div class="spread"><h3 style="margin:0">Fitness & Freshness</h3>${p.status === "calibrating" ? badge("Calibrating", "") : p.status === "partial" ? badge("Partial", "warn") : ""}</div>
      <div class="kpi-strip" style="margin:10px 0">${stat("Fitness", fmt.n(rows[rows.length - 1].ctl))}${stat("Fatigue", fmt.n(rows[rows.length - 1].atl))}${stat("Form", fmt.signed(rows[rows.length - 1].tsb, 0))}${stat("Ramp", isNum(st.ramp) ? fmt.signed(st.ramp, 1) + "/wk" : "—")}</div>
      ${chips("pmc-range", RANGES, rng)}
      ${chart({ id: "pmc", label: "Fitness and fatigue over time", x: all.map(r => r.date), h: 180, noX: true, legend: false,
        series: [{ name: "Fitness", color: "var(--info)", values: all.map(r => r.ctl), dashFrom, width: 2.6, area: true, areaOpacity: 0.16 },
          { name: "Fatigue", color: "var(--protein)", values: all.map(r => r.atl), dashFrom, width: 1.3 }],
        hatchFrom: fc.length ? dashFrom + 1 : null, hatchLabel: "Plan", fmtX: d => fmt.date(d, { day: "numeric", month: "short", year: "2-digit" }),
        fmtY: v => fmt.n(v, 1), zeroBase: true,
        tipExtra: i => { const r0 = all[i]; return r0.forecast ? `<div class="k">Projected from plan</div>` : `<div class="k">Load ${fmt.n(r0.load)} · form ${fmt.signed(r0.tsb, 0)}${r0.known ? "" : " · no data this day"}</div>`; },
        onPick: i => { const r0 = all[i]; if (!r0.forecast) dayActivitiesSheet(r0.date); } })}
      ${chart({ id: "pmc-form", label: "Form (training stress balance) over time", x: all.map(r => r.date), h: 96, legend: false,
        series: [{ name: "Form", color: "var(--ok)", values: all.map(r => r.tsb), dashFrom, width: 1.6, area: true, areaBase: 0, areaOpacity: 0.25 }],
        hatchFrom: fc.length ? dashFrom + 1 : null, hatchLabel: " ", refLines: [{ y: 0, color: "var(--line-2)" }], fmtX: d => fmt.date(d, { day: "numeric", month: "short", year: "2-digit" }), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.signed(v, 0) })}
      <div class="chart-legend"><span><i style="background:var(--info)"></i>Fitness</span><span><i style="background:var(--protein)"></i>Fatigue</span><span><i style="background:var(--ok)"></i>Form</span>${fc.length ? `<span><i style="background:repeating-linear-gradient(90deg,var(--text-2) 0 4px,transparent 4px 7px)"></i>Plan projection</span>` : ""}</div>
      <div class="chart-range">${esc(rangeLabel(rows))}</div>
      <p class="cap">Fitness = 42-day load average · Fatigue = 7-day · Form = yesterday's Fitness − Fatigue. Load is Banister TRIMP from heart rate${D.training.srpe && D.training.srpe.pairs ? "; RPE fallback calibrated on " + D.training.srpe.pairs + " sessions" : ""}.</p></div>
    <div class="card"><div class="spread"><h3 style="margin:0">Weekly effort</h3>${we.hint ? badge({ maintain: "Maintain", increase: "Room to increase", recover: "Recover" }[we.hint], we.hint === "recover" ? "warn" : "ok") : ""}</div>
      ${weeks.length ? chart({ id: "we", type: "bar", label: "Weekly training load with your typical range", x: weeks.map(w => w.week), h: 160, partialIndex: weeks.findIndex(w => w.partial),
        series: [{ name: "Weekly load", color: (i) => weeks[i].partial ? "var(--accent-2)" : "var(--accent)", values: weeks.map(w => w.load) }],
        band: we.band ? { low: we.band.low, high: we.band.high, color: "color-mix(in srgb, var(--accent) 16%, transparent)" } : null,
        fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.n(v) }) : empty(STR.noData)}
      ${we.band ? `<p class="cap">Shaded band: recency-weighted average of your last ${we.band.weeks} weeks ±15%. Current week is partial.</p>` : ""}</div></div>
    <div class="stack"><div class="card"><h3>Cardio status</h3><div class="stat"><span class="v" style="font-size:28px">${st.v ? esc(fmt.sport(st.v)) : "—"}</span></div><p class="small muted">${esc(statusTxt[st.v] || "")}</p>
      ${st.ramp_warning ? insightCard("Fitness ramping fast", `+${fmt.n(st.ramp, 1)} per week`, "action") : ""}
      ${ot.enabled ? `<div class="li" style="border:0"><div class="grow"><div class="t">Overtraining check</div><div class="s">HRV ${ot.evidence && isNum(ot.evidence.hrv_z_7d) ? (ot.evidence.hrv_z_7d < 0 ? "below" : "above") + " baseline (z " + fmt.n(ot.evidence.hrv_z_7d, 1) + ")" : "—"} · form ${ot.evidence && isNum(ot.evidence.tsb) ? fmt.n(ot.evidence.tsb) : "—"}${ot.note ? " · " + esc(ot.note) : ""}</div></div>${badge(ot.active ? "Warning" : "Clear", ot.active ? "bad" : "ok")}</div>` : `<p class="cap">Overtraining warning disabled in config</p>`}</div>
    ${prop ? `<div class="card"><h3>Threshold update suggested</h3><p class="small">${esc(prop.reason)}</p><div class="stats-grid">${stat("Current", fmt.pace(prop.current))}${stat("Proposed", fmt.pace(prop.proposed))}</div><p class="cap">Applied only when you confirm in profile.</p></div>` : ""}
    ${cand.length ? `<div class="card"><h3>Calibration candidates</h3><div class="list">${cand.slice(-3).reverse().map(c => `<div class="li"><div class="grow"><div class="t">${c.metric === "lthr" ? "LTHR " + c.value + " bpm" : "Threshold " + fmt.pace(c.value)}</div><div class="s">${esc(c.method)} · ${fmt.date(c.date)}</div></div><div class="r small">${isNum(c.delta) ? (c.metric === "lthr" ? fmt.signed(c.delta) : fmt.signed(c.delta) + " s") : "new"}</div></div>`).join("")}</div><p class="cap">${D.profile.auto_accept_thresholds ? "Auto-accept is on." : "Not applied: confirm in profile (auto-accept off)."}</p></div>` : ""}
    <a class="card chev row" href="#/training?tab=review">${icon("calendar")} <b>Weekly review</b></a><a class="card chev row" href="#/training?tab=recaps">${icon("records")} <b>Year in Sport</b></a></div></div>`;
}

function dayActivitiesSheet(date) {
  const acts = D.activities.list.filter(a => a.date === date);
  openSheet(fmt.dateLong(date), acts.length ? `<div class="list">${acts.map(activityRow).join("")}</div>` : `<p class="small muted">No activities this day</p>`);
}

function totalsRow(label, t, prev, unit) {
  const cur = t[unit] || 0, pv = prev ? prev[unit] || 0 : null;
  const d = pv ? (cur - pv) / pv * 100 : null;
  const f = unit === "distance_m" ? fmt.dist(cur) : unit === "duration_s" ? fmt.mins(cur) : unit === "elevation_gain_m" ? fmt.elev(cur) : fmt.n(cur);
  return stat(label, f, "", { d: isNum(d) ? deltaHtml(d, 0, "%", true) + `<span class="cap"> vs prior</span>` : `<span class="cap">no prior data</span>` });
}

function trLog() {
  const log = D.training.log;
  const view = chipVal("log-view", "calendar");
  const per = chipVal("log-period", "week");
  const fam = chipVal("log-fam", "all");
  const P0 = log[per];
  const t = (P0.totals[fam] || { distance_m: 0, duration_s: 0, elevation_gain_m: 0, load: 0, count: 0 });
  const prev = P0.prev_to_date[fam];
  const ly = P0.last_year_to_date ? P0.last_year_to_date[fam] : null;
  const head = `<div class="card"><div class="spread"><div>${seg("log-period", [["week", "Week"], ["month", "Month"], ["quarter", "Quarter"], ["year", "Year"]], per)}</div><span class="cap">${fmt.date(P0.start)} – ${fmt.date(P0.end)}${P0.partial ? " · to date" : ""}</span></div>
    <div style="margin:10px 0">${chips("log-fam", [["all", "All"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"], ["swim", "Swim"]], fam)}</div>
    <div class="stats-grid s4">${totalsRow("Distance", t, prev, "distance_m")}${totalsRow("Time", t, prev, "duration_s")}${totalsRow("Elevation", t, prev, "elevation_gain_m")}${totalsRow("Activities", t, prev, "count")}</div>
    <p class="cap">Compared with the same elapsed part of the previous ${per}${ly ? `; same period last year: ${fmt.dist(ly.distance_m)}, ${fmt.n(ly.count)} activities` : "; no data for last year yet"}.</p></div>`;
  let body;
  if (view === "calendar") {
    const weeks = log.weeks.slice().reverse();
    const maxLoad = Math.max(1, ...weeks.flatMap(w => w.days.flatMap(d => d.acts.map(a => a.load || 0))));
    body = `<div class="card"><div class="log-days-h"><span></span>${["M", "T", "W", "T", "F", "S", "S"].map(x => `<span>${x}</span>`).join("")}</div>
      ${weeks.map(w => `<div class="log-week"><div class="wk"><b>${fmt.dist(w.totals.distance_m, 0)}</b>${fmt.date(w.week)}</div>
      ${w.days.map(d => `<div class="log-day ${d.future ? "future" : ""}">${d.acts.filter(a => fam === "all" || a.family === fam).slice(0, 1).map(a => {
        const sz = 14 + 22 * Math.sqrt((a.load || 10) / maxLoad);
        return `<a href="#/activity/${encodeURIComponent(a.id)}" class="bubble" style="width:${sz}px;height:${sz}px;background:${sportColor(a.family)}" title="${esc(a.name || a.sport)} · ${a.distance_m ? fmt.dist(a.distance_m) : fmt.mins(a.duration_s)}" aria-label="${esc(a.name || a.sport)} ${fmt.date(d.date)}">${d.acts.length > 1 ? d.acts.length : ""}</a>`;
      }).join("")}</div>`).join("")}</div>`).join("")}
      <div class="legend" style="margin-top:8px">${["run", "ride", "strength", "walk", "swim"].map(f => `<span><i style="background:${sportColor(f)};border-radius:50%"></i>${fmt.sport(f)}</span>`).join("")}<span>Size = load</span></div></div>`;
  } else {
    const rows = D.activities.list.filter(a => fam === "all" || a.family === fam).slice(0, 80);
    body = `<div class="card tight"><div class="list">${rows.map(activityRow).join("") || empty(STR.noData)}</div></div>`;
  }
  const months = log.months;
  const mchart = months.length ? `<div class="card"><h3>Monthly ${fam === "all" ? "distance" : fmt.sport(fam) + " distance"}</h3>${chart({ id: "months", type: "bar", label: "Monthly distance", x: months.map(m => m.month), h: 150,
    series: [{ name: "Distance", color: "var(--accent)", values: months.map(m => (fam === "all" ? m.totals : (fam === "run" ? m.run : null) || m.totals).distance_m / (IMPERIAL ? 1609.344 : 1000)) }],
    fmtX: m => fmt.date(m + "-15", { month: "long", year: "numeric" }), fmtXAxis: m => fmt.date(m + "-15", { month: "short" }), fmtY: v => fmt.n(v, 0) + " " + fmt.distUnit() })}</div>` : "";
  return `<div class="stack">${head}<div class="spread">${seg("log-view", [["calendar", "Calendar"], ["list", "List"]], view)}<a class="small" style="color:var(--accent);font-weight:600" href="#/training?tab=plan">Plan ›</a></div>${body}${mchart}</div>`;
}

function trProgress() {
  const range = chipVal("prog-range", "3m");
  const fam = chipVal("prog-fam", "all");
  const metric = chipVal("prog-metric", "distance_m");
  const P0 = D.training.progress[range === "24m" ? "12m" : range];
  if (!P0) return empty(STR.noData);
  const s = P0.series[fam] || P0.series.all;
  if (!s) return empty("No activities in this period");
  const conv = v => metric === "distance_m" ? v / (IMPERIAL ? 1609.344 : 1000) : metric === "duration_s" ? v / 3600 : metric === "elevation_gain_m" ? (IMPERIAL ? v * 3.28084 : v) : v;
  const unit = metric === "distance_m" ? fmt.distUnit() : metric === "duration_s" ? "h" : metric === "elevation_gain_m" ? (IMPERIAL ? "ft" : "m") : "";
  let a = 0, b = 0;
  const cur = s.current.map(r => (a += conv(r[metric]), a)), pri = s.prior.map(r => (b += conv(r[metric]), b));
  const tot = s.total[metric], ptot = s.prior_total[metric], dp = s.delta_pct[metric];
  const ft = v => metric === "distance_m" ? fmt.dist(v) : metric === "duration_s" ? fmt.mins(v) : metric === "elevation_gain_m" ? fmt.elev(v) : fmt.n(v);
  return `<div class="card"><div style="margin-bottom:8px">${chips("prog-fam", [["all", "All sports"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"]], fam)}</div>
    <div style="margin-bottom:8px">${chips("prog-metric", [["distance_m", "Distance"], ["duration_s", "Time"], ["elevation_gain_m", "Elevation"], ["load", "Load"], ["count", "Activities"]], metric, "accent")}</div>
    <div class="spread" style="margin:10px 0"><div><div class="cap">Total ${esc(fmt.sport(metric.replace(/_m$|_s$/, "").replace("elevation_gain", "elevation")))}</div><div class="stat"><span class="v">${ft(tot)} ${isNum(dp) ? deltaHtml(dp, 0, "%", true) : ""}</span></div><div class="cap" style="color:var(--accent)">● ${fmt.date(P0.start)} – today</div></div>
      <div style="text-align:right"><div class="stat"><span class="v">${ft(ptot)}</span></div><div class="cap" style="color:var(--prior)">● prior ${P0.weeks} weeks${P0.prior_complete ? "" : " (partial history)"}</div></div></div>
    ${chart({ id: "prog", label: "Cumulative progress vs prior period", x: s.current.map(r => r.week), h: 200,
      series: [{ name: "Current", color: "var(--accent)", values: cur, area: true, dots: cur.length < 20 }, { name: "Prior period", color: "var(--prior)", values: pri, dots: pri.length < 20 }],
      fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.n(v, unit === "h" ? 1 : 0) + (unit ? " " + unit : "") })}
    <div style="margin-top:10px">${chips("prog-range", [["1m", "1 month"], ["3m", "3 months"], ["6m", "6 months"], ["12m", "1 year"]], range)}</div>
    <p class="cap">${isNum(dp) ? `You've logged ${fmt.n(Math.abs(dp))}% ${dp >= 0 ? "more" : "less"} than the prior ${P0.weeks} weeks.` : "No prior data to compare."}</p></div>`;
}

/* ---------------- plan ---------------- */
function weekGrid(wk) {
  const today = D.meta.build_date;
  return `<div class="weekgrid" data-weekgrid>${wk.days.map(d => `<div class="dh ${d === today ? "today" : ""}">${fmt.dow(d).slice(0, 2)}<b>${fmt.date(d, { day: "numeric" })}</b></div>`).join("")}
    ${wk.days.map(d => `<div class="col" data-drop="${d}">${wk.sessions.filter(s => s.date === d).map(s => {
      const cls = s.type === "REST" ? "rest" : s.compliance || "planned";
      const load = isNum(s.actual_load) ? `L${fmt.n(s.actual_load)}${isNum(s.planned_load) ? ` <span class="faint">(${fmt.n(s.planned_load)})</span>` : ""}` : isNum(s.planned_load) ? `<span class="faint">L${fmt.n(s.planned_load)}</span>` : "";
      const dur = s.actual_duration_s || s.duration_s;
      return `<button class="wtile ${cls}" ${s.origin === "plan" && d >= today ? `draggable="true" data-drag="${esc(s.id)}"` : ""} data-open="session" data-arg="${esc(s.id)}" aria-label="${esc(s.label || s.type)} ${esc(fmt.sport(cls))}">
        <b>${esc(s.type === "NPU" ? "NPU" : s.type)}</b>${s.type !== "REST" ? `<span>${load}</span><br><span>${dur ? fmt.mins(dur) : ""}</span>` : ""}<div class="tl">${esc(fmt.sport(cls === "planned" ? "" : cls))}</div></button>`;
    }).join("")}</div>`).join("")}</div>`;
}
function weekHeader(h) {
  return `<div class="week-head"><span></span><span class="h">Sessions</span><span class="h">Duration</span><span class="h">Load</span>
    <span class="small">Actual</span><span class="v a">${h.actual.sessions}</span><span class="v a">${fmt.dur(h.actual.duration_s)}</span><span class="v a">${fmt.n(h.actual.load)}</span>
    <span class="small">Planned</span><span class="v">${h.planned.sessions}</span><span class="v">${fmt.dur(h.planned.duration_s)}</span><span class="v">${fmt.n(h.planned.load)}</span></div>`;
}
function bindWeekDnD() {
  $$("[data-drag]").forEach(el => {
    el.addEventListener("dragstart", e => { e.dataTransfer.setData("text/plain", el.dataset.drag); el.style.opacity = ".5"; });
    el.addEventListener("dragend", () => { el.style.opacity = ""; });
  });
  $$("[data-drop]").forEach(col => {
    col.addEventListener("dragover", e => { e.preventDefault(); col.style.outline = "1px dashed var(--accent)"; });
    col.addEventListener("dragleave", () => { col.style.outline = ""; });
    col.addEventListener("drop", async e => {
      e.preventDefault(); col.style.outline = "";
      const id = e.dataTransfer.getData("text/plain");
      await moveSession(id, col.dataset.drop);
    });
  });
}
async function moveSession(id, date) {
  try { await api("PATCH", "entries/plans.sessions/" + encodeURIComponent(id), { date }); toast("Moved · rebuilding"); setTimeout(() => location.reload(), 900); }
  catch (err) { toast(err.message); }
}
function trPlan() {
  const p = D.plans;
  const which = chipVal("plan-week", "this");
  const wk = which === "next" ? p.next_week : which === "last" ? p.last_week : p.this_week;
  const races = p.races.races;
  const inst = p.instant;
  const cal = p.calendar;
  return `<div class="cols c21"><div class="stack"><div class="card">
      <div class="spread" style="margin-bottom:10px"><h3 style="margin:0">${fmt.date(wk.days[0])} – ${fmt.date(wk.days[6])}</h3>${seg("plan-week", [["last", "Last"], ["this", "This week"], ["next", "Next"]], which)}</div>
      ${weekHeader(wk.header)}<div style="height:10px"></div>${weekGrid(wk)}
      <div class="legend" style="margin-top:10px"><span><i style="border:2px solid var(--ok)"></i>As planned</span><span><i style="border:2px solid var(--warn)"></i>Partial</span><span><i style="border:2px dashed var(--bad)"></i>Missed</span><span><i style="border:2px solid var(--text-3)"></i>Unplanned</span></div>
      <p class="cap">${isNum(wk.header.compliance_pct) ? `Compliance ${wk.header.compliance_pct}% so far. ` : ""}Drag a planned session to another day (desktop) or open it for alternatives. ${p.has_explicit_plan ? "" : "Sessions come from your weekly template."}</p>${offlineNote()}</div>
    ${p.adaptations.length ? `<div class="card"><h3>Suggested changes</h3>${p.adaptations.map(a => insightCard(`${fmt.dow(a.date)}: ${adaptText(a)}`, a.reason, "action")).join("")}<p class="cap">Originals stay visible; nothing changes until you accept.</p></div>` : ""}
    ${p.conflicts.length ? `<div class="card"><h3>Calendar conflicts</h3><div class="list">${p.conflicts.map(c => `<div class="li"><div class="grow"><div class="t">${fmt.dow(c.date)} ${fmt.date(c.date)}</div><div class="s">${esc(c.event || "")} · ${esc(c.reason)}</div></div></div>`).join("")}</div></div>` : ""}
    <div class="card"><h3>Upcoming sessions</h3>${p.upcoming.length ? `<div class="list">${p.upcoming.map(s => `<button class="li" data-open="session" data-arg="${esc(s.id)}"><span class="icon-dot" style="color:${sportColor(s.sport === "strength" ? "strength" : "run")}">${sportIcon(s.sport === "strength" ? "strength" : "run")}</span><div class="grow"><div class="t">${esc(s.title || s.label)}</div><div class="s">${fmt.dow(s.date)} ${fmt.date(s.date)} · ${esc(s.label || s.type)}${s.origin === "template" ? " · template" : ""}</div></div><div class="r small">${s.duration_s ? fmt.mins(s.duration_s) : ""}</div></button>`).join("")}</div>` : empty(STR.noPlan)}</div>
    <div class="card"><h3>Training calendar</h3>${monthGrid(cal)}</div></div>
    <div class="stack">
    <div class="card"><h3>Season</h3>${races.length ? `<div class="list">${races.map(r => `<div class="li"><span class="badge ${r.priority === "A" ? "accent" : r.priority === "B" ? "info" : ""}">${esc(r.priority || "B")}</span><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })}${r.distance_m ? " · " + fmt.dist(r.distance_m) : ""} · ${esc(fmt.sport(r.phase))}</div></div><div class="r">${r.days_to}<div class="cap">days</div></div></div>`).join("")}</div>
      <p class="cap">A races get a ${races.find(r => r.priority === "A") ? races.find(r => r.priority === "A").taper_days : 14}-day taper; C races none.</p>` : `<p class="small muted">No target race · ${p.races.mode === "maintain" ? "train-to-maintain mode" : "add races in plans.json"}</p>`}
      ${p.plans.map(pl => `<div style="margin-top:10px"><b>${esc(pl.name)}</b><div class="cap">${esc(pl.goal || "")}</div>${(pl.phases || []).map(ph => `<div class="spread small" style="margin-top:6px"><span>${esc(ph.name)} <span class="faint">${esc(ph.focus || "")}</span></span><span class="muted">${fmt.date(ph.start)}–${fmt.date(ph.end)}</span></div>`).join("")}</div>`).join("")}</div>
    <div class="card"><h3>Instant workouts</h3>${inst.status === "ok" ? `<div class="list">${inst.options.map(o => `<div class="li"><div class="grow"><div class="t">${esc(o.title)} <span class="tag">${esc(o.mode)}</span></div><div class="s">${esc(o.why)}${o.route ? " · " + esc(o.route.name) : ""}</div></div><div class="r small">${fmt.mins(o.duration_s)}</div></div>`).join("")}</div>` : `<p class="small muted">Needs ${inst.needed} runs in the last 4 weeks (have ${inst.have})</p>`}</div>
    <div class="card"><h3>Routines</h3>${p.routines.length ? `<div class="list">${p.routines.map(rt => `<button class="li" data-open="routine" data-arg="${esc(rt.id)}"><div class="grow"><div class="t">${esc(rt.name)}</div><div class="s">${esc(fmt.sport(rt.sport))} · ${fmt.mins(rt.total_duration_s)}${rt.guiding_metric ? " · guide by " + esc(rt.guiding_metric) : ""}</div></div></button>`).join("")}</div>` : empty("No routines yet")}</div>
    </div></div>`;
}
AG.sheets.routine = function (id) {
  const rt = D.plans.routines.find(r => r.id === id);
  if (!rt) return;
  openSheet(rt.name, `${stepList(rt.steps)}${sectionTitle("Apple Watch export")}<p class="small muted">${esc(rt.watch_export.note)}</p>
    <pre style="white-space:pre-wrap;font-size:11px;background:var(--surface-2);padding:10px;border-radius:10px;max-height:240px;overflow:auto">${esc(JSON.stringify(rt.watch_export, null, 1))}</pre>
    <p class="cap">${STR.companion}</p>`);
};
function monthGrid(cal) {
  const days = cal.days;
  const today = D.meta.build_date;
  const start = days.findIndex(d => d.date.slice(0, 7) === today.slice(0, 7));
  const month = days.filter(d => d.date.slice(0, 7) === today.slice(0, 7));
  const first = new Date(month[0].date + "T12:00:00Z").getUTCDay();
  const lead = (first + 6) % 7;
  const cells = [];
  for (let i = 0; i < lead; i++) cells.push(`<div></div>`);
  month.forEach(d => {
    const dot = style => `<i style="width:6px;height:6px;border-radius:50%;display:inline-block;${style}"></i>`;
    const dots = d.acts.map(a => dot(`background:${sportColor(a.family)}`)).join("") +
      d.sessions.filter(s => !s.workout_id && s.type !== "REST").map(() => dot("border:1.5px solid var(--text-3)")).join("") +
      d.events.map(() => dot("background:var(--info)")).join("");
    cells.push(`<button data-open="calday" data-arg="${d.date}" style="padding:6px 2px;border-radius:8px;${d.date === today ? "background:var(--surface-3);" : ""}text-align:center;min-height:44px" aria-label="${fmt.dateLong(d.date)}"><div class="small" style="font-weight:${d.date === today ? 800 : 500}">${+d.date.slice(8)}</div><div style="display:flex;gap:2px;justify-content:center;flex-wrap:wrap;margin-top:3px">${dots}</div></button>`);
  });
  return `<div class="cap" style="margin-bottom:6px">${fmt.date(today, { month: "long", year: "numeric" })}</div><div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px">${["M", "T", "W", "T", "F", "S", "S"].map(x => `<div class="cap" style="text-align:center">${x}</div>`).join("")}${cells.join("")}</div>
    <div class="legend" style="margin-top:8px"><span><i style="background:var(--run);border-radius:50%"></i>Done</span><span><i style="border:1.5px solid var(--text-3);border-radius:50%"></i>Planned</span><span><i style="background:var(--info);border-radius:50%"></i>Event</span></div>`;
}
AG.sheets.calday = function (date) {
  const d = D.plans.calendar.days.find(x => x.date === date);
  if (!d) return;
  openSheet(fmt.dateLong(date), `${d.acts.length ? sectionTitle("Activities") + `<div class="list">${d.acts.map(a => `<a class="li" href="#/activity/${encodeURIComponent(a.id)}"><div class="grow"><div class="t">${esc(a.name || fmt.sport(a.sport))}</div><div class="s">${fmt.mins(a.duration_s)}${a.distance_m ? " · " + fmt.dist(a.distance_m) : ""}${a.planned ? " · planned" : " · unplanned"}</div></div></a>`).join("")}</div>` : ""}
    ${d.sessions.length ? sectionTitle("Planned") + `<div class="list">${d.sessions.map(s => `<button class="li" data-open="session" data-arg="${esc(s.id)}"><div class="grow"><div class="t">${esc(s.title || s.label)}</div><div class="s">${esc(fmt.sport(s.compliance || ""))}</div></div></button>`).join("")}</div>` : ""}
    ${d.events.length ? sectionTitle("Calendar") + `<div class="list">${d.events.map(e => `<div class="li"><div class="grow"><div class="t">${esc(e.title)}</div><div class="s">${fmt.time(e.start)}–${fmt.time(e.end)}</div></div></div>`).join("")}</div>` : ""}
    ${!d.acts.length && !d.sessions.length && !d.events.length ? `<p class="small muted">Nothing on this day</p>` : ""}`);
};

function trZones() {
  const hz = D.training.hr_zones, pz = D.training.pace_zones, zd = D.training.zone_distribution;
  const zc = i => `var(--z${i + 1})`;
  return `<div class="cols"><div class="stack"><div class="card"><h3>Heart-rate zones</h3>${hz.zones ? `<table class="tbl"><tr><th>Zone</th><th class="r">Range (bpm)</th></tr>${hz.zones.map((z, i) => `<tr><td><span style="color:${zc(i)}">●</span> ${z.name}</td><td class="r">${z.low}–${z.high}</td></tr>`).join("")}</table>
      <p class="cap">${esc(hz.model)} from ${esc(fmt.sport(hz.basis))} ${hz.basis_value || ""}${hz.method ? " · " + esc(hz.method) : ""}${hz.date ? " · " + fmt.date(hz.date, { day: "numeric", month: "short", year: "numeric" }) : ""}. No age-based formula is used.</p>` : empty(STR.hrMax, hz.reason)}</div>
    <div class="card"><h3>Pace zones</h3>${pz.zones ? `<table class="tbl"><tr><th>Zone</th><th class="r">Pace</th></tr>${pz.zones.map((z, i) => `<tr><td><span style="color:${zc(i)}">●</span> ${z.name}</td><td class="r">${z.slow ? fmt.pace(z.slow, false) : "slower"} – ${fmt.pace(z.fast)}</td></tr>`).join("")}</table><p class="cap">From threshold pace ${fmt.pace(pz.basis_value)}${pz.method ? " · " + esc(pz.method) : ""}.</p>` : empty("Threshold pace not configured", pz.reason)}</div></div>
    <div class="card"><h3>Time in zones by week</h3>${zd.status === "ok" ? chart({ id: "zd", type: "bar", stacked: true, label: "Weekly time in heart-rate zones", x: zd.weeks.map(w => w.week), h: 200,
      series: zd.zones.map((z, i) => ({ name: z, color: zc(i), values: zd.weeks.map(w => w.s[i] / 60) })), fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.hm(v), fmtYAxis: v => fmt.n(v / 60, 0) + "h" }) : empty(STR.hrMax, zd.reason)}</div></div>`;
}

function trRecords() {
  const rec = D.records, preds = D.training.predictions;
  const effortRows = (rec.run || []).map(r => `<button class="li" data-open="efforts" data-arg="${r.distance_m}"><div class="grow"><div class="t">${fmt.distLabel(r.distance_m)}</div><div class="s">${fmt.date(r.best.date, { day: "numeric", month: "short", year: "numeric" })} · ${fmt.pace(r.best.pace_s_per_km)}</div></div><div class="r">${fmt.dur(r.best.time_s)}</div></button>`).join("");
  const lg = rec.longest || {};
  return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Race predictions</h3>${badge("Estimate", "est")}</div>
      ${preds.length ? `<div class="grid g2" style="margin-top:10px">${preds.map(p => `<div class="card flat tight"><div class="tag">${fmt.distLabel(p.distance_m)}</div><div class="stat"><span class="v">${fmt.dur(p.time_s)}</span></div><div class="cap">${fmt.pace(p.pace_s_per_km)}</div></div>`).join("")}</div>
      <p class="cap">${esc(preds[0].method)} from your ${fmt.distLabel(preds[0].source.distance_m)} of ${fmt.dur(preds[0].source.time_s)} on ${fmt.date(preds[0].source.date)} (nearest-distance effort in the last 120 days).</p>` : empty("No qualifying efforts in the last 120 days", "Run 3 km or more with distance samples")}</div>
    <div class="card"><h3>Running best efforts</h3>${effortRows ? `<div class="list">${effortRows}</div>` : empty(STR.noData)}</div></div>
    <div class="stack"><div class="card"><h3>Longest</h3><div class="list">${Object.entries(lg).map(([f, v]) => `<a class="li" href="#/activity/${encodeURIComponent(v.workout_id)}"><span class="icon-dot" style="color:${sportColor(f)}">${sportIcon(f)}</span><div class="grow"><div class="t">${fmt.sport(f)}</div><div class="s">${fmt.date(v.date, { day: "numeric", month: "short", year: "numeric" })}</div></div><div class="r">${fmt.dist(v.distance_m)}</div></a>`).join("") || empty(STR.noData)}</div></div>
    <div class="card"><h3>Cycling & swimming</h3>${(rec.ride || []).length || (rec.swim || []).length ? `<div class="list">${[].concat(rec.ride || [], rec.swim || []).map(r => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(r.distance_m)}</div></div><div class="r">${fmt.dur(r.best.time_s)}</div></div>`).join("")}</div>` : `<p class="small muted">No ride or swim efforts yet</p>`}
      ${rec.power ? sectionTitle("Best power") + `<div class="list">${rec.power.map(p => `<div class="li"><div class="grow"><div class="t">${durLabel(p.s)}</div></div><div class="r">${p.v} W</div></div>`).join("")}</div>` : `<p class="cap">${STR.noPower}: power curve omitted.</p>`}</div>
    <a class="card chev row" href="#/strength?tab=records">${icon("strength")} <b>Strength records</b></a></div></div>`;
}
AG.sheets.efforts = function (dist) {
  const r = (D.records.run || []).find(x => String(x.distance_m) === String(dist));
  if (!r) return;
  openSheet(fmt.distLabel(r.distance_m) + " · top efforts", `<table class="tbl"><tr><th>#</th><th>Date</th><th class="r">Time</th><th class="r">Pace</th></tr>${r.top.map((e, i) => `<tr><td>${i + 1}</td><td><a href="#/activity/${encodeURIComponent(e.workout_id)}">${fmt.date(e.date, { day: "numeric", month: "short", year: "numeric" })}</a></td><td class="r">${fmt.dur(e.time_s)}</td><td class="r">${fmt.pace(e.pace_s_per_km)}</td></tr>`).join("")}</table><p class="cap">Ranks within your own history only.</p>`);
};

function recapCard(y, big) {
  const run = (y.totals || {}).run || {};
  const all = Object.values(y.totals || {}).reduce((a, t) => ({ d: a.d + (t.distance_m || 0), s: a.s + (t.duration_s || 0), e: a.e + (t.elevation_gain_m || 0) }), { d: 0, s: 0, e: 0 });
  return `<div class="card"><div class="spread"><h3 style="margin:0">${esc(y.label)}</h3>${y.partial ? badge("To date", "info") : ""}</div>
    <div class="stats-grid ${big ? "s4" : ""}" style="margin-top:10px">${stat("Activities", fmt.n(y.activities))}${stat("Distance", fmt.dist(all.d, 0))}${stat("Time", fmt.mins(all.s))}${stat("Elevation", fmt.elev(all.e))}
      ${stat("Active weeks", `${y.active_weeks}/${y.total_weeks}`)}${stat("PRs", fmt.n(y.prs))}${stat("Avg sleep", isNum(y.avg_sleep_min) ? fmt.hm(y.avg_sleep_min) : "—")}${stat("Avg recovery", isNum(y.avg_recovery) ? y.avg_recovery + "%" : "—")}</div>
    ${big ? `${y.longest ? `<p class="small" style="margin-top:12px">Longest: <b>${fmt.dist(y.longest.distance_m)}</b> · ${esc(y.longest.name || "")} · ${fmt.date(y.longest.date)}</p>` : ""}
      ${y.fastest.length ? `<div class="list">${y.fastest.map(f => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(f.distance_m)}</div><div class="s">${fmt.date(f.date)}</div></div><div class="r">${fmt.dur(f.time_s)} ${f.pr ? badge("PR", "accent") : ""}</div></div>`).join("")}</div>` : ""}
      ${y.best_month ? `<p class="small">Best month: <b>${fmt.date(y.best_month.month + "-15", { month: "long" })}</b> (load ${fmt.n(y.best_month.load)})${y.quietest_month ? ` · quietest: ${fmt.date(y.quietest_month.month + "-15", { month: "long" })}` : ""}</p>` : ""}
      ${isNum(y.weight_change_kg) ? `<p class="small">Weight change: ${fmt.signed(IMPERIAL ? y.weight_change_kg * 2.20462 : y.weight_change_kg, 1)} ${fmt.wUnit()}</p>` : ""}
      ${y.goals ? `<div style="margin-top:8px">${y.goals.map(g => `<div class="spread small"><span>${esc(g.title)}</span>${goalStatusBadge(g.status)}</div>`).join("")}</div>` : ""}` : ""}</div>`;
}
function trRecaps() {
  const R = D.recaps;
  if (!R.years.length) return empty("Year in Sport appears after your first imported activities");
  return `<div class="cols"><div class="stack">${sectionTitle("Year in Sport")}${R.years.slice().reverse().map(y => recapCard(y, true)).join("")}</div>
    <div class="stack">${sectionTitle("Month in Sport")}${R.months.map(m => recapCard(m, false)).join("")}</div></div>`;
}

function trReview() {
  const w = D.weekly_review;
  const n = w.numbers;
  return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Week of ${fmt.date(w.week_start)}</h3>${w.complete ? badge("Complete", "ok") : badge("Partial", "warn")}</div>
      <div class="stats-grid s3" style="margin-top:10px">${stat("Distance", n.totals ? fmt.dist(n.totals.distance_m) : "—")}${stat("Time", n.totals ? fmt.mins(n.totals.duration_s) : "—")}${stat("Load", fmt.n(n.load_sum))}
      ${stat("Sleep avg", isNum(n.sleep_avg_min) ? fmt.hm(n.sleep_avg_min) : "—")}${stat("Recovery avg", isNum(n.recovery_avg) ? n.recovery_avg + "%" : "—")}${stat("Weight", isNum(n.weight_median_kg) ? fmt.kg(n.weight_median_kg) : "—")}
      ${stat("Protein days", isNum(n.protein_days_hit) ? `${n.protein_days_hit}/${n.protein_days_logged}` : "—")}${stat("Compliance", isNum(w.compliance_pct) ? w.compliance_pct + "%" : "—")}${stat("Status", w.cardio_status && w.cardio_status.v ? esc(fmt.sport(w.cardio_status.v)) : "—")}</div></div>
    <div class="card"><h3>Four-week log</h3><table class="tbl"><tr><th>Week</th><th class="r">Distance</th><th class="r">Time</th><th class="r">Load</th></tr>${w.four_week_log.map(x => `<tr><td>${fmt.date(x.week)}</td><td class="r">${fmt.dist(x.totals.distance_m)}</td><td class="r">${fmt.mins(x.totals.duration_s)}</td><td class="r">${fmt.n(x.totals.load)}</td></tr>`).join("")}</table></div></div>
    <div class="stack"><div class="card"><h3>Goal trajectories</h3>${w.goals.length ? w.goals.map(g => `<div class="spread small" style="padding:6px 0"><span>${esc(g.title)}</span><span>${isNum(g.progress_pct) ? fmt.n(g.progress_pct) + "% " : ""}${goalStatusBadge(g.status)}</span></div>`).join("") : empty(STR.noGoals)}</div>
    <div class="card"><h3>Next week</h3>${w.next_week_intent.length ? `<div class="list">${w.next_week_intent.map(s => `<div class="li"><div class="grow"><div class="t">${esc(s.title || s.type)}</div><div class="s">${fmt.dow(s.date)} ${fmt.date(s.date)}</div></div><span class="tag">${esc(s.type)}</span></div>`).join("")}</div>` : empty(STR.noPlan)}</div>
    <p class="cap">Steve reads the same data from dist/weekly_review.json every Monday.</p></div></div>`;
}
