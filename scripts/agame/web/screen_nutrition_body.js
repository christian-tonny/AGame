/* Nutrition and Body (weight, VO2 max, custom charts, blood pressure, Biological Age, Health Records) */
"use strict";

AG.screens.nutrition = {
  title: "Nutrition",
  render() {
    const N = D.nutrition;
    if (!N.connected) return `${empty(STR.noNutrition, `Log meals through your AGame server, or have ${AGENT} import nutrition from HealthKit. Calories and protein never show as zero when nothing is logged.`)}
      <div class="card" style="margin-top:12px"><h3>Add a meal</h3>${mealForm()}</div>`;
    const tab = chipVal("nut-tab", "today");
    const body = { today: nutToday, diary: nutDiary, trends: nutTrends, plan: nutPlan }[tab]();
    return `${chips("nut-tab", [["today", "Today"], ["diary", "Diary"], ["trends", "Trends"], ["plan", "Recipes & plan"]], tab)}<div style="margin-top:12px">${body}</div>`;
  },
  after() { drawCharts(); bindMealForm(); },
};

function nutToday() {
  const N = D.nutrition;
  const t = N.today, y = N.yesterday;
  const pr = N.protein;
  const tgt = N.targets;
  const pv = pr.today && isNum(pr.today.v) ? pr.today.v : null;
  const ppct = pv !== null && pr.target ? pv / pr.target * 100 : 0;
  const day = t || y;
  const mp = day && day.macro_pct;
  const dm = (pct, color) => { const n = Math.round((pct || 0) / 100 * 60); return `<div class="dm">${Array.from({ length: 60 }, (_, i) => `<i style="${59 - i < n ? "background:" + color : ""}"></i>`).join("")}</div>`; };
  const net = day && isNum(day.net_kcal) ? day.net_kcal : null;
  const score = day && day.score;
  const left = k => isNum(tgt[k]) && t && isNum(t[k]) ? Math.max(0, tgt[k] - t[k]) : null;
  return `<div class="cols"><div class="stack">
    <div class="card"><div class="spread"><h3 style="margin:0">Protein</h3>${pr.target ? badge(`Target ${fmt.n(pr.target)} g`, "accent") : badge("No target set", "")}</div>
      <div class="spread" style="margin:8px 0"><div class="stat hero"><span class="v">${pv === null ? "—" : fmt.n(pv)}<small>g</small></span></div><div style="text-align:right" class="small">${pr.target && pv !== null ? `${fmt.n(Math.max(0, pr.target - pv))} g to go` : ""}<div class="cap">today so far</div></div></div>
      ${bar(ppct, "var(--protein)")}
      <div class="stats-grid s3" style="margin-top:12px">${stat("Yesterday", isNum(pr.yesterday) ? fmt.n(pr.yesterday) + " g" : "—")}${stat("7-day avg", isNum(pr.avg_7) ? fmt.n(pr.avg_7) + " g" : "—")}${stat("Days hit", isNum(pr.days_hit_7) ? `${pr.days_hit_7}/${pr.days_logged_7}` : "—")}</div>
      ${pr.per_meal_today.length ? `<div class="list" style="margin-top:8px">${pr.per_meal_today.map(m => `<div class="li"><div class="grow small">${esc(fmt.sport(m.meal || "Meal"))} · ${fmt.time(m.t)}</div><div class="r small">${fmt.n(m.protein_g)} g</div></div>`).join("")}</div>` : ""}</div>
    <div class="grid g3">${["fat_g", "carbs_g", "protein_g"].map(k => `<div class="card tight"><div class="cap">${{ fat_g: "Fat", carbs_g: "Carbs", protein_g: "Protein" }[k]}</div><div class="small"><b>${isNum(left(k)) ? fmt.n(left(k)) + " g" : "—"}</b> left</div></div>`).join("")}</div>
    <div class="card"><div class="spread"><h3 style="margin:0">Nutritional details</h3><span class="cap">${t ? "Today" : y ? "Yesterday" : ""}</span></div>
      ${mp ? `<div class="dots" style="margin-top:10px"><div class="dotcol">${dm(mp.fat_g, "var(--fat)")}<b>${mp.fat_g}%</b><span style="color:var(--fat)">Fat</span></div><div class="dotcol">${dm(mp.carbs_g, "var(--carbs)")}<b>${mp.carbs_g}%</b><span style="color:var(--carbs)">Carbs</span></div><div class="dotcol">${dm(mp.protein_g, "var(--protein)")}<b>${mp.protein_g}%</b><span style="color:var(--protein)">Protein</span></div></div>` : `<p class="small muted">No macros logged</p>`}</div>
    <div class="card"><h3>Net energy</h3>${net !== null ? `<div class="stat"><span class="v">${fmt.signed(net)}<small>kcal</small></span></div><div class="row small muted">${icon("flame")} ${fmt.n(day.energy_out.total)} out · ${fmt.n(day.kcal)} in</div>
      <div style="position:relative;height:10px;border-radius:999px;margin:12px 0 4px;background:linear-gradient(90deg,var(--strain),var(--carbs),var(--sleep))"><i style="position:absolute;top:-3px;width:4px;height:16px;border-radius:2px;background:var(--text);left:calc(${Math.max(0, Math.min(100, (net + 500) / 10))}% - 2px)"></i></div>
      <div class="spread cap"><span>−500</span><span>0</span><span>+500</span></div>${day.net_partial ? `<p class="cap">Partial: ${day.complete === true ? "energy out incomplete" : "day not complete"}.</p>` : ""}` : `<p class="small muted">Needs logged food and HealthKit energy</p>`}</div></div>
    <div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Nutrition score</h3>${score && score.partial ? badge("Day in progress", "info") : ""}</div>
      ${score ? `<div class="stat"><span class="v">${score.score}</span></div><div class="list">${Object.entries(score.components).map(([k, v]) => `<div class="li"><div class="grow small">${esc(fmt.sport(k))}</div><div class="r small">${v}</div></div>`).join("")}</div>
      ${score.contributors.length ? sectionTitle("Quality contributors") + score.contributors.map(c => `<div class="row" style="gap:10px;margin:6px 0"><span class="small" style="width:96px">${esc(c.label)}</span><div class="bar thin" style="flex:1"><i style="width:${Math.min(100, Math.abs(c.points) * 10)}%;background:${c.points >= 0 ? "var(--ok)" : "var(--bad)"}"></i></div><span class="small num" style="width:36px;text-align:right">${fmt.signed(c.points, 0)}</span></div>`).join("") : ""}
      ${score.missing_components.length ? `<p class="cap">Missing: ${esc(score.missing_components.join(", "))} (set targets in profile)</p>` : ""}` : `<p class="small muted">Score needs logged food and targets</p>`}</div>
    <div class="card"><h3>Hydration & caffeine</h3><div class="stats-grid">${stat("Water", t && isNum(t.water_ml) ? fmt.n(t.water_ml) : "—", "ml", { d: isNum(tgt.water_ml) ? `<span class="cap">of ${fmt.n(tgt.water_ml)} ml</span>` : "" })}${stat("Caffeine", t && isNum(t.caffeine_mg) ? fmt.n(t.caffeine_mg) : "—", "mg", { d: tgt.caffeine_cutoff ? `<span class="cap">cutoff ${esc(tgt.caffeine_cutoff)}</span>` : "" })}</div></div>
    <div class="card"><h3>Meals today</h3>${t && t.per_meal.length ? `<div class="list">${t.per_meal.map(m => `<div class="li"><div class="grow"><div class="t">${esc(m.name || fmt.sport(m.meal))}</div><div class="s">${fmt.time(m.t)} · ${esc(m.items.join(", "))}</div></div><div class="r small">${fmt.n(m.kcal)} kcal<div class="cap">${fmt.n(m.protein_g)} g P</div></div></div>`).join("")}</div>` : `<p class="small muted">Nothing logged yet today</p>`}
      <details style="margin-top:10px"><summary class="small" style="cursor:pointer;color:var(--accent);font-weight:600">Add a meal</summary>${mealForm()}</details></div>
    ${N.glucose ? `<div class="card"><h3>Glucose</h3>${chart({ id: "glu", label: "Glucose samples", x: N.glucose.points.map(p => p.t), h: 130, series: [{ name: "Glucose", color: "var(--warn)", values: N.glucose.points.map(p => p.v) }], fmtX: t => fmt.time(t), fmtY: v => fmt.n(v) + " mg/dL" })}</div>` : ""}</div></div>`;
}

