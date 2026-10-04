/* Training: fitness/freshness, training log, progress, plan & calendar, zones, records, recaps, weekly review */
"use strict";

const TRAINING_TABS = [["fitness", "Fitness"], ["plan", "Plan"], ["log", "Log"], ["progress", "Progress"], ["records", "Records"], ["zones", "Zones"]];

AG.screens.training = {
  title: "Training",
  render(r) {
    const tab = r.params.tab || chipVal("training-tab", "fitness");
    if (r.params.tab) uiSet("chip:training-tab", r.params.tab);
    if (tab === "review" || tab === "recaps") { location.replace("#/" + tab); return ""; }
    const body = { fitness: trFitness, log: trLog, progress: trProgress, plan: trPlan, zones: trZones, records: trRecords }[tab] || trFitness;
    return `${tabs("training-tab", TRAINING_TABS, tab)}${body()}`;
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
  const pmcAbout = `Fitness is your 42-day load average and Fatigue your 7-day average. Form is yesterday's Fitness minus Fatigue. Load is Banister TRIMP from heart rate${D.training.srpe && D.training.srpe.pairs ? ", with an RPE fallback calibrated on " + D.training.srpe.pairs + " sessions" : ""}. The hatched area projects your planned sessions.`;
  const cands = [];
  cand.slice().reverse().forEach(c => { const k = c.metric + ":" + c.value; const hit = cands.find(x => x.k === k); if (hit) hit.n++; else cands.push({ k, c, n: 1 }); });
  return `<div class="cols c21"><div class="stack"><div class="card">
      ${cardHead("Fitness & freshness", `${p.status === "calibrating" ? badge("Calibrating", "est") : p.status === "partial" ? badge("Partial", "warn") : ""}${seg("pmc-range", RANGES, rng)}`, pmcAbout)}
      <div class="stats-grid s4" style="margin-bottom:12px">${stat("Fitness", fmt.n(rows[rows.length - 1].ctl))}${stat("Fatigue", fmt.n(rows[rows.length - 1].atl))}${stat("Form", fmt.signed(rows[rows.length - 1].tsb, 0))}${stat("Ramp", isNum(st.ramp) ? fmt.signed(st.ramp, 1) : "—", "/wk")}</div>
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
      <div class="chart-range">${esc(rangeLabel(rows))}</div></div>
    <div class="card">${cardHead("Weekly effort", we.hint ? badge({ maintain: "Maintain", increase: "Room to build", recover: "Ease off" }[we.hint], we.hint === "recover" ? "warn" : "ok") : "", we.band ? `The shaded band is the recency-weighted average of your last ${we.band.weeks} weeks, ±15%. The current week is partial.` : "")}
      ${weeks.length ? chart({ id: "we", type: "bar", label: "Weekly training load with your typical range", x: weeks.map(w => w.week), h: 160, partialIndex: weeks.findIndex(w => w.partial),
        series: [{ name: "Weekly load", color: (i) => weeks[i].partial ? "var(--accent-2)" : "var(--accent)", values: weeks.map(w => w.load) }],
        band: we.band ? { low: we.band.low, high: we.band.high, color: "color-mix(in srgb, var(--accent) 16%, transparent)" } : null,
        fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.n(v) }) : empty(STR.noData)}
</div></div>
    <div class="stack"><div class="card">${cardHead("Cardio status")}<div class="stat"><span class="v" style="font-size:28px">${st.v ? esc(fmt.sport(st.v)) : "—"}</span><span class="cap">${esc(statusTxt[st.v] || "")}</span></div>
      ${st.ramp_warning ? `<div class="suggest" style="margin-top:12px"><div class="grow"><b>Fitness ramping fast</b><span>+${fmt.n(st.ramp, 1)} per week</span></div></div>` : ""}
      ${ot.enabled ? `<div class="li" style="border:0;padding-bottom:0;margin-top:8px"><div class="grow"><div class="t">Overtraining check</div><div class="s">HRV ${ot.evidence && isNum(ot.evidence.hrv_z_7d) ? (ot.evidence.hrv_z_7d < 0 ? "below" : "above") + " baseline" : "—"} · form ${ot.evidence && isNum(ot.evidence.tsb) ? fmt.n(ot.evidence.tsb) : "—"}</div></div>${badge(ot.active ? "Warning" : "Clear", ot.active ? "bad" : "ok")}</div>` : ""}</div>
    ${prop || cands.length ? `<div class="card">${cardHead("Threshold pace", "", `${prop ? esc(prop.reason) + ". " : ""}Test efforts propose a new threshold. ${D.profile.auto_accept_thresholds ? "Auto-accept is on." : "Nothing changes until you accept."}`)}
      ${prop ? `<div class="stats-grid">${stat("Current", fmt.pace(prop.current, false), fmt.paceUnit())}${stat("Suggested", fmt.pace(prop.proposed, false), fmt.paceUnit())}</div>${AG.online ? `<div class="actions"><button class="btn sm" data-thr-metric="${esc(prop.metric)}" data-thr-value="${prop.proposed}">Accept</button></div>` : ""}` : ""}
      ${cands.length ? `<div class="list" style="margin-top:${prop ? 12 : 0}px">${cands.slice(0, 3).map(({ c, n }) => `<div class="li"><div class="grow"><div class="t">${c.metric === "lthr" ? "LTHR " + c.value + " bpm" : fmt.pace(c.value)}</div><div class="s">From ${n > 1 ? n + " tests · latest " : "a test on "}${fmt.date(c.date)}</div></div><div class="r small">${isNum(c.delta) ? (c.metric === "lthr" ? fmt.signed(c.delta) : fmt.signed(c.delta) + " s") : "New"}</div>${AG.online && !c.applied ? `<button class="btn sm secondary" data-thr-metric="${esc(c.metric)}" data-thr-value="${c.value}">Accept</button>` : ""}</div>`).join("")}</div>` : ""}</div>` : ""}
    <div class="card tight"><div class="list"><a class="li chev" href="#/review"><span class="icon-dot">${icon("calendar")}</span><div class="grow"><div class="t">Weekly review</div></div></a><a class="li chev" href="#/recaps"><span class="icon-dot">${icon("records")}</span><div class="grow"><div class="t">Year in Sport</div></div></a></div></div></div></div>`;
}

document.addEventListener("click", e => {
  const b = e.target.closest("[data-thr-metric]");
  if (b) act("threshold.accept", { metric: b.dataset.thrMetric, value: +b.dataset.thrValue }, "Threshold updated").catch(() => {});
});
function dayActivitiesSheet(date) {
  const acts = D.activities.list.filter(a => a.date === date);
  openSheet(fmt.dateLong(date), acts.length ? `<div class="list">${acts.map(activityRow).join("")}</div>` : `<p class="small muted">No activities this day</p>`);
}

function totalsRow(label, t, prev, unit) {
  const cur = t[unit] || 0, pv = prev ? prev[unit] || 0 : null;
  const d = pv ? (cur - pv) / pv * 100 : null;
  const f = unit === "distance_m" ? fmt.dist(cur) : unit === "duration_s" ? fmt.mins(cur) : unit === "elevation_gain_m" ? fmt.elev(cur) : fmt.n(cur);
  return stat(label, f, "", { d: isNum(d) && d !== 0 ? deltaHtml(d, 0, "%", true) : "" });
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
  const head = `<div class="card">${cardHead(`${fmt.date(P0.start)} – ${fmt.date(P0.end)}`, seg("log-period", [["week", "Week"], ["month", "Month"], ["quarter", "Quarter"], ["year", "Year"]], per), `Changes compare with the same elapsed part of the previous ${per}${ly ? `. Same period last year: ${fmt.dist(ly.distance_m)}, ${fmt.n(ly.count)} activities` : ""}.`)}
    <div style="margin-bottom:16px">${chips("log-fam", [["all", "All"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"], ["swim", "Swim"]], fam)}</div>
    <div class="stats-grid s4">${totalsRow("Distance", t, prev, "distance_m")}${totalsRow("Time", t, prev, "duration_s")}${totalsRow("Elevation", t, prev, "elevation_gain_m")}${totalsRow("Activities", t, prev, "count")}</div></div>`;
  let body;
  if (view === "calendar") {
    const weeks = log.weeks.slice().reverse();
    const maxLoad = Math.max(1, ...weeks.flatMap(w => w.days.flatMap(d => d.acts.map(a => a.load || 0))));
    body = `<div class="card">${cardHead("Training log", seg("log-view", [["calendar", "Calendar"], ["list", "List"]], view))}<div class="log-days-h"><span></span>${["M", "T", "W", "T", "F", "S", "S"].map(x => `<span>${x}</span>`).join("")}</div>
      ${weeks.map(w => `<div class="log-week"><div class="wk"><b>${fmt.dist(w.totals.distance_m, 0)}</b>${fmt.date(w.week)}</div>
      ${w.days.map(d => `<div class="log-day ${d.future ? "future" : ""}">${d.acts.filter(a => fam === "all" || a.family === fam).slice(0, 1).map(a => {
        const sz = 14 + 22 * Math.sqrt((a.load || 10) / maxLoad);
        return `<a href="#/activity/${encodeURIComponent(a.id)}" class="bubble" style="width:${sz}px;height:${sz}px;background:${sportColor(a.family)}" title="${esc(a.name || a.sport)} · ${a.distance_m ? fmt.dist(a.distance_m) : fmt.mins(a.duration_s)}" aria-label="${esc(a.name || a.sport)} ${fmt.date(d.date)}">${d.acts.length > 1 ? d.acts.length : ""}</a>`;
      }).join("")}</div>`).join("")}</div>`).join("")}
      <div class="legend" style="margin-top:8px">${["run", "ride", "strength", "walk", "swim"].map(f => `<span><i style="background:${sportColor(f)};border-radius:50%"></i>${fmt.sport(f)}</span>`).join("")}</div></div>`;
  } else {
    const rows = D.activities.list.filter(a => fam === "all" || a.family === fam).slice(0, 80);
    body = `<div class="card">${cardHead("Training log", seg("log-view", [["calendar", "Calendar"], ["list", "List"]], view))}<div class="list">${rows.map(activityRow).join("") || empty(STR.noData)}</div></div>`;
  }
  const months = log.months;
  const mchart = months.length ? `<div class="card">${cardHead(fam === "all" ? "Monthly distance" : "Monthly " + fmt.sport(fam).toLowerCase() + " distance")}${chart({ id: "months", type: "bar", label: "Monthly distance", x: months.map(m => m.month), h: 150,
    series: [{ name: "Distance", color: "var(--accent)", values: months.map(m => (fam === "all" ? m.totals : (fam === "run" ? m.run : null) || m.totals).distance_m / (IMPERIAL ? 1609.344 : 1000)) }],
    fmtX: m => fmt.date(m + "-15", { month: "long", year: "numeric" }), fmtXAxis: m => fmt.date(m + "-15", { month: "short" }), fmtY: v => fmt.n(v, 0) + " " + fmt.distUnit() })}</div>` : "";
  return `<div class="stack">${head}${body}${mchart}</div>`;
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
  return `<div class="card">${cardHead("Progress", seg("prog-range", [["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["12m", "1Y"]], range))}
    <div class="row wrap" style="justify-content:space-between;gap:12px;margin-bottom:16px">${chips("prog-fam", [["all", "All sports"], ["run", "Run"], ["ride", "Ride"], ["strength", "Strength"], ["walk", "Walk"]], fam)}${seg("prog-metric", [["distance_m", "Distance"], ["duration_s", "Time"], ["elevation_gain_m", "Elevation"], ["load", "Load"], ["count", "Count"]], metric)}</div>
    <div class="stats-grid" style="margin-bottom:12px">${stat(`Last ${P0.weeks} weeks`, ft(tot), "", { d: isNum(dp) ? deltaHtml(dp, 0, "%", true) : "" })}${stat(`Prior ${P0.weeks} weeks${P0.prior_complete ? "" : " (partial)"}`, ft(ptot))}</div>
    ${chart({ id: "prog", label: "Cumulative progress vs prior period", x: s.current.map(r => r.week), h: 200,
      series: [{ name: "Current", color: "var(--accent)", values: cur, area: true, dots: cur.length < 20 }, { name: "Prior period", color: "var(--prior)", values: pri, dots: pri.length < 20 }],
      fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.n(v, unit === "h" ? 1 : 0) + (unit ? " " + unit : "") })}
</div>`;
}

/* ---------------- plan ---------------- */
function weekGrid(wk) {
  const today = D.meta.build_date;
  return `<div class="weekgrid" data-weekgrid>${wk.days.map(d => `<div class="dh ${d === today ? "today" : ""}">${fmt.dow(d).slice(0, 2)}<b>${fmt.date(d, { day: "numeric" })}</b></div>`).join("")}
    ${wk.days.map(d => `<div class="col" data-drop="${d}">${wk.sessions.filter(s => s.date === d).map(s => {
      const cls = s.type === "REST" ? "rest" : s.compliance || "planned";
      const load = isNum(s.actual_load) ? `L${fmt.n(s.actual_load)}${isNum(s.planned_load) ? ` <span class="faint">(${fmt.n(s.planned_load)})</span>` : ""}` : isNum(s.planned_load) ? `<span class="faint">L${fmt.n(s.planned_load)}</span>` : "";
      const dur = s.actual_duration_s || s.duration_s;
      return `<button class="wtile ${cls}" ${d >= today && !s.workout_id && AG.online ? `draggable="true" data-drag="${esc(s.id)}"` : ""} data-open="session" data-arg="${esc(s.id)}" aria-label="${esc(s.label || s.type)} ${esc(fmt.sport(cls))}">
        <b>${esc(s.type === "NPU" ? "NPU" : s.type)}</b>${s.type !== "REST" ? `<span>${load}</span><br><span>${dur ? fmt.mins(dur) : ""}</span>` : ""}<span class="sr">${esc(fmt.sport(cls === "planned" ? "" : cls))}</span></button>`;
    }).join("")}</div>`).join("")}</div>`;
}
function weekSummary(h) {
  const row = (label, a, p, f) => `<div class="wk-sum"><div class="spread small"><span class="muted">${label}</span><span><b>${f(a)}</b><span class="muted"> of ${f(p)}</span></span></div>${bar(p ? Math.min(100, a / p * 100) : 0, "var(--accent)")}</div>`;
  return `<div class="wk-sums">${row("Sessions", h.actual.sessions, h.planned.sessions, v => fmt.n(v))}${row("Time", h.actual.duration_s, h.planned.duration_s, v => fmt.mins(v))}${row("Load", h.actual.load, h.planned.load, v => fmt.n(v))}</div>`;
}
const WK_ICON = { STR: "strength", REST: "bed", REC: "walk" };
function weekStrip(wk) {
  const today = D.meta.build_date;
  return `<div class="wk-strip">${wk.days.map(d => {
    const ss = wk.sessions.filter(s => s.date === d && s.type !== "REST");
    const s = ss[0];
    const st = !s ? "rest" : s.compliance || "planned";
    return `<button class="wk-day ${d === today ? "today" : ""}" data-open="calday" data-arg="${d}" aria-label="${fmt.dateLong(d)}: ${s ? esc(s.label || s.type) + ", " + esc(fmt.sport(st)) : "rest"}">
      <span class="wk-dow">${fmt.dow(d).slice(0, 1)}</span><span class="wk-num">${fmt.date(d, { day: "numeric" })}</span>
      <span class="wk-ic ${esc(st)}">${icon(s ? WK_ICON[s.type] || "run" : "bed")}</span></button>`;
  }).join("")}</div>`;
}
function weekList(wk) {
  const rows = wk.sessions.filter(s => s.type !== "REST").map(s => {
    const st = s.compliance && s.compliance !== "planned" ? s.compliance : null;
    const dur = s.actual_duration_s || s.duration_s;
    return `<button class="li" data-open="session" data-arg="${esc(s.id)}"><span class="wk-ic sm ${esc(st || "planned")}">${icon(WK_ICON[s.type] || "run")}</span>
      <div class="grow"><div class="t">${esc(s.title || s.label || s.type)}</div><div class="s">${fmt.dow(s.date)} ${fmt.date(s.date, { day: "numeric" })}${dur ? " · " + fmt.mins(dur) : ""}${isNum(s.actual_load) ? " · load " + fmt.n(s.actual_load) : isNum(s.planned_load) ? " · load " + fmt.n(s.planned_load) : ""}</div></div>
      ${st ? badge(({ as_planned: "As planned", done: "Done", partial: "Partial", missed: "Missed", unplanned: "Unplanned", skipped: "Skipped" })[st] || fmt.sport(st), st === "as_planned" || st === "done" ? "ok" : st === "partial" ? "warn" : st === "unplanned" ? "est" : "bad") : `<span class="small muted">Planned</span>`}</button>`;
  }).join("");
  return `<div class="list">${rows}</div>`;
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
  try { await act("plan.move", { session_id: id, date }, "Session moved"); } catch (err) { /* shown */ }
}
function trPlan() {
  const p = D.plans;
  const which = chipVal("plan-week", "this");
  const wk = which === "next" ? p.next_week : which === "last" ? p.last_week : p.this_week;
  const races = p.races.races;
  const inst = p.instant;
  const cal = p.calendar;
  return `<div class="cols c21"><div class="stack"><div class="card">
      ${cardHead(`${fmt.date(wk.days[0])} – ${fmt.date(wk.days[6])}`, seg("plan-week", [["last", "Last"], ["this", "This week"], ["next", "Next"]], which), `Drag a planned session to another day, or open it and choose Move to. ${p.has_explicit_plan ? "" : "Sessions come from your weekly template."}`)}
      ${weekSummary(wk.header)}
      <div class="hide-m" style="margin-top:16px">${weekGrid(wk)}</div><div class="hide-d" style="margin-top:16px">${weekStrip(wk)}${weekList(wk)}</div>
      <div class="spread hide-m" style="margin-top:12px;flex-wrap:wrap"><div class="legend"><span><i style="border:2px solid var(--ok)"></i>As planned</span><span><i style="border:2px solid var(--warn)"></i>Partial</span><span><i style="border:2px dashed var(--bad)"></i>Missed</span><span><i style="border:2px solid var(--text-3)"></i>Unplanned</span></div>${isNum(wk.header.compliance_pct) ? `<span class="small muted">${wk.header.compliance_pct}% compliance</span>` : ""}</div>
      ${AG.online ? `<div class="actions">${editBtn("session-new", "", "Add session")}${editBtn("event-add", undefined, "Add event")}${editBtn("plan-new", undefined, "New plan")}</div>` : ""}</div>
    ${p.adaptations.length ? `<div class="card">${cardHead("Suggested changes", "", "Originals stay visible and nothing changes until you accept. An accepted change notes the original on the session.")}${p.adaptations.map(a => `<div class="suggest"><div class="grow"><b>${fmt.dow(a.date)}: ${esc(adaptText(a))}</b><span>${esc(a.reason)}</span></div>${adaptButtons(a)}</div>`).join("")}</div>` : ""}
    ${p.conflicts.length ? `<div class="card">${cardHead("Calendar conflicts")}<div class="list">${p.conflicts.map(c => `<div class="li"><div class="grow"><div class="t">${fmt.dow(c.date)} ${fmt.date(c.date)}</div><div class="s">${esc(c.event || "")} · ${esc(c.reason)}</div></div></div>`).join("")}</div></div>` : ""}
    <div class="card">${cardHead("Upcoming")}${p.upcoming.length ? `<div class="list" data-upcoming>${p.upcoming.map(s => `<button class="li" data-open="session" data-arg="${esc(s.id)}"><span class="icon-dot" style="color:${sportColor(s.sport === "strength" ? "strength" : "run")}">${sportIcon(s.sport === "strength" ? "strength" : "run")}</span><div class="grow"><div class="t">${esc(s.title || s.label)}</div><div class="s">${fmt.dow(s.date)} ${fmt.date(s.date)} · ${esc(s.label || s.type)}${s.origin === "template" ? " · template" : ""}</div></div><div class="r small">${s.duration_s ? fmt.mins(s.duration_s) : ""}</div></button>`).join("")}</div>` : empty(STR.noPlan)}</div>
    <div class="card">${cardHead(fmt.date(D.meta.build_date, { month: "long", year: "numeric" }))}${monthGrid(cal)}</div></div>
    <div class="stack">
    <div class="card">${cardHead("Season", editBtn("race-edit", "", "Add race"), races.length ? `A races get a ${(races.find(r => r.priority === "A") || {}).taper_days || 14}-day taper. B races get a short one. C races get none.` : "")}${races.length ? `<div class="list">${races.map(r => `<div class="li" ${AG.online ? `role="button" tabindex="0" data-open="race-edit" data-arg="${esc(r.id)}"` : ""}><span class="prio ${esc(r.priority || "B")}">${esc(r.priority || "B")}</span><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })}${r.distance_m ? " · " + fmt.dist(r.distance_m) : ""} · ${esc(fmt.sport(r.phase))}</div></div><div class="r">${r.days_to}<div class="cap">days</div></div></div>`).join("")}</div>
` : `<p class="small muted" style="margin:0">${p.races.mode === "maintain" ? "No target race. Training to maintain." : "No target race"}</p>`}</div>
    ${p.plans.map(pl => `<div class="card">${cardHead(esc(pl.name), pl.goal ? `<span class="small muted">${esc(pl.goal)}</span>` : "")}<div class="list">${(pl.phases || []).map(ph => `<div class="li"><div class="grow"><div class="t">${esc(ph.name)}</div><div class="s">${esc(ph.focus || "")}</div></div><div class="r small muted" style="font-weight:500">${fmt.date(ph.start)} – ${fmt.date(ph.end)}</div></div>`).join("")}</div></div>`).join("")}
    <div class="card">${cardHead("Instant workouts")}${inst.status === "ok" ? `<div class="list">${inst.options.map((o, i) => `<div class="li"><div class="grow"><div class="t">${esc(o.title)}</div><div class="s">${esc(fmt.sport(o.mode))} · ${esc(o.why)}${o.route ? " · " + esc(o.route.name) : ""}</div></div><div class="r small">${fmt.mins(o.duration_s)}</div>${editBtn("instant-schedule", i, "Schedule")}</div>`).join("")}</div>` : `<p class="small muted">Needs ${inst.needed} runs in the last 4 weeks (have ${inst.have})</p>`}</div>
    <div class="card">${cardHead("Routines", editBtn("routine-new", undefined, "New"))}${p.routines.length ? `<div class="list">${p.routines.map(rt => `<button class="li" data-open="routine" data-arg="${esc(rt.id)}"><div class="grow"><div class="t">${esc(rt.name)}</div><div class="s">${esc(fmt.sport(rt.sport))} · ${fmt.mins(rt.total_duration_s)}${rt.guiding_metric ? " · guide by " + esc(rt.guiding_metric) : ""}</div></div></button>`).join("")}</div>` : empty("No routines yet")}</div>
    <div class="card">${cardHead("Templates")}${(p.templates || []).length ? `<div class="list">${p.templates.map(t => `<${AG.online ? `button type="button" data-open="template-edit" data-arg="${esc(t.id)}"` : "div"} class="li"><div class="grow"><div class="t">${esc(t.name)}</div><div class="s">${esc(t.type)}${t.duration_s ? " · " + fmt.mins(t.duration_s) : ""}</div></div></${AG.online ? "button" : "div"}>`).join("")}</div>` : `<p class="small muted" style="margin:0">None saved yet</p>`}</div>
    </div></div>`;
}
AG.sheets.routine = function (id) {
  const rt = D.plans.routines.find(r => r.id === id);
  if (!rt) return;
  openSheet(rt.name, `${stepList(rt.steps)}${AG.online ? `<div class="edit-row"><button class="btn sm" data-open="routine-schedule" data-arg="${esc(rt.id)}">Schedule…</button></div>` : ""}${sectionTitle("Apple Watch export")}<p class="small muted">${esc(rt.watch_export.note)}</p>
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
  return `<div style="display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px">${["M", "T", "W", "T", "F", "S", "S"].map(x => `<div class="cap" style="text-align:center">${x}</div>`).join("")}${cells.join("")}</div>
    <div class="legend" style="margin-top:8px"><span><i style="background:var(--run);border-radius:50%"></i>Done</span><span><i style="border:1.5px solid var(--text-3);border-radius:50%"></i>Planned</span><span><i style="background:var(--info);border-radius:50%"></i>Event</span></div>`;
}
AG.sheets.calday = function (date) {
  const d = D.plans.calendar.days.find(x => x.date === date);
  if (!d) return;
  openSheet(fmt.dateLong(date), `${d.acts.length ? sectionTitle("Activities") + `<div class="list">${d.acts.map(a => `<a class="li" href="#/activity/${encodeURIComponent(a.id)}"><div class="grow"><div class="t">${esc(a.name || fmt.sport(a.sport))}</div><div class="s">${fmt.mins(a.duration_s)}${a.distance_m ? " · " + fmt.dist(a.distance_m) : ""}${a.planned ? " · planned" : " · unplanned"}</div></div></a>`).join("")}</div>` : ""}
    ${d.sessions.length ? sectionTitle("Planned") + `<div class="list">${d.sessions.map(s => `<button class="li" data-open="session" data-arg="${esc(s.id)}"><div class="grow"><div class="t">${esc(s.title || s.label)}</div><div class="s">${esc(fmt.sport(s.compliance || ""))}</div></div></button>`).join("")}</div>` : ""}
    ${AG.online && date >= D.meta.build_date ? `<div class="edit-row"><button class="btn sm secondary" data-open="session-new" data-arg="${date}">Add session this day</button></div>` : ""}
    ${d.events.length ? sectionTitle("Calendar") + `<div class="list">${d.events.map(e => `<div class="li"><div class="grow"><div class="t">${esc(e.title)}</div><div class="s">${fmt.time(e.start)}–${fmt.time(e.end)}</div></div></div>`).join("")}</div>` : ""}
    ${!d.acts.length && !d.sessions.length && !d.events.length ? `<p class="small muted">Nothing on this day</p>` : ""}`);
};

function trZones() {
  const hz = D.training.hr_zones, pz = D.training.pace_zones, zd = D.training.zone_distribution;
  const zc = i => `var(--z${i + 1})`;
  return `<div class="cols"><div class="stack"><div class="card">${cardHead("Heart-rate zones", "", hz.zones ? `${esc(fmt.sport(String(hz.model).replace(/^(\d)zone$/, "$1 zones")))} from ${esc(fmt.sport(hz.basis))} ${hz.basis_value || ""}${hz.method ? " (" + esc(fmt.sport(hz.method)) + ")" : ""}${hz.date ? ", " + fmt.date(hz.date, { day: "numeric", month: "short", year: "numeric" }) : ""}. No age-based formula is used.` : "")}${hz.zones ? `<table class="tbl"><tr><th>Zone</th><th class="r">Range (bpm)</th></tr>${hz.zones.map((z, i) => `<tr><td><i class="zdot" style="background:${zc(i)}"></i>${z.name}</td><td class="r">${z.low}–${z.high}</td></tr>`).join("")}</table>
` : empty(STR.hrMax, hz.reason)}</div>
    <div class="card">${cardHead("Pace zones", "", pz.zones ? `From threshold pace ${fmt.pace(pz.basis_value)}${pz.method ? " (" + esc(fmt.sport(pz.method)) + ")" : ""}.` : "")}${pz.zones ? `<table class="tbl"><tr><th>Zone</th><th class="r">Pace</th></tr>${pz.zones.map((z, i) => `<tr><td><i class="zdot" style="background:${zc(i)}"></i>${z.name}</td><td class="r">${z.slow ? fmt.pace(z.slow, false) : "slower"} – ${fmt.pace(z.fast)}</td></tr>`).join("")}</table>` : empty("Threshold pace not configured", pz.reason)}</div></div>
    <div class="card">${cardHead("Time in zones by week")}${zd.status === "ok" ? chart({ id: "zd", type: "bar", stacked: true, label: "Weekly time in heart-rate zones", x: zd.weeks.map(w => w.week), h: 200,
      series: zd.zones.map((z, i) => ({ name: z, color: zc(i), values: zd.weeks.map(w => w.s[i] / 60) })), fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.hm(v), fmtYAxis: v => fmt.n(v / 60, 0) + "h" }) : empty(STR.hrMax, zd.reason)}</div></div>`;
}

function trRecords() {
  const rec = D.records, preds = D.training.predictions;
  const effortRows = (rec.run || []).map(r => `<button class="li" data-open="efforts" data-arg="${r.distance_m}"><div class="grow"><div class="t">${fmt.distLabel(r.distance_m)}</div><div class="s">${fmt.date(r.best.date, { day: "numeric", month: "short", year: "numeric" })} · ${fmt.pace(r.best.pace_s_per_km)}</div></div><div class="r">${fmt.dur(r.best.time_s)}</div></button>`).join("");
  const lg = rec.longest || {};
  return `<div class="cols"><div class="stack"><div class="card">${cardHead("Race predictions", badge("Estimate", "est"), preds.length ? `${esc(preds[0].method)} from your ${fmt.distLabel(preds[0].source.distance_m)} of ${fmt.dur(preds[0].source.time_s)} on ${fmt.date(preds[0].source.date)}, the nearest-distance effort in the last 120 days.` : "")}
      ${preds.length ? `<div class="list">${preds.map(p => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(p.distance_m)}</div><div class="s">${fmt.pace(p.pace_s_per_km)}</div></div><div class="r">${fmt.dur(p.time_s)}</div></div>`).join("")}</div>` : empty("No qualifying efforts in the last 120 days", "Run 3 km or more with distance samples")}</div>
    <div class="card">${cardHead("Best efforts")}${effortRows ? `<div class="list">${effortRows}</div>` : empty(STR.noData)}</div></div>
    <div class="stack"><div class="card">${cardHead("Longest")}<div class="list">${Object.entries(lg).map(([f, v]) => `<a class="li" href="#/activity/${encodeURIComponent(v.workout_id)}"><span class="icon-dot" style="color:${sportColor(f)}">${sportIcon(f)}</span><div class="grow"><div class="t">${fmt.sport(f)}</div><div class="s">${fmt.date(v.date, { day: "numeric", month: "short", year: "numeric" })}</div></div><div class="r">${fmt.dist(v.distance_m)}</div></a>`).join("") || empty(STR.noData)}</div></div>
    ${(rec.ride || []).length || (rec.swim || []).length ? `<div class="card">${cardHead("Cycling & swimming")}<div class="list">${[].concat(rec.ride || [], rec.swim || []).map(r => `<div class="li"><div class="grow"><div class="t">${fmt.distLabel(r.distance_m)}</div></div><div class="r">${fmt.dur(r.best.time_s)}</div></div>`).join("")}</div></div>` : ""}
    ${rec.power ? `<div class="card">${cardHead("Best power")}<div class="list">${rec.power.map(p => `<div class="li"><div class="grow"><div class="t">${durLabel(p.s)}</div></div><div class="r">${p.v} W</div></div>`).join("")}</div></div>` : ""}
    <div class="card tight"><div class="list"><a class="li chev" href="#/strength?tab=records"><span class="icon-dot" style="color:var(--strength)">${icon("strength")}</span><div class="grow"><div class="t">Strength records</div></div></a></div></div></div></div>`;
}
AG.sheets.efforts = function (dist) {
  const r = (D.records.run || []).find(x => String(x.distance_m) === String(dist));
  if (!r) return;
  openSheet(fmt.distLabel(r.distance_m) + " · top efforts", `<table class="tbl"><tr><th>#</th><th>Date</th><th class="r">Time</th><th class="r">Pace</th></tr>${r.top.map((e, i) => `<tr><td>${i + 1}</td><td><a href="#/activity/${encodeURIComponent(e.workout_id)}">${fmt.date(e.date, { day: "numeric", month: "short", year: "numeric" })}</a></td><td class="r">${fmt.dur(e.time_s)}</td><td class="r">${fmt.pace(e.pace_s_per_km)}</td></tr>`).join("")}</table><p class="cap">Ranks within your own history only.</p>`);
};

function recapCard(y, big, idx) {
  const run = (y.totals || {}).run || {};
  const all = Object.values(y.totals || {}).reduce((a, t) => ({ d: a.d + (t.distance_m || 0), s: a.s + (t.duration_s || 0), e: a.e + (t.elevation_gain_m || 0) }), { d: 0, s: 0, e: 0 });
  return `<div class="card">${cardHead(esc(y.label) + (y.partial ? ` <span class="small muted" style="font-weight:500">to date</span>` : ""), isNum(idx) ? `<button class="btn sm secondary" data-share="${idx}" data-kind="png">Share</button>` : "")}
    <div class="stats-grid ${big ? "s4" : ""}">${stat("Activities", fmt.n(y.activities))}${stat("Distance", fmt.dist(all.d, 0))}${stat("Time", fmt.mins(all.s))}${stat("Elevation", fmt.elev(all.e))}
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
  return `<div class="cols"><div class="stack">${sectionTitle("Year in Sport")}${R.years.map((y, i) => [y, i]).reverse().map(([y, i]) => recapCard(y, true, i)).join("")}</div>
    <div class="stack">${sectionTitle("Month in Sport")}${R.months.map((m, i) => recapCard(m, false, R.years.length + i)).join("")}</div></div>
`;
}

function trReview() {
  const w = D.weekly_review;
  const n = w.numbers;
  return `<div class="cols"><div class="stack"><div class="card">${cardHead(`Week of ${fmt.date(w.week_start)}`, [w.cardio_status && w.cardio_status.v ? badge(fmt.sport(w.cardio_status.v), "info") : "", w.complete ? "" : badge("In progress", "est")].join(""))}
      <div class="stats-grid s3-d">${stat("Distance", n.totals ? fmt.dist(n.totals.distance_m) : "—")}${stat("Time", n.totals ? fmt.mins(n.totals.duration_s) : "—")}${stat("Load", fmt.n(n.load_sum))}
      ${stat("Sleep avg", isNum(n.sleep_avg_min) ? fmt.hm(n.sleep_avg_min) : "—")}${stat("Recovery avg", isNum(n.recovery_avg) ? n.recovery_avg + "%" : "—")}${stat("Weight", isNum(n.weight_median_kg) ? fmt.kg(n.weight_median_kg) : "—")}
      ${stat("Protein days", isNum(n.protein_days_hit) ? `${n.protein_days_hit}/${n.protein_days_logged}` : "—")}${stat("Compliance", isNum(w.compliance_pct) ? w.compliance_pct + "%" : "—")}</div></div>
    <div class="card">${cardHead("Four weeks")}<table class="tbl"><tr><th>Week</th><th class="r">Distance</th><th class="r">Time</th><th class="r">Load</th></tr>${w.four_week_log.map(x => `<tr><td>${fmt.date(x.week)}</td><td class="r">${fmt.dist(x.totals.distance_m)}</td><td class="r">${fmt.mins(x.totals.duration_s)}</td><td class="r">${fmt.n(x.totals.load)}</td></tr>`).join("")}</table></div></div>
    <div class="stack"><div class="card">${cardHead("Goals")}${w.goals.length ? `<div class="list">${w.goals.map(g => `<div class="li"><div class="grow"><div class="t">${esc(g.title)}</div><div class="s">${isNum(g.progress_pct) ? fmt.n(g.progress_pct) + "%" : ""}</div></div>${goalStatusBadge(g.status)}</div>`).join("")}</div>` : empty(STR.noGoals)}</div>
    <div class="card">${cardHead("Next week")}${w.next_week_intent.length ? `<div class="list">${w.next_week_intent.map(s => `<div class="li"><div class="grow"><div class="t">${esc(s.title || s.type)}</div><div class="s">${fmt.dow(s.date)} ${fmt.date(s.date)}</div></div></div>`).join("")}</div>` : empty(STR.noPlan)}</div></div></div>`;
}

AG.screens.review = { title: "Weekly review", parent: "#/training", nav: "training", render() { return trReview(); }, after() { drawCharts(); } };
AG.screens.recaps = { title: "Year in Sport", parent: "#/training", nav: "training", render() { return trRecaps(); }, after() { drawCharts(); } };
