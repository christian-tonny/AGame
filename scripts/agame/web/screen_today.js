/* Today, Strain detail, Timeline */
"use strict";

const CALL_LABEL = { train: ["Train as planned", "ok"], reduce: ["Go easier today", "warn"], rest: ["Rest today", "bad"], rest_day: ["Planned rest day", "info"],
  open: ["Nothing planned", ""], unknown: ["Not enough data", ""] };

function sessionCard(s, opts = {}) {
  const pre = s.pre || {};
  const tg = pre.targets || {};
  const tgt = tg.hr ? `HR ${tg.hr.low}–${tg.hr.high}` : tg.pace ? `Pace ${fmt.pace(tg.pace.fast, false)}–${fmt.pace(tg.pace.slow)}` : "";
  const comp = s.compliance && s.compliance !== "planned" ? badge(fmt.sport(s.compliance), s.compliance === "as_planned" || s.compliance === "done" ? "ok" : s.compliance === "partial" ? "warn" : "bad") : "";
  return `<button class="card tight" data-open="session" data-arg="${esc(s.id)}" style="margin-bottom:8px">
    <div class="spread"><span class="tag">${esc(s.label || s.type)}${s.origin === "template" ? " · from your weekly template" : ""}</span>${comp || (s.priority === "key" ? badge("Key", "accent") : "")}</div>
    <div class="spread" style="margin-top:4px"><b style="font-size:17px">${esc(s.title || s.label)}</b><span class="muted small">${s.duration_s ? fmt.mins(s.duration_s) : ""}</span></div>
    <div class="small muted" style="margin-top:2px">${esc(pre.objective || "")}${pre.guiding_metric ? ` · guide by ${esc(pre.guiding_metric.toUpperCase())}` : ""}${tgt ? " · " + esc(tgt) : ""}</div></button>`;
}

AG.sheets.session = function (id) {
  const all = [].concat(D.plans.today, D.plans.tomorrow, D.plans.upcoming, D.plans.this_week.sessions, D.plans.next_week.sessions);
  const s = all.find(x => x.id === id);
  if (!s) return;
  const pre = s.pre || {};
  const alts = s.alternatives || (D.plans.upcoming.find(x => x.id === id) || {}).alternatives || [];
  const adapt = D.plans.adaptations.filter(a => a.session_id === id);
  const tg = pre.targets || {};
  openSheet(s.title || s.label, `
    <div class="stats-grid s3">${stat("Type", esc(s.label || s.type))}${stat("Duration", s.duration_s ? fmt.mins(s.duration_s) : "—")}${stat("Planned load", isNum(s.planned_load) ? fmt.n(s.planned_load) : "—")}</div>
    ${pre.objective ? `<p class="small" style="margin:12px 0 4px"><b>Objective</b> · ${esc(pre.objective)}</p>` : ""}
    ${pre.guiding_metric ? `<p class="small muted" style="margin:0">Guide by ${esc(pre.guiding_metric.toUpperCase())} · ${esc(pre.watch || "")}</p>` : ""}
    ${tg.hr || tg.pace ? `<div class="row wrap" style="margin-top:10px">${tg.hr ? badge(`Zone ${tg.hr.zone}: ${tg.hr.low}–${tg.hr.high} bpm`, "info") : ""}${tg.pace ? badge(`Pace ${fmt.pace(tg.pace.fast, false)}–${fmt.pace(tg.pace.slow)}`, "info") : ""}</div>` : ""}
    ${adapt.length ? sectionTitle("Suggested change") + adapt.map(a => insightCard(adaptText(a), a.reason, "action")).join("") : ""}
    ${s.steps && s.steps.length ? sectionTitle("Steps") + stepList(s.steps) : ""}
    ${s.workout_id ? `<a class="btn secondary" style="margin-top:12px;width:100%" href="#/activity/${encodeURIComponent(s.workout_id)}">Open completed activity</a>` : ""}
    ${alts.length ? sectionTitle("Workout Wizard") + `<div class="list">${alts.map(a => `<div class="li"><div class="grow"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.note)}</div></div><div class="r small">${a.duration_s ? fmt.mins(a.duration_s) : "—"}<div class="cap">${isNum(a.est_load) ? "load ~" + fmt.n(a.est_load) : ""}</div></div></div>`).join("")}</div>
      <p class="cap">Alternatives keep the rest of your week unchanged. Choosing one updates plans.json through your AGame server.</p>${offlineNote()}` : ""}`);
};
function adaptText(a) {
  const lbl = t => (D.plans.this_week.sessions.find(s => s.type === t) || {}).label || ({ AER: "Aerobic", REC: "Recovery", REST: "Rest", MOB: "Mobility" }[t] || t);
  if (a.action === "swap") return `Swap to ${lbl(a.to)}`;
  if (a.action === "shorten") return `Shorten to ${Math.round(a.factor * 100)}%`;
  if (a.action === "move") return `Move to ${fmt.dow(a.to_date)} ${fmt.date(a.to_date)}`;
  if (a.action === "adjust_pace") return `Run ${a.pct_slower}% slower`;
  return fmt.sport(a.action);
}