function mealForm() {
  return `<form class="form" id="meal-form" style="margin-top:8px">
    <div class="grid g2"><label>Meal <select name="meal"><option>breakfast</option><option>lunch</option><option>dinner</option><option>snack</option></select></label><label>Time <input name="t" type="datetime-local" required></label></div>
    <label>Describe it <input name="name" placeholder="e.g. Chicken, rice, beans" required></label>
    <div class="grid g4"><label>kcal <input name="kcal" inputmode="decimal"></label><label>Protein g <input name="protein_g" inputmode="decimal"></label><label>Carbs g <input name="carbs_g" inputmode="decimal"></label><label>Fat g <input name="fat_g" inputmode="decimal"></label></div>
    <label>Barcode <input name="barcode" inputmode="numeric" placeholder="Stored as text; lookup needs a food database"></label>
    <p class="cap">Photo recognition not connected${(D.profile.integrations || {}).vision_service ? "" : ""}. Conversational logging works through Coach when an LLM is configured.</p>
    <button class="btn" ${AG.online ? "" : "disabled"}>Save meal</button>${offlineNote()}</form>`;
}
function bindMealForm() {
  const f = $("#meal-form");
  if (!f) return;
  f.onsubmit = async e => {
    e.preventDefault();
    const num = k => f[k].value === "" ? null : +f[k].value;
    const item = { name: f.name.value, qty: 1, unit: "serving", kcal: num("kcal"), protein_g: num("protein_g"), carbs_g: num("carbs_g"), fat_g: num("fat_g"), barcode: f.barcode.value || null };
    try { await api("POST", "entries/nutrition.meals", { t: new Date(f.t.value).toISOString(), meal: f.meal.value, name: f.name.value, items: [item] }); toast("Saved · rebuilding"); setTimeout(() => location.reload(), 900); }
    catch (err) { toast(err.message); }
  };
}

