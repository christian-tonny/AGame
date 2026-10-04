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
    ${adapt.map(a => `<div class="suggest" style="margin-top:12px"><div class="grow"><b>${esc(adaptText(a))}</b><span>${esc(a.reason)}</span></div>${adaptButtons(a)}</div>`).join("")}
    ${s.steps && s.steps.length ? sectionTitle("Steps") + stepList(s.steps) : ""}
    ${s.workout_id ? `<a class="btn secondary" style="margin-top:12px;width:100%" href="#/activity/${encodeURIComponent(s.workout_id)}">Open completed activity</a>` : ""}
    ${alts.length ? sectionTitle("Workout Wizard") + `<div class="list">${alts.map(a => `<div class="li"><div class="grow"><div class="t">${esc(a.title)}</div><div class="s">${esc(a.note)}</div></div><div class="r small">${a.duration_s ? fmt.mins(a.duration_s) : "—"}<div class="cap">${isNum(a.est_load) ? "load ~" + fmt.n(a.est_load) : ""}</div></div>${AG.online && s.date >= D.meta.build_date ? `<button type="button" class="btn sm secondary" data-wizard="${esc(a.kind)}" data-sid="${esc(s.id)}">Use</button>` : ""}</div>`).join("")}</div>
      <p class="cap">Alternatives keep the rest of your week unchanged. Choosing one updates plans.json through your AGame server.</p>${offlineNote()}` : ""}
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
function adaptText(a) {
  const lbl = t => (D.plans.this_week.sessions.find(s => s.type === t) || {}).label || ({ AER: "Aerobic", REC: "Recovery", REST: "Rest", MOB: "Mobility" }[t] || t);
  if (a.action === "swap") return `Swap to ${lbl(a.to)}`;
  if (a.action === "shorten") return `Shorten to ${Math.round(a.factor * 100)}%`;
  if (a.action === "move") return `Move to ${fmt.dow(a.to_date)} ${fmt.date(a.to_date)}`;
  if (a.action === "adjust_pace") return `Run ${a.pct_slower}% slower`;
  return fmt.sport(a.action);
}

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
  openSheet("Why this call", `<p class="small"><b>${esc((CALL_LABEL[r.call] || [r.call])[0])}</b> · ${esc(r.why)}</p><div class="list">${r.factors.map(factorRow).join("") || empty(STR.noData)}</div>
    <p class="cap" style="margin-top:12px">Thresholds come from config (recovery bands, form, sleep debt). Fitness information, not medical advice.</p>`);
};

const FACTOR_PHRASE = { sleep: "short sleep", sleep_debt: "sleep debt", hrv: "a dip in HRV", rhr: "a raised resting heart rate", tsb: "built-up fatigue", ramp: "a fast ramp in load", strain: "yesterday's strain", status: "how you're feeling", resp: "a higher breathing rate" };
function joinPhrases(list) { return list.length < 2 ? list.join("") : list.slice(0, -1).join(", ") + " and " + list[list.length - 1]; }
/* One plain sentence that says what to do and why, from the computed call and factors. */
function coachingLine(rec, t) {
  const hurting = rec.factors.filter(f => f.direction === "hurting").slice(0, 2).map(f => FACTOR_PHRASE[f.id] || f.label.toLowerCase());
  const helping = rec.factors.filter(f => f.direction === "helping").slice(0, 1).map(f => FACTOR_PHRASE[f.id] ? null : f.label.toLowerCase()).filter(Boolean);
  const session = (t.plan || []).find(s => s.type !== "REST");
  const what = session ? (session.title || session.label || "today's session").toLowerCase() : "today";
  if (rec.call === "reduce") return `${hurting.length ? cap1(joinPhrases(hurting)) + (hurting.length > 1 ? " are" : " is") + " holding your recovery back. " : ""}Keep ${what === "today" ? "today" : "the " + what} easy and conversational.`;
  if (rec.call === "rest") return `${hurting.length ? cap1(joinPhrases(hurting)) + (hurting.length > 1 ? " are" : " is") + " weighing on you. " : ""}Take the day off and let your body catch up.`;
  if (rec.call === "train") return `You're recovered${helping.length ? "" : " and ready"}. ${session ? "Go ahead with the " + what + " as planned." : "A good day for a quality session."}`;
  if (rec.call === "rest_day") return "Rest day on your plan. Enjoy it, and get to bed on time.";
  if (rec.call === "open") return "Nothing planned today. Move if you feel like it.";
  return t.action ? t.action.text : rec.why;
}
function cap1(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }
function seriesTail(points, key, n) { return (points || []).slice(-n).map(p => isNum(p[key]) ? p[key] : null); }