AG.sheets.factors = function () {
  const r = D.today.recommendation;
  openSheet("Why this call", `<p class="small"><b>${esc((CALL_LABEL[r.call] || [r.call])[0])}</b> · ${esc(r.why)}</p><div class="list">${r.factors.map(factorRow).join("") || empty(STR.noData)}</div>
    <p class="cap" style="margin-top:12px">Thresholds come from config (recovery bands, form, sleep debt). Fitness information, not medical advice.</p>`);
};

AG.screens.today = {
  title: "Today",
  render() {
    const t = D.today;
    const rec = t.recommendation;
    const [callTxt, callCls] = CALL_LABEL[rec.call] || [rec.call, ""];
    const rings = `<div class="card"><div class="rings">
      <a class="ring-tile" href="#/strain">${ring("strain", t.rings.strain, { label: "Strain", sub: "so far" })}<span class="label">Strain</span><span class="sub">${t.rings.strain && isNum(t.rings.strain.yesterday) ? "Yday " + fmt.n(t.rings.strain.yesterday) + "%" : "&nbsp;"}</span></a>
      <a class="ring-tile" href="#/recovery">${ring("recovery", t.rings.recovery, { label: "Recovery", sub: t.rings.recovery && t.rings.recovery.status === "stale" ? "stale" : "" })}<span class="label">Recovery</span><span class="sub">${t.rings.recovery && t.rings.recovery.confidence ? esc(t.rings.recovery.confidence) + " confidence" : "&nbsp;"}</span></a>
      <a class="ring-tile" href="#/sleep">${ring("sleep", t.rings.sleep, { label: "Sleep", sub: t.rings.sleep && t.rings.sleep.status === "stale" ? "stale" : "" })}<span class="label">Sleep</span><span class="sub">${D.sleep.last_night && !D.sleep.stale ? fmt.hm(D.sleep.last_night.asleep_min) : D.sleep.stale ? STR.sleepNotSynced : "&nbsp;"}</span></a>
    </div>${stLine(t.rings.recovery)}</div>`;
    const brief = t.brief && t.brief.line1 ? `<a class="card" href="#/coach"><h3>${icon("coach")} Morning brief</h3><div style="font-weight:650">${esc(t.brief.line1)}</div><div class="small muted" style="margin-top:2px">${esc(t.brief.line2)}</div></a>` : "";
    const action = t.action ? insightCard(t.action.text, t.action.detail, "action") : "";
    const recCard = `<button class="card" data-open="factors"><div class="spread"><h3 style="margin:0">Today's call</h3>${badge(callTxt, callCls)}</div>
      <div class="list" style="margin-top:6px">${rec.factors.slice(0, 3).map(factorRow).join("") || `<p class="small muted">${esc(rec.why)}</p>`}</div><div class="cap" style="text-align:right">All factors ›</div></button>`;
    const bigday = (t.big_day || []).map(b => `<div class="card" style="border-color:color-mix(in srgb,var(--accent) 45%,var(--line))"><h3>${icon("flame")} Big Day Brief · ${esc(b.when)}</h3>
      <b>${esc(b.title)}</b> <span class="muted small">${b.duration_s ? fmt.mins(b.duration_s) : ""}</span>
      <div class="grid g2" style="margin-top:10px"><div><div class="tag">Evening before</div><div class="small">${b.evening.bedtime ? "Bed by " + esc(b.evening.bedtime) : "Set wake time in profile"}</div>${b.evening.fuel ? `<div class="small muted">${esc(b.evening.fuel)}</div>` : ""}<div class="small muted">${esc(b.evening.kit.join(" · "))}</div></div>
      <div><div class="tag">Morning of</div><div class="small">Readiness ${b.morning.readiness === null ? "—" : fmt.n(b.morning.readiness) + "%"} · ${b.morning.call ? esc(b.morning.call === "go" ? "Go" : "Adjust") : "awaiting data"}</div>
      ${b.morning.targets && b.morning.targets.pace ? `<div class="small muted">Pace ${fmt.pace(b.morning.targets.pace.fast, false)}–${fmt.pace(b.morning.targets.pace.slow)}</div>` : ""}${b.morning.targets && b.morning.targets.hr ? `<div class="small muted">HR ${b.morning.targets.hr.low}–${b.morning.targets.hr.high}</div>` : ""}</div></div></div>`).join("");
    const plan = `<div>${sectionTitle("Today's plan", `<a href="#/training?tab=plan">Week ›</a>`)}
      ${t.adaptations.map(a => insightCard(adaptText(a), a.reason, "action")).join("")}
      ${t.plan.length ? t.plan.map(s => sessionCard(s)).join("") : empty(D.plans.has_template || D.plans.has_explicit_plan ? "Rest day" : STR.noPlan, D.plans.has_template ? null : "Add a weekly template in profile or a plan in plans.json")}
      ${t.conflicts.map(c => `<div class="empty inline"><b>Calendar</b><span class="cap">${esc(c.event || "")} · ${esc(c.reason)}</span></div>`).join("")}</div>`;
    const sl = t.stress_latest;
    const eb = t.energy;
    const stress = `<a class="card" href="#/recovery"><div class="spread"><h3 style="margin:0">Stress & Energy</h3>${t.stress && t.stress.kind === "estimated" ? badge("Estimate", "est") : ""}</div>
      ${sl ? `<div class="stats-grid s3" style="margin-top:8px">${stat("Highest", fmt.n(sl.high))}${stat("Lowest", fmt.n(sl.low))}${stat("Average", fmt.n(sl.avg))}</div><div class="cap">${sl.date === D.meta.build_date ? "Today" : "Latest: " + fmt.date(sl.date)}</div>` : `<p class="small muted">Not enough daytime heart-rate samples for stress</p>`}
      <div style="margin-top:10px">${eb ? `<div class="spread small"><span>Energy Bank</span><b>${fmt.n(eb.current)}%</b></div><div class="energy" role="img" aria-label="Energy ${fmt.n(eb.current)} percent"><i style="width:${eb.current}%"></i></div><div class="cap">As of ${fmt.time(eb.as_of)} · started ${fmt.n(eb.start)}%</div>` : `<p class="small muted">Energy Bank needs recovery or sleep</p>`}</div></a>`;
    const ld = t.load;
    const we = ld.weekly_effort || {};
    const band = we.band;
    const maxv = band ? Math.max(band.high * 1.3, we.current || 0) : (we.current || 1);
    const load = `<a class="card" href="#/training"><div class="spread"><h3 style="margin:0">Training load</h3>${ld.status && ld.status.v ? badge(fmt.sport(ld.status.v), { productive: "ok", maintaining: "info", fatigued: "warn", overreaching: "bad", detraining: "", calibrating: "" }[ld.status.v]) : ""}</div>
      <div class="stats-grid s3" style="margin-top:8px">${stat("Form", ld.tsb && isNum(ld.tsb.v) ? fmt.signed(ld.tsb.v, 0) : "—")}${stat("Fitness", ld.status && isNum(ld.status.ctl) ? fmt.n(ld.status.ctl) : "—")}${stat("Fatigue", ld.status && isNum(ld.status.atl) ? fmt.n(ld.status.atl) : "—")}</div>
      ${band ? `<div style="margin-top:10px"><div class="spread small"><span>This week's effort</span><b>${fmt.n(we.current)}</b></div>
        <div class="bar" style="height:10px"><i style="width:${Math.min(100, (we.current || 0) / maxv * 100)}%"></i><em style="left:${band.low / maxv * 100}%"></em><em style="left:${band.high / maxv * 100}%"></em></div>
        <div class="cap">Range ${fmt.n(band.low)}–${fmt.n(band.high)} from your last ${band.weeks} weeks · ${esc({ maintain: "maintain", increase: "room to increase", recover: "consider recovering" }[we.hint] || "")}</div></div>` : `<p class="cap">Weekly effort range appears after 3 full weeks</p>`}</a>`;
    const sy = t.since_yesterday;
    const since = `<div class="card"><h3>Since yesterday</h3><div class="stats-grid s4">
      ${stat("HRV", isNum(sy.hrv.v) ? fmt.n(sy.hrv.v) : "—", "ms", { d: isNum(sy.hrv.v) ? deltaHtml(sy.hrv.delta, 0, "", true) : `<span class="cap">${esc(sy.hrv.note || "")}</span>` })}
      ${stat("Resting HR", isNum(sy.rhr.v) ? fmt.n(sy.rhr.v) : "—", "bpm", { d: isNum(sy.rhr.v) ? deltaHtml(sy.rhr.delta, 0, "", false) : `<span class="cap">${esc(sy.rhr.note || "")}</span>` })}
      ${stat("Sleep", isNum(sy.sleep.v) ? fmt.hm(sy.sleep.v) : "—", "", { d: isNum(sy.sleep.v) ? deltaHtml(sy.sleep.delta, 0, "m", true) : `<span class="cap">${esc(sy.sleep.note || "")}</span>` })}
      ${stat("Weight", isNum(sy.weight.v) ? fmt.kgNum(sy.weight.v) : "—", fmt.wUnit(), { d: isNum(sy.weight.v) ? deltaHtml(IMPERIAL && isNum(sy.weight.delta) ? sy.weight.delta * 2.20462 : sy.weight.delta, 1, "", null) : `<span class="cap">${esc(sy.weight.note || "")}</span>` })}
    </div></div>`;
    const yday = `<div>${sectionTitle("Yesterday", `<a href="#/activities">All ›</a>`)}<div class="card tight">${t.yesterday.length ? `<div class="list">${t.yesterday.map(activityRow).join("")}</div>` : `<p class="small muted" style="margin:4px">No workouts yesterday</p>`}</div></div>`;
    const goals = `<div>${sectionTitle("Goals", `<a href="#/goals">All ›</a>`)}<div class="card">${t.goals.length ? t.goals.map(goalRow).join("") : empty(STR.noGoals, "Add goals in goals.json or the Goals screen")}</div></div>`;
    const status = t.status && t.status.status !== "normal" ? badge("Status: " + fmt.sport(t.status.status), "warn") : "";
    const head = `<div class="spread" style="margin-bottom:12px"><div><div class="page-title" style="margin:0">${esc(fmt.dateLong(t.date))}</div></div><div class="row">${status}${freshChip()}</div></div>`;
    return `${head}<div class="cols c3">
      <div class="stack">${rings}${brief}${action}${recCard}</div>
      <div class="stack">${bigday}${plan}${stress}</div>
      <div class="stack">${load}${since}${yday}${goals}<a class="card chev row" href="#/timeline">${icon("timeline")} <b>Timeline</b></a></div>
    </div>`;
  },
  after() { drawCharts(); },
};