function nutDiary() {
  const days = D.nutrition.days.slice().reverse().slice(0, 21);
  return `<div class="stack">${days.map(d => `<div class="card"><div class="spread"><b>${fmt.dow(d.date)} ${fmt.date(d.date)}</b><span class="small muted">${isNum(d.kcal) ? fmt.n(d.kcal) + " kcal" : "—"} · ${isNum(d.protein_g) ? fmt.n(d.protein_g) + " g P" : "—"}${d.complete === false ? " · incomplete" : d.complete === null ? " · in progress" : ""}</span></div>
    <div class="list">${d.per_meal.map(m => `<div class="li"><div class="grow"><div class="t small">${esc(m.name || fmt.sport(m.meal))}</div><div class="s">${fmt.time(m.t)} · ${esc(m.items.join(", "))}</div></div><div class="r small">${fmt.n(m.protein_g)} g</div></div>`).join("")}</div></div>`).join("")}
    <p class="cap">Copy a meal or day, edit date/time, multi-select and make a recipe through your AGame server (edits keep history and undo).</p></div>`;
}

function nutTrends() {
  const rng = chipVal("nut-range", "30");
  const days = sliceDays(D.nutrition.days.filter(d => d.complete !== false || d.date === D.meta.build_date), rangeDays(rng));
  const pt = D.nutrition.targets.protein_g, kt = D.nutrition.targets.kcal;
  return `<div class="cols"><div class="stack">${chips("nut-range", RANGES_DWMY, rng)}
    <div class="card"><h3>Protein</h3>${chart({ id: "n-p", type: "bar", label: "Daily protein", x: days.map(d => d.date), h: 150, series: [{ name: "Protein", color: (i, v) => pt && v >= pt ? "var(--protein)" : "color-mix(in srgb, var(--protein) 55%, transparent)", values: days.map(d => d.protein_g) }], refLines: pt ? [{ y: pt, label: "target" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " g" })}</div>
    <div class="card"><h3>Calories</h3>${chart({ id: "n-k", type: "bar", label: "Daily calories", x: days.map(d => d.date), h: 150, series: [{ name: "Calories", color: "var(--carbs)", values: days.map(d => d.kcal) }], refLines: kt ? [{ y: kt, label: "target" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " kcal" })}</div></div>
    <div class="stack"><div class="card"><h3>Macro split</h3>${chart({ id: "n-m", type: "bar", stacked: true, label: "Macro percentages", x: days.map(d => d.date), h: 150, yMin: 0, yMax: 100, series: [["fat_g", "Fat", "var(--fat)"], ["carbs_g", "Carbs", "var(--carbs)"], ["protein_g", "Protein", "var(--protein)"]].map(([k, n, c]) => ({ name: n, color: c, values: days.map(d => d.macro_pct ? d.macro_pct[k] : null) })), fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%" })}</div>
    <div class="card"><h3>Net energy</h3>${chart({ id: "n-net", type: "bar", label: "Net energy", x: days.map(d => d.date), h: 150, series: [{ name: "Net", color: (i, v) => v < 0 ? "var(--ok)" : "var(--warn)", values: days.map(d => isNum(d.net_kcal) ? d.net_kcal : null) }], fmtX: d => fmt.date(d), fmtY: v => fmt.signed(v) + " kcal" })}</div>
    <div class="card"><h3>Nutrition score</h3>${chart({ id: "n-s", label: "Nutrition score", x: days.map(d => d.date), h: 130, yMin: 0, yMax: 100, series: [{ name: "Score", color: "var(--ok)", values: days.map(d => d.score ? d.score.score : null), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) })}</div></div></div>`;
}