function healthTile(label, ic, value, unit, d, betterHigher, spark, color, href, dUnit = "") {
  const good = !isNum(d) || d === 0 || betterHigher === null ? null : (d > 0) === betterHigher;
  const status = isNum(d) && d !== 0 ? `<span class="tile-st ${good === null ? "muted" : good ? "up" : "down"}">${icon(d > 0 ? "caret-up" : "caret-down", "tiny")}${d > 0 ? "+" : "−"}${Math.abs(d) < 10 && d % 1 ? fmt.n(Math.abs(d), 1) : fmt.n(Math.abs(d))}${dUnit} vs yesterday</span>` : `<span class="tile-st muted">No change</span>`;
  return `<a class="card tile" href="${href}"><div class="tile-h">${icon(ic)}<span>${esc(label)}</span></div>
    <div class="tile-v">${value === null ? "—" : value}${value !== null && unit ? `<small>${esc(unit)}</small>` : ""}</div>${value === null ? `<span class="tile-st muted">No data</span>` : status}
    <div class="tile-spark">${spark ? sparkline(spark, color, 30) : ""}</div></a>`;
}

AG.screens.today = {
  title: "Today",
  render() {
    const t = D.today;
    const rec = t.recommendation;
    const [callTxt, callCls] = CALL_LABEL[rec.call] || [rec.call, ""];
    const r = t.rings;
    const tile = (kind, href, v, label) => `<a class="ring-tile" href="${href}">${ring(kind, v, { label, sub: v && v.status === "stale" ? "stale" : "" })}<span class="label">${label}</span></a>`;
    const hero = `<div class="card hero-card">
      <div class="rings">${tile("strain", "#/strain", r.strain, "Strain")}${tile("recovery", "#/recovery", r.recovery, "Recovery")}${tile("sleep", "#/sleep", r.sleep, "Sleep")}</div>
      <button class="coach-note ${callCls}" data-open="factors"><span class="coach-k">${icon("sparkles")}${esc(callTxt)}</span><span class="coach-t">${esc(coachingLine(rec, t))}</span></button></div>`;

    const adapts = t.adaptations || [];
    const suggest = a => `<div class="suggest"><div class="grow"><b>${esc(adaptText(a))}</b><span>${esc(a.reason)}</span></div>${adaptButtons(a)}</div>`;
    const planRows = t.plan.map(s => sessionRow(s) + adapts.filter(a => a.session_id === s.id).map(suggest).join("")).join("");
    const orphan = adapts.filter(a => !t.plan.some(s => s.id === a.session_id)).map(suggest).join("");
    const bigday = (t.big_day || []).map((b, i) => `<button class="li chev" data-open="bigday" data-arg="${i}"><span class="icon-dot" style="color:var(--accent)">${icon("flame")}</span><div class="grow"><div class="t">Big day brief</div><div class="s">${esc(b.evening.bedtime ? "Bed by " + b.evening.bedtime : b.title)}${b.morning.call ? " · " + (b.morning.call === "go" ? "Go" : "Adjust") : ""}</div></div></button>`).join("");
    const conflicts = t.conflicts.map(c => `<div class="li"><span class="icon-dot" style="color:var(--info)">${icon("event")}</span><div class="grow"><div class="t">${esc(c.event || "Calendar")}</div><div class="s">${esc(c.reason)}</div></div></div>`).join("");
    const plan = `${sectionTitle("Today's plan", `<a class="link" href="#/training?tab=plan">Week</a>`)}<div class="card">
      ${t.plan.length || orphan ? `<div class="list">${planRows}${orphan}${bigday}${conflicts}</div>` : `<p class="small muted" style="margin:0">${D.plans.has_template || D.plans.has_explicit_plan ? "Rest day" : STR.noPlan}</p>`}</div>`;

    const sl = t.stress_latest, eb = t.energy;
    const stress = `${sectionTitle("Stress & energy")}<a class="card" href="#/recovery">
      <div class="tile-h">${icon("heart")}<span>${sl && sl.date !== D.meta.build_date ? "Stress · " + esc(fmt.date(sl.date)) : "Today's stress"}</span><span class="est-tag">Estimate</span></div>
      ${sl ? `<div class="trio"><div><b style="color:var(--strain)">${fmt.n(sl.high)}</b><span>Highest</span></div><div><b style="color:var(--prior)">${fmt.n(sl.low)}</b><span>Lowest</span></div><div><b style="color:var(--recovery-2)">${fmt.n(sl.avg)}</b><span>Average</span></div></div>` : `<p class="small muted">Not enough daytime heart rate yet</p>`}</a>
      ${eb ? `<a class="card energy-card" href="#/recovery">${icon("bolt")}<div class="energy" role="img" aria-label="Energy ${fmt.n(eb.current)} percent"><i style="width:${eb.current}%"></i></div><b>${fmt.n(eb.current)}%</b></a>` : ""}`;

    const ld = t.load, st = ld.status || {};
    const ctlSeries = seriesTail(D.training.pmc.series, "ctl", 42);
    const statusColor = { productive: "var(--ok)", maintaining: "var(--sleep-2)", fatigued: "var(--warn)", overreaching: "var(--bad)", detraining: "var(--text-2)" }[st.v] || "var(--text-2)";
    const load = `${sectionTitle("Cardio load")}<a class="card load-card" href="#/training"><div class="grow"><div class="tile-h">${icon("activities")}<span>Fitness</span></div>
      <div class="tile-v">${isNum(st.ctl) ? fmt.n(st.ctl) : "—"}</div><div class="tile-st" style="color:${statusColor}">${st.v ? esc(fmt.sport(st.v)) : "Calibrating"}</div>
      <div class="small muted" style="margin-top:6px">Form ${ld.tsb && isNum(ld.tsb.v) ? fmt.signed(ld.tsb.v, 0) : "—"} · Fatigue ${isNum(st.atl) ? fmt.n(st.atl) : "—"}</div></div>
      <div class="load-spark">${sparkline(ctlSeries, statusColor, 64)}</div></a>`;

    const sy = t.since_yesterday;
    const hrvPts = (D.body.metrics.hrv_sdnn_ms || {}).points, rhrPts = (D.body.metrics.resting_hr_bpm || {}).points;
    const health = `${sectionTitle("Health monitor")}<div class="grid g2 tiles">
      ${healthTile("HRV", "heart", isNum(sy.hrv.v) ? fmt.n(sy.hrv.v) : null, "ms", sy.hrv.delta, true, seriesTail(hrvPts, "v", 21), "var(--recovery)", "#/recovery")}
      ${healthTile("Resting HR", "activities", isNum(sy.rhr.v) ? fmt.n(sy.rhr.v) : null, "bpm", sy.rhr.delta, false, seriesTail(rhrPts, "v", 21), "var(--bad)", "#/recovery")}
      ${healthTile("Sleep", "sleep", isNum(sy.sleep.v) ? fmt.hm(sy.sleep.v) : null, "", isNum(sy.sleep.delta) ? Math.round(sy.sleep.delta) : null, true, seriesTail(D.sleep.history, "asleep_min", 21), "var(--sleep)", "#/sleep", "m")}
      ${healthTile("Weight", "scale", isNum(sy.weight.v) ? fmt.kgNum(sy.weight.v) : null, fmt.wUnit(), isNum(sy.weight.delta) ? (IMPERIAL ? sy.weight.delta * 2.20462 : sy.weight.delta) : null, null, seriesTail(D.body.weight.points, "v", 30), "var(--accent)", "#/body")}</div>`;

    const days = Object.keys(D.timeline).sort();
    const tday = days.includes(D.meta.build_date) ? D.meta.build_date : days[days.length - 1];
    const items = (D.timeline[tday] || []).slice().sort((a, b) => String(b.t).localeCompare(String(a.t)));
    const timeline = `${sectionTitle("Timeline", items.length ? `<span class="small muted">${items.length} events</span>` : "")}<div class="card">
      ${items.length ? `<div class="list">${items.slice(0, 3).map(timelineRow).join("")}</div><a class="btn secondary block" href="#/timeline">View timeline</a>` : `<p class="small muted" style="margin:0">Nothing recorded yet today</p>`}</div>`;

    const yday = `${sectionTitle("Yesterday", `<a class="link" href="#/activities">All</a>`)}<div class="card">${t.yesterday.length ? `<div class="list">${t.yesterday.map(activityRow).join("")}</div>` : `<p class="small muted" style="margin:0">No workouts</p>`}</div>`;
    const goals = `${sectionTitle("Goals", `<a class="link" href="#/goals">All</a>`)}<div class="card">${t.goals.length ? t.goals.map(g => goalRow(g)).join("") : `<p class="small muted" style="margin:0">${STR.noGoals}</p>`}</div>`;
    const fc = (t.plan || []).find(s => isNum(s.forecast_temp_c));
    const head = `<div class="page-head"><h2 class="page-title">${esc(fmt.dateLong(t.date))}</h2><div class="row">${t.status && t.status.status !== "normal" ? `<a class="pill" href="#/journal">${esc(fmt.sport(t.status.status))}</a>` : ""}${fc ? `<span class="pill">${esc(fmt.temp(fc.forecast_temp_c))}</span>` : ""}${freshChip()}</div></div>`;
    return `${head}${todayWidgetRow()}<div class="cols c21">
      <div class="stack">${hero}${plan}${stress}${load}${health}</div>
      <div class="stack">${goals}${timeline}${yday}</div></div>`;
  },
  after() { drawCharts(); },
};