AG.screens.strain = {
  title: "Strain", parent: "#/today", nav: "today",
  render() {
    const s = D.strain;
    const rng = chipVal("strain-range", "90");
    const rows = sliceDays(s.history, rangeDays(rng));
    const nr = s.normal_range;
    const todayActs = D.today.today_activities.concat(D.today.yesterday);
    return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><div><div class="stat hero"><span class="v">${val(s.score, 0, "%")}</span></div><div class="cap">${fmt.dateLong(D.meta.build_date)} · ${esc(s.score.note || "")}</div></div>
      <div style="text-align:right">${nr ? `<div class="small" style="color:var(--ok);font-weight:700">Normal range</div><div class="cap">${nr.low}–${nr.high}%</div>` : `<div class="cap">Normal range after 14 days</div>`}${prov(s.score, "Strain")}</div></div></div>
      <div class="card">${chips("strain-range", RANGES_DWMY, rng)}
      ${rows.length ? chart({ id: "strain-ch", label: "Daily strain percent", x: rows.map(r => r.date), series: [{ name: "Strain", color: "var(--strain)", values: rows.map(r => r.v), dots: rows.length < 40 }],
        band: nr ? { low: nr.low, high: nr.high, color: "color-mix(in srgb, var(--strain) 22%, transparent)", name: "Your normal range" } : null, yMin: 0, yMax: 100, fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%", range: rangeLabel(rows), h: 190 }) : empty(STR.noData)}</div></div>
      <div class="stack"><div class="grid g2"><div class="card">${stat("Exercise today", fmt.hm(s.exercise_min))}</div><div class="card">${stat("Daytime HR", isNum(s.daytime_hr) ? fmt.n(s.daytime_hr) : "—", "bpm")}</div></div>
      <div class="card"><h3>Workout strain</h3>${todayActs.length ? `<div class="list">${todayActs.map(a => `<a class="li" href="#/activity/${encodeURIComponent(a.id)}"><div class="grow"><div class="t">${esc(a.name)}</div><div class="s">${fmt.date(a.date)}</div></div><div class="r">${isNum(a.strain) ? fmt.n(a.strain) + "%" : "—"}</div></a>`).join("")}</div>` : `<p class="small muted">No workouts today or yesterday</p>`}
      <p class="cap">Strain = saturating transform of daily load (TRIMP${s.score.k_method === "personal_p90" ? ", personal scale" : ", default scale"}). See calculations doc.</p></div></div></div>`;
  },
  after() { drawCharts(); },
};

AG.screens.timeline = {
  title: "Timeline", parent: "#/today", nav: "today",
  render() {
    const days = Object.keys(D.timeline).sort().reverse();
    const sel = chipVal("tl-day", days[0]);
    const items = D.timeline[sel] || [];
    const ic = { sleep: "sleep", workout: "activities", meal: "nutrition", measurement: "body", journal: "timeline", event: "calendar", planned: "calendar", score: "recovery" };
    return `${chips("tl-day", days.map(d => [d, d === D.meta.build_date ? "Today" : fmt.dow(d) + " " + fmt.date(d, { day: "numeric" })]), sel)}
      <div class="card" style="margin-top:12px">${items.length ? `<div class="list">${items.map(i => `<${i.id && i.type === "workout" ? `a href="#/activity/${encodeURIComponent(i.id)}"` : "div"} class="li"><span class="icon-dot">${icon(ic[i.type] || "other")}</span>
        <div class="grow"><div class="t">${esc(i.title)}</div><div class="s">${esc(i.detail || "")}</div></div><div class="r small muted">${fmt.time(i.t)}</div></${i.id && i.type === "workout" ? "a" : "div"}>`).join("")}</div>` : empty("Nothing recorded for this day")}</div>
      <p class="cap">Sleep, meals, workouts, measurements, journal and planned events in local time (${esc(TZ)}).</p>`;
  },
};