function nutPlan() {
  const N = D.nutrition;
  return `<div class="cols"><div class="card"><h3>Recipes</h3>${N.recipes.length ? `<div class="list">${N.recipes.map(r => `<div class="li"><div class="grow"><div class="t">${esc(r.name)} ${r.favorite ? badge("Favorite", "accent") : ""}</div><div class="s">${r.items.map(i => esc(i.name)).join(", ")}</div></div><div class="r small">${fmt.n(r.items.reduce((s, i) => s + (i.protein_g || 0), 0))} g P</div></div>`).join("")}</div>` : empty("No recipes yet")}
    ${sectionTitle("Favorites")}${N.favorites.length ? `<div class="list">${N.favorites.map(i => `<div class="li"><div class="grow"><div class="t">${esc(i.name)}</div></div><div class="r small">${fmt.n(i.kcal)} kcal</div></div>`).join("")}</div>` : empty("No favorites yet")}</div>
    <div class="card"><h3>Planned meals</h3>${N.planned.length ? `<div class="list">${N.planned.map(p => `<div class="li"><div class="grow"><div class="t">${fmt.dow(p.date)} ${fmt.date(p.date)} · ${esc(p.meal || "")}</div><div class="s">${esc((N.recipes.find(r => r.id === p.recipe_id) || {}).name || p.items.map(i => i.name).join(", "))}</div></div></div>`).join("")}</div>` : empty("Nothing planned")}</div></div>`;
}

/* ---------------- Body ---------------- */
AG.screens.body = {
  title: "Body",
  render() {
    const tab = chipVal("body-tab", "weight");
    const body = { weight: bodyWeight, vo2: bodyVO2, charts: bodyCharts, bp: bodyBP, bioage: bodyBioAge, records: bodyRecords }[tab] || bodyWeight;
    return `${chips("body-tab", [["weight", "Weight"], ["vo2", "VO2 max"], ["charts", "Charts"], ["bp", "Blood pressure"], ["bioage", "Biological Age"], ["records", "Health records"]], tab)}<div style="margin-top:12px">${body()}</div>`;
  },
  after() { drawCharts(); },
};