const TL_ICON = { sleep: ["sleep", "var(--sleep)"], workout: ["run", "var(--run)"], meal: ["meal", "var(--carbs)"], measurement: ["scale", "var(--accent)"], journal: ["note", "var(--text-2)"], event: ["event", "var(--info)"], planned: ["calendar", "var(--text-2)"], score: ["recovery", "var(--recovery)"] };
function timelineRow(i) {
  const [ic, col] = TL_ICON[i.type] || ["activities", "var(--text-2)"];
  const tag = i.id && i.type === "workout" ? `a href="#/activity/${encodeURIComponent(i.id)}"` : "div";
  return `<${tag} class="li tl-row"><span class="tl-ic" style="color:${col}">${icon(ic)}</span><div class="grow"><div class="tl-time">${fmt.time(i.t)}</div><div class="t">${esc(i.title)}</div>${i.detail ? `<div class="s">${esc(i.detail)}</div>` : ""}</div>${i.id && i.type === "workout" ? `<span class="tl-go">${icon("arrow")}</span>` : ""}</${tag.split(" ")[0]}>`;
}


AG.screens.strain = {
  title: "Strain", parent: "#/today", nav: "today",
  render() {
    const s = D.strain;
    const rng = chipVal("strain-range", "90");
    const rows = sliceDays(s.history, rangeDays(rng));
    const nr = s.normal_range;
    const todayActs = D.today.today_activities.concat(D.today.yesterday);
    const strainAbout = `Strain turns your daily training load into a percentage${s.score.k_method === "personal_p90" ? " on your personal scale" : ""}. ${nr ? `Your normal range is ${nr.low}–${nr.high}%.` : "Your normal range appears after 14 days."}`;
    return `<div class="cols"><div class="stack"><div class="card">${cardHead(esc(fmt.dateLong(D.meta.build_date)), prov(s.score, "Strain"), strainAbout)}<div class="spread"><div class="stat hero"><span class="v">${val(s.score, 0, "%")}</span>${s.score.note ? `<span class="cap">${esc(s.score.note)}</span>` : ""}</div>
      ${nr ? `<div style="text-align:right"><div class="small muted">Normal range</div><div style="font-weight:700">${nr.low}–${nr.high}%</div></div>` : ""}</div></div>
      <div class="card">${cardHead("History", seg("strain-range", RANGES_DWMY, rng))}
      ${rows.length ? chart({ id: "strain-ch", label: "Daily strain percent", x: rows.map(r => r.date), series: [{ name: "Strain", color: "var(--strain)", values: rows.map(r => r.v), dots: rows.length < 40 }],
        band: nr ? { low: nr.low, high: nr.high, color: "color-mix(in srgb, var(--strain) 22%, transparent)", name: "Your normal range" } : null, yMin: 0, yMax: 100, fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%", range: rangeLabel(rows), h: 190 }) : empty(STR.noData)}</div></div>
      <div class="stack"><div class="grid g2"><div class="card">${stat("Exercise today", fmt.hm(s.exercise_min))}</div><div class="card">${stat("Daytime HR", isNum(s.daytime_hr) ? fmt.n(s.daytime_hr) : "—", "bpm")}</div></div>
      <div class="card">${cardHead("Workout strain")}${todayActs.length ? `<div class="list">${todayActs.map(a => `<a class="li" href="#/activity/${encodeURIComponent(a.id)}"><div class="grow"><div class="t">${esc(a.name)}</div><div class="s">${fmt.date(a.date)}</div></div><div class="r">${isNum(a.strain) ? fmt.n(a.strain) + "%" : "—"}</div></a>`).join("")}</div>` : `<p class="small muted" style="margin:0">No workouts today or yesterday</p>`}
</div></div></div>`;
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
        <${tag} class="tlx-card"><span class="tl-ic" style="color:${col}">${icon(ic)}</span><div class="grow"><div class="t">${esc(i.title)}</div>${i.detail ? `<div class="s">${esc(i.detail)}</div>` : ""}</div>${i.id && i.type === "workout" ? `<span class="tl-go">${icon("arrow")}</span>` : ""}</${tag.split(" ")[0]}></div>`;
    }).join("");
    return `${tabs("tl-day", days.slice(0, 14).map(d => [d, d === D.meta.build_date ? "Today" : fmt.dow(d) + " " + fmt.date(d, { day: "numeric" })]), sel)}
      ${items.length ? `<div class="tlx">${rows}</div>` : `<div class="card">${empty("Nothing recorded for this day")}</div>`}`;
  },
};
