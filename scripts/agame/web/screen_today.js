/* Today, Strain detail, Timeline */
"use strict";

const CALL_LABEL = { train: ["Train as planned", "ok"], reduce: ["Go easier today", "warn"], rest: ["Rest today", "bad"], rest_day: ["Planned rest day", "info"],
  open: ["Nothing planned", ""], unknown: ["Not enough data", ""] };

function paceRange(p) {
  if (!p) return "";
  if (isNum(p.fast) && isNum(p.slow)) return `Pace ${fmt.pace(p.fast, false)}–${fmt.pace(p.slow)}`;
  if (isNum(p.fast)) return `Pace slower than ${fmt.pace(p.fast)}`;
  return isNum(p.slow) ? `Pace up to ${fmt.pace(p.slow)}` : "";
}
function sessionTarget(s) {
  const tg = (s.pre || {}).targets || {};
  return tg.hr ? `HR ${tg.hr.low}–${tg.hr.high}` : tg.pace ? paceRange(tg.pace) : "";
}
function sessionRow(s) {
  const pre = s.pre || {};
  const meta = [pre.objective, sessionTarget(s)].filter(Boolean).join(" · ");
  const done = s.compliance && s.compliance !== "planned" ? badge(fmt.sport(s.compliance), s.compliance === "as_planned" || s.compliance === "done" ? "ok" : s.compliance === "partial" ? "warn" : "bad") : "";
  return `<button class="li" data-open="session" data-arg="${esc(s.id)}"><span class="icon-dot" style="color:${sportColor(s.family || (s.type === "STR" ? "strength" : "run"))}">${s.type === "STR" ? icon("strength") : icon("run")}</span>
    <div class="grow"><div class="t">${esc(s.title || s.label)}</div><div class="s">${esc(meta || s.label || "")}</div></div>
    <div class="r">${done || (s.duration_s ? fmt.mins(s.duration_s) : "")}</div></button>`;
}
function sessionCard(s) { return `<div class="card tight">${sessionRow(s)}</div>`; }

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
    ${tg.hr || tg.pace ? `<div class="row wrap" style="margin-top:10px">${tg.hr ? badge(`Zone ${tg.hr.zone}: ${tg.hr.low}–${tg.hr.high} bpm`, "info") : ""}${tg.pace ? badge(paceRange(tg.pace), "info") : ""}</div>` : ""}
    ${adapt.map(a => `<div class="suggest" style="margin-top:12px"><div class="grow"><b>${esc(a.title)}</b><span>${esc(a.sub)}</span></div>${adaptButtons(a)}</div>`).join("")}
    ${s.steps && s.steps.length ? sectionTitle("Steps") + stepList(s.steps) : ""}
    ${s.workout_id ? `<a class="btn secondary" style="margin-top:12px;width:100%" href="#/activity/${encodeURIComponent(s.workout_id)}">Open completed activity</a>` : ""}
    ${alts.length ? sectionTitle("Workout Wizard") + `<div class="list">${alts.map(a => `<div class="li"><div class="grow"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.note)}</div></div><div class="r small">${a.duration_s ? fmt.mins(a.duration_s) : "—"}<div class="cap">${isNum(a.est_load) ? "load ~" + fmt.n(a.est_load) : ""}</div></div>${AG.online && s.date >= D.meta.build_date ? `<button type="button" class="btn sm secondary" data-wizard="${esc(a.kind)}" data-sid="${esc(s.id)}">Use</button>` : ""}</div>`).join("")}</div>
` : ""}
    ${AG.online && s.date >= D.meta.build_date && !s.workout_id ? `<div class="edit-row"><button class="btn sm secondary" data-open="session-move" data-arg="${esc(s.id)}">Move to…</button>${s.origin === "plan" ? `<button class="btn sm secondary" data-open="session-edit" data-arg="${esc(s.id)}">Edit</button>` : ""}${s.type !== "REST" ? `<button class="btn sm secondary" data-skip="${esc(s.id)}">Skip</button><button class="btn sm secondary" data-open="session-template" data-arg="${esc(s.id)}">Save as template</button>` : ""}</div>` : ""}`);
};
function adaptButtons(a) {
  return AG.online ? `<div class="actions" style="margin:0"><button class="btn sm" data-adapt="accepted" data-sid="${esc(a.session_id)}" data-rule="${esc(a.rule)}">Accept</button><button class="btn sm secondary" data-adapt="declined" data-sid="${esc(a.session_id)}" data-rule="${esc(a.rule)}">Keep original</button></div>` : "";
}
document.addEventListener("click", e => {
  const w = e.target.closest("[data-wizard]"), ad = e.target.closest("[data-adapt]"), sk = e.target.closest("[data-skip]");
  if (w) act("plan.alternative", { session_id: w.dataset.sid, kind: w.dataset.wizard }, "Session changed").catch(() => {});
  if (ad) act("plan.adaptation", { session_id: ad.dataset.sid, rule: ad.dataset.rule, decision: ad.dataset.adapt }, ad.dataset.adapt === "accepted" ? "Change applied" : "Kept original").catch(() => {});
  if (sk) act("plan.skip", { session_id: sk.dataset.skip }, "Session skipped").catch(() => {});
});

AG.sheets.bigday = function (i) {
  const b = (D.today.big_day || [])[+i || 0];
  if (!b) return;
  const tg = b.morning.targets || {};
  const rows = [
    ["Bedtime", b.evening.bedtime ? "By " + esc(b.evening.bedtime) : "Set a wake time in Profile"],
    b.evening.fuel ? ["Fuel", esc(b.evening.fuel)] : null,
    b.evening.kit && b.evening.kit.length ? ["Kit", esc(b.evening.kit.join(", "))] : null,
    ["Readiness", b.morning.readiness === null ? "Waiting for the morning sync" : fmt.n(b.morning.readiness) + "%" + (b.morning.call ? " · " + (b.morning.call === "go" ? "Go" : "Adjust") : "")],
    tg.pace ? ["Pace", paceRange(tg.pace).replace(/^Pace /, "")] : null,
    tg.hr ? ["Heart rate", `${tg.hr.low}–${tg.hr.high} bpm`] : null,
  ].filter(Boolean);
  openSheet(b.title, `<div class="list">${rows.map(([k, v]) => `<div class="li"><div class="grow"><div class="s">${k}</div></div><div class="r" style="font-weight:600;white-space:normal;text-align:right;max-width:65%">${v}</div></div>`).join("")}</div>`);
};

AG.sheets.factors = function () {
  const r = D.today.recommendation;
  openSheet("Why this call", `<p class="small" style="margin-top:0"><b>${esc((CALL_LABEL[r.call] || [r.call])[0])}</b></p><div class="list">${r.factors.map(factorRow).join("") || empty(STR.noData)}</div>
    <p class="cap" style="margin-top:12px">Thresholds come from config (recovery bands, form, sleep debt). Fitness information, not medical advice.</p>`);
};

function seriesTail(points, key, n) { return (points || []).slice(-n).map(p => isNum(p[key]) ? p[key] : null); }

/* Bevel status line: filled icon + coloured words. good: true/false/null (neutral). */
function statusLine(text, good, dir) {
  const cls = good === null || good === undefined ? "muted" : good ? "ok" : "bad";
  const ic = dir === "up" ? "up-fill" : dir === "down" ? "down-fill" : good ? "ok-fill" : null;
  return `<span class="st ${cls}">${ic ? icon(ic) : ""}${esc(text)}</span>`;
}
function healthTile(label, ic, value, unit, d, betterHigher, spark, color, href, dUnit = "") {
  const good = !isNum(d) || d === 0 || betterHigher === null ? null : (d > 0) === betterHigher;
  const dTxt = isNum(d) && d !== 0 ? `${d > 0 ? "+" : "−"}${Math.abs(d) < 10 && d % 1 ? fmt.n(Math.abs(d), 1) : fmt.n(Math.abs(d))}${dUnit} vs yesterday` : isNum(d) ? "Same as yesterday" : "";
  return `<a class="card tile" href="${href}"><div class="tile-h">${icon(ic)}<span>${esc(label)}</span></div>
    <div class="tile-v">${value === null ? "—" : value}${value !== null && unit ? `<small>${esc(unit)}</small>` : ""}</div>${value === null ? statusLine("No data", null) : statusLine(dTxt.replace(" vs yesterday", ""), good, isNum(d) && d !== 0 ? (d > 0 ? "up" : "down") : null) + (isNum(d) && d !== 0 ? `<span class="st-sub">vs yesterday</span>` : "")}
    <div class="tile-spark">${spark ? sparkline(spark, color, 40) : ""}</div></a>`;
}
/* Wrist temperature against your own baseline: the computed deviation, never an absolute norm. */
function tempTile(T) {
  const k = IMPERIAL ? 1.8 : 1, unit = IMPERIAL ? "°F" : "°C";
  if (!T) return healthTile("Temp", "thermometer", null, unit, null, null, null, "var(--warn)", "#/body?tab=charts");
  const dev = isNum(T.deviation) ? `${T.deviation > 0 ? "+" : T.deviation < 0 ? "−" : ""}${fmt.n(Math.abs(T.deviation * k), 1)}` : null;
  if (dev === null) return `<a class="card tile" href="#/body?tab=charts"><div class="tile-h">${icon("thermometer")}<span>Temp</span></div><div class="tile-v">—</div>${statusLine(`Baseline ${T.nights} of ${T.needed} nights`, null)}<div class="tile-spark"></div></a>`;
  return healthTile("Temp", "thermometer", dev, unit, isNum(T.delta) ? T.delta * k : null, null, T.series.map(p => p.v), "var(--warn)", "#/body?tab=charts", " " + unit);
}
function energyTicks(pct, n = 32) {
  const on = isNum(pct) ? Math.round(Math.max(0, Math.min(100, pct)) / 100 * n) : 0;
  return `<span class="ticks" role="img" aria-label="Energy ${isNum(pct) ? fmt.n(pct) + " percent" : "unknown"}">${Array.from({ length: n }, (_, i) => `<i class="${i < on ? "on" : ""}"></i>`).join("")}</span>`;
}
const goArrow = () => `<span class="go" aria-hidden="true">${icon("arrow")}</span>`;

AG.screens.today = {
  title: "Today", ownTitle: true,
  headRight() {
    const t = D.today, fc = (t.plan || []).find(s => isNum(s.forecast_temp_c));
    return `${t.status && t.status.status !== "normal" ? `<a class="pill" href="#/journal">${esc(fmt.sport(t.status.status))}</a>` : ""}${fc ? `<span class="pill">${esc(fmt.temp(fc.forecast_temp_c))}</span>` : ""}${AG.online ? `<button class="fresh-ic log-ic" data-open="quick-log" aria-label="Log food, water, weight or mood">${icon("plus")}</button>` : ""}${freshChip()}`;
  },
  render() {
    const t = D.today;
    const rec = t.recommendation;
    const callCls = (CALL_LABEL[rec.call] || [rec.call, ""])[1];
    const r = t.rings;
    const tile = (kind, href, v, label) => `<a class="ring-tile" href="${href}">${ring(kind, v, { label, sub: v && v.status === "stale" ? "stale" : "" })}<span class="label">${label}</span></a>`;
    const hero = `<section class="t-hero"><div class="card hero-card">
      <div class="rings">${tile("strain", "#/strain", r.strain, "Strain")}${tile("recovery", "#/recovery", r.recovery, "Recovery")}${tile("sleep", "#/sleep", r.sleep, "Sleep")}</div>
      <button class="coach-note ${callCls}" data-open="factors" aria-label="Why this call"><span class="coach-t">${esc(t.coach_line)}</span><span class="coach-x" aria-hidden="true">${icon("expand")}</span></button></div></section>`;

    const adapts = t.adaptations || [];
    const suggest = a => `<div class="suggest"><span class="ic-sm">${icon("sparkles")}</span><div class="grow"><b>${esc(a.title)}</b><span>${esc(a.sub)}</span></div>${adaptButtons(a)}</div>`;
    const planRows = t.plan.map(s => sessionRow(s) + adapts.filter(a => a.session_id === s.id).map(suggest).join("")).join("");
    const orphan = adapts.filter(a => !t.plan.some(s => s.id === a.session_id)).map(suggest).join("");
    const bigday = (t.big_day || []).map((b, i) => `<button class="li" data-open="bigday" data-arg="${i}"><span class="icon-dot" style="color:var(--accent)">${icon("flame")}</span><div class="grow"><div class="t">Big day brief</div><div class="s">${esc(b.evening.bedtime ? "Bed by " + b.evening.bedtime : b.title)}</div></div>${goArrow()}</button>`).join("");
    const conflicts = t.conflicts.map(c => `<div class="li"><span class="icon-dot" style="color:var(--info)">${icon("event")}</span><div class="grow"><div class="t">${esc(c.event || "Calendar")}</div><div class="s">${esc(c.reason)}</div></div></div>`).join("");
    const plan = `<section class="t-plan">${sectionTitle("Today's plan", `<a class="link" href="#/training?tab=plan">Week</a>`)}<div class="card">
      ${t.plan.length || orphan ? `<div class="list">${planRows}${orphan}${bigday}${conflicts}</div>` : `<p class="small muted" style="margin:0">${D.plans.has_template || D.plans.has_explicit_plan ? "Rest day" : STR.noPlan}</p>`}</div></section>`;

    const sl = t.stress_latest, eb = t.energy;
    const stress = `<section class="t-stress">${sectionTitle("Stress & energy")}<div class="stack"><a class="card" href="#/recovery">
      <div class="card-top"><span class="ttl"><i class="live-dot"></i>${sl && sl.date !== D.meta.build_date ? "Stress on " + esc(fmt.date(sl.date, { weekday: "long" })) : "Today's stress"}</span>${goArrow()}</div>
      <div class="sub">Estimate${sl && isNum(sl.hours) ? ` · ${fmt.n(sl.hours)} h of daytime heart rate` : ""}</div>
      ${sl ? `<div class="trio"><div><b style="color:var(--strain)">${fmt.n(sl.high)}</b><span>Highest</span></div><div><b style="color:var(--prior)">${fmt.n(sl.low)}</b><span>Lowest</span></div><div><b style="color:var(--recovery-2)">${fmt.n(sl.avg)}</b><span>Average</span></div></div>` : `<p class="small muted" style="margin:10px 0 0">Not enough daytime heart rate yet</p>`}</a>
      ${eb ? `<a class="card energy-card" href="#/recovery" aria-label="Energy bank ${fmt.n(eb.current)} percent"><span class="bolt">${icon("bolt-fill")}</span>${energyTicks(eb.current)}<b>${fmt.n(eb.current)}%</b></a>` : ""}</div></section>`;

    const ld = t.load, st = ld.status || {};
    const ctlSeries = seriesTail(D.training.pmc.series, "ctl", 42);
    const statusColor = { productive: "var(--ok)", maintaining: "var(--load)", fatigued: "var(--warn)", overreaching: "var(--bad)", detraining: "var(--text-2)" }[st.v] || "var(--text-2)";
    const load = `<section class="t-load">${sectionTitle("Cardio load")}<a class="card load-card" href="#/training"><div class="load-l"><div class="tile-h">${icon("heart-rate-monitor")}<span>Fitness</span></div>
      <div class="tile-v big">${isNum(st.ctl) ? fmt.n(st.ctl) : "—"}</div><div class="tile-st" style="color:${statusColor}">${st.v ? esc(fmt.sport(st.v)) : "Calibrating"}</div></div>
      <div class="load-spark">${sparkline(ctlSeries, statusColor, 72)}</div>${goArrow()}</a></section>`;

    const sy = t.since_yesterday;
    const hrvPts = (D.body.metrics.hrv_sdnn_ms || {}).points, rhrPts = (D.body.metrics.resting_hr_bpm || {}).points;
    const health = `<section class="t-health">${sectionTitle("Health monitor")}<div class="grid g2 tiles">
      ${healthTile("HRV", "heart", isNum(sy.hrv.v) ? fmt.n(sy.hrv.v) : null, "ms", sy.hrv.delta, true, seriesTail(hrvPts, "v", 21), "var(--recovery)", "#/recovery", " ms")}
      ${healthTile("Resting HR", "activities", isNum(sy.rhr.v) ? fmt.n(sy.rhr.v) : null, "bpm", sy.rhr.delta, false, seriesTail(rhrPts, "v", 21), "var(--bad)", "#/recovery", " bpm")}
      ${healthTile("Sleep", "sleep", isNum(sy.sleep.v) ? fmt.hm(sy.sleep.v) : null, "", isNum(sy.sleep.delta) ? Math.round(sy.sleep.delta) : null, true, seriesTail(D.sleep.history, "asleep_min", 21), "var(--sleep-2)", "#/sleep", "m")}
      ${healthTile("Weight", "scale", isNum(sy.weight.v) ? fmt.kgNum(sy.weight.v) : null, fmt.wUnit(), isNum(sy.weight.delta) ? (IMPERIAL ? sy.weight.delta * 2.20462 : sy.weight.delta) : null, null, seriesTail(D.body.weight.median_7d, "v", 30), "var(--accent)", "#/body", " " + fmt.wUnit())}
      ${tempTile(sy.temp)}
      ${healthTile("Blood oxygen", "lungs", isNum(sy.spo2.v) ? fmt.n(sy.spo2.v) : null, "%", sy.spo2.delta, null, seriesTail((D.body.metrics.spo2_pct || {}).points, "v", 21), "var(--info)", "#/body?tab=charts", "%")}</div></section>`;

    const days = Object.keys(D.timeline).sort();
    const tday = days.includes(D.meta.build_date) ? D.meta.build_date : days[days.length - 1];
    const items = (D.timeline[tday] || []).slice().sort((a, b) => String(b.t).localeCompare(String(a.t)));
    const timeline = `<section class="t-timeline">${sectionTitle("Timeline", items.length ? `<span class="small muted">${items.length} events</span>` : "")}<div class="card">
      ${items.length ? `<div class="list">${items.slice(0, 3).map(timelineRow).join("")}</div><a class="btn secondary block" href="#/timeline">View timeline</a>` : `<p class="small muted" style="margin:0">Nothing recorded yet today</p>`}</div></section>`;

    const yday = `<section class="t-yday">${sectionTitle("Yesterday", `<a class="link" href="#/activities">All</a>`)}<div class="card">${t.yesterday.length ? `<div class="list">${t.yesterday.map(activityRow).join("")}</div>` : `<p class="small muted" style="margin:0">No workouts</p>`}</div></section>`;
    const goals = `<section class="t-goals">${sectionTitle("Goals", `<a class="link" href="#/goals">All</a>`)}<div class="card">${t.goals.length ? t.goals.map(g => goalRow(g)).join("") : `<p class="small muted" style="margin:0">${STR.noGoals}</p>`}</div></section>`;
    const head = `<h2 class="page-title">${esc(D.meta.build_date === t.date ? "Today, " + fmt.date(t.date, { day: "numeric", month: "long" }) : fmt.dateLong(t.date))}</h2>`;
    return `${head}${todayWidgetRow()}<div class="today">
      <div class="today-main">${hero}${stress}${load}${health}</div>
      <div class="today-side">${plan}${goals}${timeline}${yday}</div></div>`;
  },
  after() { drawCharts(); },
};

const TL_ICON = { sleep: ["sleep", "var(--sleep)"], workout: ["run", "var(--run)"], meal: ["meal", "var(--carbs)"], measurement: ["scale", "var(--accent)"], journal: ["note", "var(--text-2)"], event: ["event", "var(--info)"], planned: ["calendar", "var(--text-2)"], score: ["recovery", "var(--recovery)"] };
function timelineRow(i) {
  const [ic, col] = TL_ICON[i.type] || ["activities", "var(--text-2)"];
  const tag = i.id && i.type === "workout" ? `a href="#/activity/${encodeURIComponent(i.id)}"` : "div";
  return `<${tag} class="li tl-row"><span class="tl-ic" style="--c:${col}">${icon(ic)}</span><div class="grow"><div class="tl-time">${fmt.time(i.t)}</div><div class="t">${esc(i.title)}</div>${i.detail ? `<div class="s">${esc(i.detail)}</div>` : ""}</div>${i.id && i.type === "workout" ? goArrow() : ""}</${tag.split(" ")[0]}>`;
}


AG.screens.strain = {
  title: "Strain", parent: "#/today", nav: "today",
  render() {
    const s = D.strain;
    const rng = chipVal("strain-range", "30");
    const rows = sliceDays(s.history, rangeDays(rng));
    const nr = s.normal_range;
    const todayActs = D.today.today_activities.concat(D.today.yesterday);
    const strainAbout = `Strain turns your daily training load into a percentage${s.score.k_method === "personal_p90" ? " on your personal scale" : ""}. ${nr ? `Your normal range is ${nr.low}–${nr.high}%.` : "Your normal range appears after 14 days."}`;
    const m = D.body.metrics, tail = (k, n = 30) => seriesTail((m[k] || {}).points, "v", n);
    const latest = k => m[k] && isNum(m[k].latest) ? m[k] : null;
    const ae = latest("active_energy_kcal"), stp = latest("steps");
    const hero = `<div class="card score-hero">${cardHead(esc(fmt.dateLong(D.meta.build_date)), "", strainAbout, s.score)}
      <div class="score-hero-b">${ring("strain", s.score, { lg: true, label: "Strain" })}
      <div class="score-meta">${s.score.note ? `<p class="small muted">${esc(s.score.note)}</p>` : ""}${nr ? `<div class="kv"><span>Normal range</span><b>${nr.low}–${nr.high}%</b></div>` : ""}</div></div></div>`;
    const hist = `<div class="card">${cardHead("History", seg("strain-range", RANGES_DWMY, rng))}
      ${rows.length ? chart({ type: "bar", id: "strain-ch", label: "Daily strain percent", x: rows.map(r => r.date), series: [{ name: "Strain", color: "var(--strain)", values: rows.map(r => r.v) }],
        band: nr ? { low: nr.low, high: nr.high, color: "color-mix(in srgb, var(--strain) 16%, transparent)" } : null, yMin: 0, yMax: 100, fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%", range: rangeLabel(rows), h: 190 }) : empty(STR.noData)}</div>`;
    const trends = `${sectionTitle("Trends")}<div class="trends-wrap"><div class="trends two">
      ${trendRow({ label: "Exercise today", icon: "clock", value: fmt.hm(s.exercise_min) })}
      ${trendRow({ label: "Daytime HR", icon: "heart", value: isNum(s.daytime_hr) ? fmt.n(s.daytime_hr) : null, unit: "bpm", status: isNum(s.daytime_hr) ? "" : statusLine("Not synced yet", null) })}
      ${ae ? trendRow({ label: "Active energy", icon: "flame", value: fmt.n(ae.latest), unit: "kcal", status: statusLine(`${fmt.dow(ae.latest_date)} · avg ${fmt.n(ae.avg_7)} kcal`, null), spark: tail("active_energy_kcal"), color: "var(--strain)" }) : ""}
      ${stp ? trendRow({ label: "Steps", icon: "walk", value: fmt.n(stp.latest), status: statusLine(`${fmt.dow(stp.latest_date)} · avg ${fmt.n(stp.avg_7)}`, null), spark: tail("steps"), color: "var(--strain-2)" }) : ""}</div></div>`;
    const work = `${sectionTitle("Workout strain")}<div class="card">${todayActs.length ? `<div class="list">${todayActs.map(a => `<a class="li act-row" href="#/activity/${encodeURIComponent(a.id)}"><span class="icon-dot round" style="color:${sportColor(a.family)}">${sportIcon(a.family)}</span><div class="grow"><div class="tl-time">${fmt.dow(a.date)} ${fmt.date(a.date)}</div><div class="t">${esc(a.name)}</div></div><b class="num">${isNum(a.strain) ? fmt.n(a.strain) + "%" : "—"}</b><span class="go">${icon("arrow")}</span></a>`).join("")}</div>` : `<p class="small muted" style="margin:0">No workouts today or yesterday</p>`}</div>`;
    return `<div class="cols"><div class="stack">${hero}${hist}</div><div class="stack">${trends}${work}</div></div>`;
  },
  after() { drawCharts(); },
};

AG.screens.timeline = {
  title: "Timeline", parent: "#/today", nav: "today",
  render() {
    const days = Object.keys(D.timeline).sort().reverse();
    const sel = chipVal("tl-day", days[0]);
    const items = (D.timeline[sel] || []).slice().sort((a, b) => String(a.t).localeCompare(String(b.t)));
    let lastHour = null;
    const rows = items.map(i => {
      const [ic, col] = TL_ICON[i.type] || ["activities", "var(--text-2)"];
      const h = fmt.time(i.t).slice(0, 2);
      const mark = h !== lastHour ? `<div class="tlx-hour"><span>${h}:00</span></div>` : "";
      lastHour = h;
      const tag = i.id && i.type === "workout" ? `a href="#/activity/${encodeURIComponent(i.id)}"` : "div";
      return `${mark}<div class="tlx-item"><span class="tlx-time">${fmt.time(i.t)}</span><span class="tlx-dot" style="background:${col}"></span>
        <${tag} class="tlx-card"><span class="tl-ic" style="--c:${col}">${icon(ic)}</span><div class="grow"><div class="t">${esc(i.title)}</div>${i.detail ? `<div class="s">${esc(i.detail)}</div>` : ""}</div>${i.id && i.type === "workout" ? `<span class="tl-go">${icon("arrow")}</span>` : ""}</${tag.split(" ")[0]}></div>`;
    }).join("");
    return `${tabs("tl-day", days.slice(0, 14).map(d => [d, d === D.meta.build_date ? "Today" : fmt.dow(d) + " " + fmt.date(d, { day: "numeric" })]), sel)}
      ${items.length ? `<div class="tlx">${rows}</div>` : `<div class="card">${empty("Nothing recorded for this day")}</div>`}`;
  },
};