function bodyWeight() {
  const W = D.body.weight;
  if (W.status === "missing") return empty(STR.noWeight, "Weight comes from HealthKit body mass or manual entries");
  const g = W.goal;
  const rng = chipVal("w-range", "180");
  const pts = sliceDays(W.points, rangeDays(rng === "180" ? "6m" : rng));
  const wk = W.weekly.filter(w => pts.length && w.week >= pts[0].date);
  const conv = v => isNum(v) ? (IMPERIAL ? v * 2.20462 : v) : null;
  const wkMap = {};
  wk.forEach(w => wkMap[w.week] = w.median);
  const medSeries = pts.map(p => { const ws = Object.keys(wkMap).filter(k => k <= p.date).pop(); return ws ? conv(wkMap[ws]) : null; });
  let proj = null;
  if (g && g.target_date && isNum(W.current.v)) proj = [conv(W.current.v), conv(g.target)];
  return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><div><div class="cap">Current (7-day median)</div><div class="stat hero"><span class="v">${fmt.kgNum(W.current.v)}<small>${fmt.wUnit()}</small></span></div><div class="cap">Latest ${fmt.kg(W.current.latest)} on ${fmt.date(W.current.latest_date)}</div></div>
      <div style="text-align:right">${stat("4-week trend", isNum(W.trend_kg_per_week.v) ? fmt.signed(conv(W.trend_kg_per_week.v), 2) : "—", fmt.wUnit() + "/wk")}</div></div>${stLine(W.current)}${!isNum(W.trend_kg_per_week.v) ? `<p class="cap">${esc(W.trend_kg_per_week.note)}</p>` : ""}</div>
    ${g ? `<div class="card"><div class="spread"><h3 style="margin:0">Goal: ${fmt.kg(g.target)} by ${fmt.date(g.target_date, { day: "numeric", month: "short", year: "numeric" })}</h3>${goalStatusBadge(g.status)}</div>
      <div class="stats-grid s3" style="margin-top:10px">${stat("Remaining", fmt.kg(Math.abs(g.remaining_kg)))}${stat("Needed", isNum(g.required_kg_per_week) ? fmt.signed(conv(g.required_kg_per_week), 2) : "—", fmt.wUnit() + "/wk")}${stat("Projected", g.projected_date ? fmt.date(g.projected_date, { month: "short", year: "numeric" }) : "—")}</div>
      ${isNum(g.progress_pct) ? bar(g.progress_pct, "var(--accent)") : ""}<p class="cap">${isNum(g.weeks_left) ? fmt.n(g.weeks_left) + " weeks left · " : ""}Projection uses your current 4-week trend.</p></div>` : `<div class="card">${empty(STR.noGoals, "Add a body-weight goal to see the trajectory")}</div>`}</div>
    <div class="stack"><div class="card">${chips("w-range", [["30", "1M"], ["90", "3M"], ["180", "6M"], ["365", "1Y"], ["all", "All"]], rng)}
      ${chart({ id: "wt", label: "Weight with weekly median", x: pts.map(p => p.date), h: 210, gapMs: 10 * 86400000,
        series: [{ name: "Daily", color: "var(--text-3)", values: pts.map(p => conv(p.v)), dots: true, noLine: true, dotR: 2 }, { name: "Weekly median", color: "var(--accent)", values: medSeries, width: 2.4 }],
        refLines: g ? [{ y: conv(g.target), label: "goal", color: "var(--ok)" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + fmt.wUnit(), range: rangeLabel(pts) })}</div>
    ${Object.keys(W.composition || {}).length ? `<div class="card"><h3>Body composition</h3><div class="stats-grid">${Object.entries(W.composition).map(([k, c]) => stat(fmt.sport(k.replace(/_pct|_kg|_cm/, "")), fmt.n(c.current, 1), k.endsWith("pct") ? "%" : k.endsWith("kg") ? fmt.wUnit() : "cm", { d: `<span class="cap">${fmt.date(c.as_of)}</span>` })).join("")}</div></div>` : ""}</div></div>`;
}

function bodyVO2() {
  const V = D.body.vo2max;
  if (V.status === "missing") return `<div class="card">${empty(STR.noVO2, "VO2 max comes only from HealthKit cardio-fitness samples; AGame never estimates it from pace.")}</div>`;
  const rng = chipVal("vo2-range", "365");
  const pts = sliceDays(V.points, rangeDays(rng)), sm = sliceDays(V.smoothed, rangeDays(rng));
  const smMap = {}; sm.forEach(s => smMap[s.date] = s.v);
  return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><div><div class="cap">Latest sample</div><div class="stat hero"><span class="v">${fmt.n(V.current.v, 1)}<small>ml/kg/min</small></span></div><div class="cap">${fmt.date(V.current.as_of)} · HealthKit cardio fitness</div></div>${prov(V.current, "VO2 max")}</div>
      <div class="stats-grid s4" style="margin-top:10px">${stat("Trend", fmt.n(V.smoothed_current, 1))}${stat("30 days", isNum(V.delta_30) ? fmt.signed(V.delta_30, 1) : "—")}${stat("90 days", isNum(V.delta_90) ? fmt.signed(V.delta_90, 1) : "—")}${stat("Confidence", esc(fmt.sport(V.confidence)), "", { d: `<span class="cap">${V.samples_90d} samples/90d</span>` })}</div>${stLine(V.current)}</div>
    ${V.gaps.length ? `<div class="card"><h3>Data gaps</h3><div class="list">${V.gaps.map(g => `<div class="li"><div class="grow small">${fmt.date(g.from)} → ${fmt.date(g.to)}</div><div class="r small">${g.days} days</div></div>`).join("")}</div></div>` : ""}</div>
    <div class="card">${chips("vo2-range", RANGES_DWMY.slice(1), rng)}${chart({ id: "vo2", label: "VO2 max samples and trend", x: pts.map(p => p.date), h: 210,
      series: [{ name: "Samples", color: "var(--text-3)", values: pts.map(p => p.v), dots: true, noLine: true }, { name: "Smoothed trend", color: "var(--info)", values: pts.map(p => smMap[p.date] !== undefined ? smMap[p.date] : null), width: 2.4 }],
      fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1), range: rangeLabel(pts) })}<p class="cap">Raw HealthKit points with a ±21-day rolling mean.</p></div></div>`;
}

function bodyCharts() {
  const M = D.body.metrics;
  const ids = Object.keys(M);
  if (!ids.length) return empty(STR.noData, "Charts appear for every metric HealthKit provides");
  const pinned = ((D.profile.ui || {}).pinned_charts || []).filter(x => M[x] || x === "weight_kg");
  const sel = chipVal("cc-metric", pinned.find(x => M[x]) || ids[0]);
  const rng = chipVal("cc-range", "90");
  const agg = chipVal("cc-agg", "day");
  const m = M[sel] || M[ids[0]];
  let pts = sliceDays(m.points, rangeDays(rng));
  if (agg === "week") {
    const wk = {};
    pts.forEach(p => { const d = new Date(p.date + "T12:00:00Z"); const day = (d.getUTCDay() + 6) % 7; d.setUTCDate(d.getUTCDate() - day); const k = d.toISOString().slice(0, 10); (wk[k] = wk[k] || []).push(p.v); });
    pts = Object.keys(wk).sort().map(k => ({ date: k, v: m.agg === "sum" ? wk[k].reduce((a, b) => a + b, 0) : wk[k].reduce((a, b) => a + b, 0) / wk[k].length }));
  }
  const ytd = m.points.filter(p => p.date.slice(0, 4) === D.meta.build_date.slice(0, 4));
  return `<div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Pinned</h3><span class="cap">Pin and reorder in profile.ui.pinned_charts</span></div><div class="grid g4" style="margin-top:8px">${pinned.filter(x => M[x]).map(x => `<button class="card tight flat" data-chip="cc-metric" data-val="${esc(x)}"><div class="cap">${esc(M[x].label)}</div><b>${fmt.n(M[x].latest, M[x].latest % 1 ? 1 : 0)} <small class="muted">${esc(M[x].unit)}</small></b>${sparkline(M[x].points.slice(-30).map(p => p.v), "var(--accent)")}</button>`).join("") || `<p class="small muted">Nothing pinned</p>`}</div></div>
    ${chips("cc-metric", ids.map(id => [id, M[id].label]), m.id)}
    <div class="card"><div class="spread"><div><div class="cap">${esc(m.label)}</div><div class="stat"><span class="v">${fmt.n(m.latest, m.latest % 1 ? 1 : 0)}<small>${esc(m.unit)}</small></span></div><div class="cap">Latest ${fmt.date(m.latest_date)} · 7-day avg ${fmt.n(m.avg_7, 1)} · prior 4 weeks ${fmt.n(m.avg_prev_28, 1)}</div></div>${seg("cc-agg", [["day", "Day"], ["week", "Week"]], agg)}</div>
      <div style="margin:8px 0">${chips("cc-range", RANGES_DWMY, rng)}</div>
      ${chart({ id: "cc", type: m.agg === "sum" ? "bar" : "line", label: m.label + " history", x: pts.map(p => p.date), h: 200, gapMs: agg === "week" ? 15 * 86400000 : 3.5 * 86400000,
        series: [{ name: m.label, color: "var(--accent)", values: pts.map(p => p.v), dots: m.agg !== "sum" && pts.length < 60 }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + m.unit, range: rangeLabel(pts) })}
      ${ytd.length ? `<p class="cap">Year to date: ${m.agg === "sum" ? "total " + fmt.n(ytd.reduce((a, p) => a + p.v, 0)) : "average " + fmt.n(ytd.reduce((a, p) => a + p.v, 0) / ytd.length, 1)} ${esc(m.unit)} over ${ytd.length} days.</p>` : ""}</div></div>`;
}

function bodyBP() {
  const bp = D.body.bp;
  if (!bp.systolic || !bp.diastolic) return `<div class="card">${empty("No blood pressure readings", "From HealthKit or manual entries. AGame shows readings only — no categories or diagnosis.")}</div>`;
  const sMap = {}; bp.diastolic.points.forEach(p => sMap[p.date] = p.v);
  const pts = bp.systolic.points;
  return `<div class="cols"><div class="card"><div class="stat hero"><span class="v">${fmt.n(bp.systolic.latest)}/${fmt.n(bp.diastolic.latest)}<small>mmHg</small></span></div><div class="cap">${fmt.date(bp.systolic.latest_date)} · 7-day avg ${fmt.n(bp.systolic.avg_7)}/${fmt.n(bp.diastolic.avg_7)}</div>
    <p class="cap">Readings only. Talk to a clinician about what your numbers mean.</p></div>
    <div class="card">${chart({ id: "bp", label: "Blood pressure readings", x: pts.map(p => p.date), h: 190, series: [{ name: "Systolic", color: "var(--bad)", values: pts.map(p => p.v), dots: true }, { name: "Diastolic", color: "var(--info)", values: pts.map(p => sMap[p.date] !== undefined ? sMap[p.date] : null), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " mmHg" })}</div></div>`;
}

function bodyBioAge() {
  const B = D.health.bioage;
  if (B.status !== "ok") return `<div class="card">${empty("Not enough inputs for Biological Age", "Needed: " + (B.needed || []).join(" · "))}<p class="cap" style="margin-top:10px">${esc(B.methodology)}</p></div>`;
  const diff = B.chronological - B.value;
  const pct = Math.max(0, Math.min(1, (B.value - (B.chronological - 10)) / 20));
  const ang = Math.PI * (1 - pct);
  return `<div class="cols"><div class="stack"><div class="card" style="text-align:center"><div class="cap">Biological Age · as of ${fmt.date(B.as_of)}</div>
      <div class="gauge"><svg viewBox="0 0 220 130" aria-hidden="true"><path d="M20 115 A90 90 0 0 1 200 115" fill="none" stroke="var(--surface-3)" stroke-width="12" stroke-linecap="round"/><path d="M20 115 A90 90 0 0 1 ${110 + 90 * Math.cos(ang)} ${115 - 90 * Math.sin(ang)}" fill="none" stroke="var(--recovery)" stroke-width="12" stroke-linecap="round"/><circle cx="${110 + 90 * Math.cos(ang)}" cy="${115 - 90 * Math.sin(ang)}" r="7" fill="var(--surface)" stroke="var(--recovery)" stroke-width="3"/></svg>
      <div class="val"><b>${fmt.n(B.value, 1)}</b><span class="small" style="color:${diff >= 0 ? "var(--ok)" : "var(--warn)"}">${fmt.n(Math.abs(diff), 1)} years ${diff >= 0 ? "younger" : "older"}</span></div></div>
      ${isNum(B.vs_last_week) ? badge(`${fmt.signed(B.vs_last_week, 1)} from last week`, "") : ""}<p class="cap">Next update in ${B.next_update_days} day${B.next_update_days === 1 ? "" : "s"} (Mondays) · ${badge("Estimate", "est")}</p>
      <div class="insight" style="text-align:left"><span class="spark">✓</span><div><b>${B.confidence_pct}% confidence</b><span>${B.blood_missing.length ? "Blood markers missing: " + esc(B.blood_missing.join(", ")) : "All inputs present"}</span></div></div></div></div>
    <div class="stack"><div class="card"><h3>By category</h3><div class="list">${Object.values(B.categories).map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.label)}</div><div class="s">${Object.entries(c.inputs).filter(([, v]) => v !== null).map(([k, v]) => esc(fmt.sport(k)) + " " + esc(String(v))).join(" · ")}</div></div><div class="r" style="color:${c.delta_years <= 0 ? "var(--ok)" : "var(--warn)"}">${fmt.n(Math.abs(c.delta_years), 1)} yrs ${c.delta_years <= 0 ? "younger" : "older"}</div></div>`).join("")}</div></div>
    ${B.this_week_changes.length ? `<div class="card"><h3>This week's changes</h3><div class="list">${B.this_week_changes.map(c => `<div class="li"><div class="grow small">${esc(c.label)}</div><div class="r small">${fmt.signed(c.delta, 1)} yrs</div></div>`).join("")}</div></div>` : ""}
    <div class="card"><h3>Methodology</h3><p class="small muted">${esc(B.methodology)}</p></div></div></div>`;
}

function bodyRecords() {
  const H = D.health.records;
  if (!H.enabled) return empty("Health records module is off", "Enable it in profile.modules");
  const bms = Object.entries(H.biomarkers);
  return `<div class="cols"><div class="card"><h3>${icon("hrec")} Records</h3>${H.records.length ? `<div class="list">${H.records.map(r => `<div class="li"><div class="grow"><div class="t">${esc(r.title)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })} · ${esc(fmt.sport(r.type))}${r.provider ? " · " + esc(r.provider) : ""}${r.file ? " · document" : ""}</div></div><div class="r small">${(r.biomarkers || []).length} markers</div></div>`).join("")}</div>` : empty(STR.noRecords, "Add labs, notes or PDFs through your AGame server. Records stay private and out of coaching unless you opt in.")}${offlineNote()}</div>
    <div class="card"><h3>Biomarkers</h3>${bms.length ? `<table class="tbl"><tr><th>Marker</th><th class="r">Latest</th><th class="r">Lab range</th></tr>${bms.map(([k, list]) => { const l = list[list.length - 1]; return `<tr><td>${esc(l.name)}</td><td class="r">${fmt.n(l.value, 1)} ${esc(l.unit)}</td><td class="r faint">${isNum(l.ref_low) && isNum(l.ref_high) ? `${l.ref_low}–${l.ref_high}` : esc(l.ref_text || "—")}</td></tr>`; }).join("")}</table><p class="cap">Ranges are the lab's own. AGame does not interpret or diagnose.</p>` : empty("No biomarkers yet")}</div></div>`;
}
