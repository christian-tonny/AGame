/* Recovery (readiness, HRV, RHR, stress, energy, prehab) and Sleep */
"use strict";

AG.screens.recovery = {
  title: "Recovery",
  render() {
    const R = D.recovery;
    const sc = R.score;
    const t = R.today;
    const rng = chipVal("rec-range", "90");
    const hist = sliceDays(R.history, rangeDays(rng));
    const hrvTrend = D.body.metrics.hrv_sdnn_ms, rhrTrend = D.body.metrics.resting_hr_bpm, rrTrend = D.body.metrics.respiratory_rate_brpm;
    const comps = t ? t.components : {};
    const tile = (c, label, unit, ic, color, pts) => `<div class="card tile"><div class="tile-h">${icon(ic)}<span>${label}</span></div>${c ? `<div class="tile-v">${fmt.n(c.value, 1)}<small>${unit}</small></div>${statusLine(`usual ${fmt.n(c.baseline, 1)} ${unit}`, c.z > 0, c.value >= c.baseline ? "up" : "down")}` : `<div class="tile-v">—</div>${statusLine((t && t.missing.find(m => m.id === (ic === "heart" ? "hrv" : "rhr")) || {}).reason || "No data", null)}`}<div class="tile-spark">${pts ? sparkline(seriesTail(pts, "v", 21), color, 40) : ""}</div></div>`;
    const headline = t ? ({ high: "High recovery", low: "Low recovery" }[sc.band] || "Moderate recovery") : "";
    const recAbout = "Recovery compares last night's HRV, resting heart rate and sleep debt with your own 60-day baseline.";
    const hero = `<div class="card score-hero">${cardHead(esc(sc.date ? fmt.dateLong(sc.date) : fmt.dateLong(D.meta.build_date)), "", recAbout, sc)}
      <div class="score-hero-b">${ring("recovery", sc, { lg: true, label: "Recovery" })}
      <div class="score-meta">${headline ? `<div class="hero-h">${headline}</div>` : ""}<p class="small muted">${[sc.confidence ? fmt.sport(sc.confidence) + " confidence" : "", isNum(sc.coverage) && sc.coverage < 1 ? fmt.n(sc.coverage * 100) + "% of inputs" : ""].filter(Boolean).join(" · ")}</p>${stLine(sc)}</div></div></div>`;
    const compRows = t ? Object.entries(comps).map(([k, c]) => `<div class="factor ${c.contribution > 1 ? "helping" : c.contribution < -1 ? "hurting" : "neutral"}"><span class="ic">${icon(c.contribution > 1 ? "up" : c.contribution < -1 ? "down" : "minus")}</span><div class="grow"><div class="t">${esc(c.label)}</div><div class="s">${fmt.signed(c.contribution, 1)} points · ${fmt.n(c.weight * 100)}% weight</div></div><span class="r">${k === "sleep_debt" ? fmt.hm(c.value) : fmt.n(c.value, 1) + " " + c.unit}</span></div>`).join("") +
      t.missing.map(m => `<div class="factor neutral"><span class="ic">${icon("question")}</span><div class="grow"><div class="t">${esc(fmt.sport(m.id))}</div><div class="s">Excluded · ${esc(m.reason)}</div></div><span class="r">—</span></div>`).join("") : "";
    const recChart = hist.length ? chart({ id: "rec-ch", label: "Recovery score history", x: hist.map(h => h.date), h: 170, yMin: 0, yMax: 100, gapMs: 2.5 * 86400000,
      series: [{ name: "Recovery", color: "var(--recovery)", values: hist.map(h => h.score), dots: hist.length < 45 }],
      band: R.normal_range ? { low: R.normal_range.low, high: R.normal_range.high, color: "color-mix(in srgb, var(--recovery) 18%, transparent)", name: "Your normal range" } : null,
      fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%", range: rangeLabel(hist) }) : empty(STR.noData);
    const trendChart = (tr, name, color, unit, betterHigher) => {
      if (!tr) return empty(`No ${name} samples`);
      const pts = sliceDays(tr.points, rangeDays(rng));
      const avg7 = pts.map((p, i) => { const w = pts.slice(Math.max(0, i - 6), i + 1).map(x => x.v); return w.reduce((a, b) => a + b, 0) / w.length; });
      return chart({ id: "tr-" + tr.id, label: name + " trend", x: pts.map(p => p.date), h: 140, gapMs: 3.5 * 86400000,
        series: [{ name, color, values: pts.map(p => p.v), dots: true, noLine: true, dotR: 2 }, { name: "7-day average", color, values: avg7, width: 2.2 }],
        fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + unit, legend: false });
    };
    const st = D.stress;
    const eb = D.energy;
    const ph = D.plans.prehab, phl = D.plans.prehab_log;
    return `<div class="cols"><div class="stack">${hero}<div class="grid g2 tiles">${tile(comps.hrv, "Resting HRV", "ms", "heart", "var(--recovery)", (hrvTrend || {}).points)}${tile(comps.rhr, "Resting HR", "bpm", "activities", "var(--bad)", (rhrTrend || {}).points)}</div>
      <div class="card">${cardHead("What's driving it", "", "Each input is compared with your own rolling baseline. Missing inputs are excluded, not counted as zero.")}<div class="list">${compRows || empty(STR.noData, sc.note)}</div></div>
      <div class="card">${cardHead("Helping & hurting", `<a class="link" href="#/coach">More</a>`)}${helpingList(["30", "90"].includes(chipVal("hh-win", "90")) ? chipVal("hh-win", "90") : "90", 4)}</div>
      <div class="card">${cardHead("Stress", badge((st.latest && st.latest.date !== D.meta.build_date ? fmt.date(st.latest.date) + " · " : "") + "Estimate", "est"), "Estimated from daytime heart rate against your resting baseline, excluding workouts and sleep.")}${st.latest ? chart({ id: "stress-h", type: "bar", label: "Hourly stress estimate", x: st.latest.hourly.map(h => h.hour), h: 120, yMin: 0, yMax: 100,
        series: [{ name: "Stress", color: (i, v) => v >= 67 ? "var(--bad)" : v >= 34 ? "var(--warn)" : "var(--ok)", values: st.latest.hourly.map(h => h.v) }], fmtX: h => `${String(h).padStart(2, "0")}:00`, fmtY: v => fmt.n(v) }) : empty("Not enough daytime heart-rate samples", "Stress is estimated only from real daytime HR samples")}</div>
      <div class="card">${cardHead("Energy bank", eb ? `<span class="small muted">${fmt.n(eb.current)}% at ${fmt.time(eb.as_of)}</span>` : "", "Charged by recovery and sleep, drained by strain and stress. It stops at the last sample and never extrapolates.")}${eb && eb.curve.length < 2 ? `<div class="energy-row"><span class="bolt">${icon("bolt-fill")}</span>${energyTicks(eb.current)}<b>${fmt.n(eb.current)}%</b></div>` : eb ? chart({ id: "eb", label: "Energy bank through the day", x: eb.curve.map(c => c.t), h: 120, yMin: 0, yMax: 100, series: [{ name: "Energy", color: "var(--recovery)", values: eb.curve.map(c => c.v), area: true }], fmtX: t => fmt.time(t), fmtY: v => fmt.n(v) + "%" }) : empty("Energy bank needs recovery or sleep")}</div>
</div>
      <div class="stack"><div class="card">${cardHead("Recovery", seg("rec-range", RANGES_DWMY, rng))}${recChart}</div>
      <div class="card">${cardHead("Resting HRV")}${trendChart(hrvTrend, "HRV", "var(--recovery)", "ms")}</div>
      <div class="card">${cardHead("Resting heart rate")}${trendChart(rhrTrend, "Resting HR", "var(--bad)", "bpm")}</div>
      ${rrTrend ? `<div class="card">${cardHead("Respiratory rate")}${trendChart(rrTrend, "Respiratory rate", "var(--info)", "br/min")}</div>` : ""}
      <div class="card">${cardHead("Prehab", editBtn("prehab-new", undefined, "New"))}${ph.length ? `<div class="list">${ph.map(r => { const n = phl.filter(l => l.routine_id === r.id).length; const last = phl.filter(l => l.routine_id === r.id).map(l => l.date).sort().pop(); return `<div class="li"><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${[r.focus, r.duration_min ? r.duration_min + " min" : "", (r.exercises || []).length ? r.exercises.length + " exercises" : ""].filter(Boolean).map(esc).join(" · ")}</div></div><div class="r small">${n}×<div class="cap">${last ? "last " + fmt.date(last) : ""}</div></div>${AG.online ? (last === D.meta.build_date ? badge("Done today", "ok") : `<button type="button" class="btn sm secondary" data-prehab="${esc(r.id)}">Done today</button>`) : ""}</div>`; }).join("")}</div>` : empty(STR.noPrehab)}</div>
      </div></div>`;
  },
  after() { drawCharts(); },
};

document.addEventListener("click", e => {
  const b = e.target.closest("[data-prehab]");
  if (b) act("prehab.done", { routine_id: b.dataset.prehab }, "Logged").catch(() => {});
});
function helpingList(win, limit) {
  const rows = (D.coach.helping_hurting[win] || []);
  const ok = rows.filter(r => r.status === "ok");
  if (!ok.length) {
    const best = rows.reduce((m, r) => Math.max(m, r.n || 0), 0);
    const needed = rows[0] ? rows[0].needed : 21;
    return `<p class="small muted" style="margin:0">${best >= needed ? `No clear effect in the last ${esc(win)} days` : `Needs more days (${best} of ${needed})`}</p>`;
  }
  return `<div class="list">${ok.slice(0, limit || 99).map(r => `<div class="factor ${r.direction}"><span class="ic">${icon(r.direction === "helping" ? "up" : "down")}</span><div class="grow"><div class="t">${esc(r.label)}</div><div class="s">${r.direction === "helping" ? "More → better recovery" : "More → lower recovery"} · ${r.n} days</div></div><span class="r">${isNum(r.effect_points) ? fmt.signed(r.effect_points, 1) + " pts" : ""}</span></div>`).join("")}</div>`;
}

AG.screens.sleep = {
  title: "Sleep",
  render() {
    const S = D.sleep;
    if (!S.last_night) return empty(STR.noData, `Sleep appears after ${AGENT} imports HealthKit sleep stages`);
    const ln = S.last_night;
    const rng = chipVal("sleep-range", "30");
    const hist = sliceDays(S.history, rangeDays(rng));
    const sp = ln.stage_pct || {}, sm = ln.stage_min || {};
    const stageTile = (k, label, color) => `<div class="stage"><div><div class="k">${label}</div><div class="v">${isNum(sm[k]) ? fmt.hm(sm[k]) : "—"}</div><div class="p" style="color:${color}">${isNum(sp[k]) ? fmt.n(sp[k]) + "%" : k === "awake" && isNum(sm.awake) && isNum(ln.in_bed_min) ? fmt.n(sm.awake / ln.in_bed_min * 100) + "%" : ""}</div></div>${ring2(isNum(sp[k]) ? sp[k] : (k === "awake" && isNum(sm.awake) ? sm.awake / ln.in_bed_min * 100 : 0), color)}</div>`;
    const need = S.need, debt = S.debt, reg = S.regularity || {};
    const bedPts = hist.map(h => { const b = new Date(h.bed), w = new Date(h.wake); return { date: h.date, bed: toLocalMin(h.bed), wake: toLocalMin(h.wake) }; });
    const corr = S.recovery_correlation;
    return `<div class="cols"><div class="stack">
      ${S.stale ? `<div class="empty inline"><b>${STR.sleepNotSynced}</b><span class="cap">Showing ${fmt.dateLong(S.last_date)}</span></div>` : ""}
      <div class="card ${S.stale ? "is-stale" : ""}">${cardHead(esc(fmt.dateLong(ln.date)), "", "", S.score)}<div class="spread"><div><div class="stat"><span class="v" style="font-size:40px">${fmt.hm(ln.asleep_min)}</span></div>
        <div class="small muted">${isNum(need.v) ? "of " + fmt.hm(need.v) + " needed" : esc(need.note || "")}</div></div>${ring("sleep", S.score, { label: "Sleep score", sub: "score" })}</div>
        <div class="stats-grid s4" style="margin-top:16px">${stat("Efficiency", isNum(ln.efficiency) ? fmt.n(ln.efficiency * 100) + "%" : "—")}${stat("Sleep debt", debt && isNum(debt.v) ? fmt.hm(debt.v) : "—")}${stat("Consistency", isNum(reg.midpoint_sd_7) ? "±" + fmt.n(reg.midpoint_sd_7) + "m" : "—")}${stat("Disruptions", fmt.n(ln.disruptions.length))}</div>
        ${S.score.missing_components && S.score.missing_components.length ? `<div class="st-line partial"><span class="dot"></span>Partial: no ${esc(S.score.missing_components.join(", "))}</div>` : ""}</div>
      <div class="card">${cardHead("Stages")}${ln.has_stages ? chart({ id: "hyp", type: "hypno", label: "Sleep stage timeline", segments: ln.segments, start: ln.start, end: ln.end, h: 150 }) : empty("No stage data", "In-bed time only for this night")}
        <div class="stage-tiles" style="margin-top:12px">${stageTile("awake", "Awake", "var(--st-awake)")}${stageTile("rem", "REM", "var(--st-rem)")}${stageTile("core", "Core", "var(--st-core)")}${stageTile("deep", "Deep", "var(--st-deep)")}</div></div>
      <div class="card">${cardHead("Details")}<div class="list"><div class="li"><div class="grow"><div class="t">Sleep needed</div><div class="s">${isNum(need.base) ? `Base ${fmt.hm(need.base)} + strain ${need.strain_add}m + debt ${need.debt_add}m` : ""}</div></div><div class="r">${isNum(need.v) ? fmt.hm(need.v) : "—"}</div></div>
        <div class="li"><div class="grow"><div class="t">Time to fall asleep</div></div><div class="r">${isNum(ln.latency_min) ? fmt.n(ln.latency_min) + " min" : "—"}</div></div>
        <div class="li"><div class="grow"><div class="t">Bedtime · wake</div></div><div class="r">${fmt.time(ln.bed)} · ${fmt.time(ln.wake)}</div></div>
        <div class="li"><div class="grow"><div class="t">Regularity</div><div class="s">Last 7 nights</div></div><div class="r">${isNum(reg.sri) ? fmt.n(reg.sri) : "—"}</div></div></div></div>
      ${S.naps.length ? `<div class="card">${cardHead("Naps")}<div class="list">${S.naps.map(n => `<div class="li"><div class="grow"><div class="t">${fmt.date(n.date)}</div><div class="s">${fmt.time(n.start)}–${fmt.time(n.end)}</div></div><div class="r">${fmt.hm(n.asleep_min)}</div></div>`).join("")}</div></div>` : ""}
      <div class="card">${cardHead("Sleep score")}${chart({ id: "sl-sc", label: "Sleep score history", x: hist.map(h => h.date), h: 140, yMin: 0, yMax: 100, gapMs: 2.5 * 86400000, series: [{ name: "Score", color: "var(--sleep)", values: hist.map(h => h.score), dots: hist.length < 45 }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) })}</div>
      </div><div class="stack">
      <div class="card">${cardHead("Duration", seg("sleep-range", RANGES_DWMY, rng))}
        ${chart({ id: "sl-dur", type: "bar", label: "Sleep duration and need per night", x: hist.map(h => h.date), h: 170,
          series: [{ name: "Asleep", color: "var(--sleep)", values: hist.map(h => isNum(h.asleep_min) ? h.asleep_min / 60 : null) }],
          refLines: isNum(S.base_need) ? [{ y: S.base_need / 60, label: "base need" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.hm(v * 60), fmtYAxis: v => fmt.n(v) + "h", range: rangeLabel(hist) })}</div>
      <div class="card">${cardHead("Bedtime & wake", isNum(reg.midpoint_sd_14) ? `<span class="small muted">±${fmt.n(reg.midpoint_sd_14)} min</span>` : "", "Variation is the standard deviation of your sleep midpoint over the last 14 nights.")}${chart({ padR: 46, id: "sl-bw", label: "Bedtime and wake time", x: bedPts.map(p => p.date), h: 160, invertY: true,
          series: [{ name: "Bedtime", color: "var(--sleep-2)", values: bedPts.map(p => p.bed), dots: true }, { name: "Wake", color: "var(--strain-2)", values: bedPts.map(p => p.wake), dots: true }],
          fmtX: d => fmt.date(d), fmtY: v => minToClock(v), fmtYAxis: v => minToClock(v), yTicks: 6 })}</div>
      <div class="card">${cardHead("Stages over time")}${chart({ id: "sl-st", type: "bar", stacked: true, label: "Sleep stage percentages per night", x: hist.map(h => h.date), h: 150, yMin: 0, yMax: 100,
          series: [["deep", "Deep", "var(--st-deep)"], ["core", "Core", "var(--st-core)"], ["rem", "REM", "var(--st-rem)"]].map(([k, n, c]) => ({ name: n, color: c, values: hist.map(h => h.stage_pct ? h.stage_pct[k] : null) })), fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%" })}</div>
      <div class="card">${cardHead("Sleep & recovery", `<span class="small muted">${corr.status === "ok" ? esc(fmt.sport(corr.strength)) + " " + esc(corr.direction) : corr.status === "no_clear_effect" ? "No clear link yet" : `${corr.n} of ${corr.needed} nights`}</span>`, `Each dot is one night: hours asleep against next-morning recovery${isNum(corr.r) ? ` (r ${fmt.n(corr.r, 2)}, ${corr.n} nights)` : ""}. A trend line appears only once the relationship is clear.`)}
        ${corr.points && corr.points.length >= 5 ? chart({ id: "sl-corr", type: "scatter", label: "Sleep duration against next-morning recovery", points: corr.points, fit: corr.fit, h: 170, xName: "Asleep", yName: "Recovery", color: "var(--sleep)", fmtX: v => fmt.hm(v), fmtY: v => fmt.n(v) + "%" }) : ""}</div>
      <div class="card tight"><div class="list"><div class="li"><span class="icon-dot">${icon("sleep")}</span><div class="grow"><div class="t">Smart alarm</div><div class="s">${(D.profile.smart_alarm || {}).enabled ? `${D.profile.smart_alarm.window_min} min before ${esc(D.profile.smart_alarm.target_wake || "—")}` : "Off"} · needs the companion app</div></div></div></div></div>
      </div></div>`;
  },
  after() { drawCharts(); },
};
function ring2(pct, color) {
  const r = 14, C = 2 * Math.PI * r, p = Math.max(0, Math.min(100, pct || 0)) / 100;
  return `<svg width="36" height="36" viewBox="0 0 36 36" aria-hidden="true" style="transform:rotate(-90deg)"><circle cx="18" cy="18" r="${r}" fill="none" stroke="var(--surface-3)" stroke-width="4"/><circle cx="18" cy="18" r="${r}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="round" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - p)}"/></svg>`;
}
function toLocalMin(iso) {
  const t = fmt.time(iso).split(":");
  let m = +t[0] * 60 + +t[1];
  if (m < 12 * 60 && m > 4 * 60) return m; // wake times
  return m >= 12 * 60 ? m - 24 * 60 : m; // bedtimes before midnight are negative
}
function minToClock(v) { let m = Math.round(v); m = ((m % 1440) + 1440) % 1440; return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); }
