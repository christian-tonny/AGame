/* Nutrition and Body (weight, VO2 max, custom charts, blood pressure, Biological Age, Health Records) */
"use strict";

AG.screens.nutrition = {
  title: "Nutrition",
  render() {
    const N = D.nutrition;
    if (!N.connected) return `${empty(STR.noNutrition, `Log meals through your AGame server, or have ${AGENT} import nutrition from HealthKit. Calories and protein never show as zero when nothing is logged.`)}
      <div class="card" style="margin-top:16px">${cardHead("Add a meal")}${mealForm()}</div>`;
    const tab = chipVal("nut-tab", "today");
    const body = { today: nutToday, diary: nutDiary, trends: nutTrends, plan: nutPlan }[tab]();
    return `${tabs("nut-tab", [["today", "Today"], ["diary", "Diary"], ["trends", "Trends"], ["plan", "Recipes & plan"]], tab)}${body}`;
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
  const score = N.last_score;
  const scoreWhen = score ? (score.date === addDays(D.meta.build_date, -1) ? "Yesterday" : fmt.dateY(score.date)) : "";
  const left = k => isNum(tgt[k]) && t && isNum(t[k]) ? Math.max(0, tgt[k] - t[k]) : null;
  return `<div class="cols"><div class="stack">
    <div class="card">${cardHead("Protein", `<span class="small muted">${pr.target ? `Target ${fmt.n(pr.target)} g` : "No target set"}</span>`)}
      <div class="spread" style="margin-bottom:8px;align-items:flex-end"><div class="stat hero"><span class="v">${pv === null ? "—" : fmt.n(pv)}<small>g</small></span></div><div style="text-align:right" class="small">${pr.target && pv !== null ? `<b>${fmt.n(Math.max(0, pr.target - pv))} g</b> to go` : ""}</div></div>
      ${bar(ppct, "var(--protein)")}
      <div class="stats-grid s3" style="margin-top:12px">${stat("Yesterday", isNum(pr.yesterday) ? fmt.n(pr.yesterday) + " g" : "—")}${stat("7-day avg", isNum(pr.avg_7) ? fmt.n(pr.avg_7) + " g" : "—")}${stat("Days hit", isNum(pr.days_hit_7) ? `${pr.days_hit_7}/${pr.days_logged_7}` : "—")}</div>
      ${pr.per_meal_today.length ? `<div class="list" style="margin-top:8px">${pr.per_meal_today.map(m => `<div class="li"><div class="grow small">${esc(fmt.sport(m.meal || "Meal"))} · ${fmt.time(m.t)}</div><div class="r small">${fmt.n(m.protein_g)} g</div></div>`).join("")}</div>` : ""}</div>
    <div class="card">${cardHead("Macros", `<span class="small muted">${t ? "Today" : y ? "Yesterday" : ""}</span>`)}
      ${mp ? `<div class="dots">${[["fat_g", "Fat", "var(--fat)"], ["carbs_g", "Carbs", "var(--carbs)"], ["protein_g", "Protein", "var(--protein)"]].map(([k, n, c]) => `<div class="dotcol">${dm(mp[k], c)}<b>${mp[k]}%</b><span style="color:${c}">${n}</span>${isNum(left(k)) ? `<div class="cap">${fmt.n(left(k))} g left</div>` : ""}</div>`).join("")}</div>` : `<p class="small muted" style="margin:0">No macros logged</p>`}</div>
    <div class="card">${cardHead("Net energy")}${net !== null ? `<div class="stat"><span class="v">${fmt.signed(net)}<small>kcal</small></span></div><div class="row small muted">${icon("flame")} ${fmt.n(day.energy_out.total)} out · ${fmt.n(day.kcal)} in</div>
      <div style="position:relative;height:10px;border-radius:999px;margin:12px 0 4px;background:linear-gradient(90deg,var(--strain),var(--carbs),var(--sleep))"><i style="position:absolute;top:-3px;width:4px;height:16px;border-radius:2px;background:var(--text);left:calc(${Math.max(0, Math.min(100, (net + 500) / 10))}% - 2px)"></i></div>
      <div class="spread cap"><span>−500</span><span>0</span><span>+500</span></div>${day.net_partial ? `<div class="st-line partial"><span class="dot"></span>${day.complete === true ? "Energy out incomplete" : "Day in progress"}</div>` : ""}` : `<p class="small muted" style="margin:0">Needs logged food and HealthKit energy</p>`}</div></div>
    <div class="stack"><div class="card">${cardHead("Nutrition score", scoreWhen ? `<span class="small muted">${esc(scoreWhen)}</span>` : "")}
      ${score ? `<div class="stat hero" style="margin-bottom:8px"><span class="v">${score.score}<small>/ 100</small></span></div><div class="list">${Object.entries(score.components).map(([k, v]) => `<div class="li"><div class="grow small">${esc(fmt.sport(k))}</div><div class="r small">${v}</div></div>`).join("")}</div>
      ${score.contributors.length ? `<div class="sub-h">Quality</div>` + score.contributors.map(c => `<div class="row" style="gap:10px;margin:6px 0"><span class="small" style="width:96px">${esc(c.label)}</span><div class="bar thin" style="flex:1"><i style="width:${Math.min(100, Math.abs(c.points) * 10)}%;background:${c.points >= 0 ? "var(--ok)" : "var(--bad)"}"></i></div><span class="small num" style="width:36px;text-align:right">${fmt.signed(c.points, 0)}</span></div>`).join("") : ""}
      ${score.missing_components.length ? `<div class="st-line partial"><span class="dot"></span>No ${esc(score.missing_components.join(", "))} target</div>` : ""}` : `<p class="small muted" style="margin:0">Scored once a fully logged day is over</p>`}</div>
    <div class="card">${cardHead("Hydration & caffeine", `${editBtn("water-add", undefined, "+ Water")}${editBtn("caffeine-add", undefined, "+ Caffeine")}`)}<div class="stats-grid">${stat("Water", t && isNum(t.water_ml) ? fmt.n(t.water_ml) : "—", "ml", { d: isNum(tgt.water_ml) ? `<span class="cap">of ${fmt.n(tgt.water_ml)} ml</span>` : "" })}${stat("Caffeine", t && isNum(t.caffeine_mg) ? fmt.n(t.caffeine_mg) : "—", "mg", { d: tgt.caffeine_cutoff ? `<span class="cap">cutoff ${esc(tgt.caffeine_cutoff)}</span>` : "" })}</div></div>
    <div class="card">${cardHead("Meals today")}${t && t.per_meal.length ? `<div class="list">${t.per_meal.map(m => `<div class="li" ${AG.online ? `role="button" tabindex="0" data-open="meal-edit" data-arg="${esc(m.id)}"` : ""}><div class="grow"><div class="t">${esc(m.name || fmt.sport(m.meal))}</div><div class="s">${fmt.time(m.t)} · ${esc(m.items.join(", "))}</div></div><div class="r small">${fmt.n(m.kcal)} kcal<div class="cap">${fmt.n(m.protein_g)} g protein</div></div></div>`).join("")}</div>` : `<p class="small muted" style="margin:0">Nothing logged yet today</p>`}
      ${AG.online ? `<details style="margin-top:12px"><summary class="link" style="cursor:pointer">Add a meal</summary>${mealForm()}</details>` : ""}</div>
    ${N.glucose ? `<div class="card">${cardHead("Glucose")}${chart({ id: "glu", label: "Glucose samples", x: N.glucose.points.map(p => p.t), h: 130, series: [{ name: "Glucose", color: "var(--warn)", values: N.glucose.points.map(p => p.v) }], fmtX: t => fmt.time(t), fmtY: v => fmt.n(v) + " mg/dL" })}</div>` : ""}</div></div>`;
}

function mealNow() { const h = new Date().getHours(); return h < 10 ? "breakfast" : h < 15 ? "lunch" : h < 21 ? "dinner" : "snack"; }
function mealForm() {
  return `<form class="form" id="meal-form" style="margin-top:8px">
    <div class="grid g2"><label>Meal <select name="meal">${["breakfast", "lunch", "dinner", "snack"].map(m => `<option value="${m}" ${m === mealNow() ? "selected" : ""}>${fmt.sport(m)}</option>`).join("")}</select></label><label>Time <input name="t" type="datetime-local" value="${nowInput()}" required></label></div>
    <label>Describe it <input name="name" placeholder="e.g. Chicken, rice, beans" required></label>
    <div class="grid g4"><label>kcal <input name="kcal" inputmode="decimal"></label><label>Protein g <input name="protein_g" inputmode="decimal"></label><label>Carbs g <input name="carbs_g" inputmode="decimal"></label><label>Fat g <input name="fat_g" inputmode="decimal"></label></div>
    <div class="actions" style="margin-top:0"><button class="btn" ${AG.online ? "" : "disabled"}>Save meal</button></div></form>`;
}
function bindMealForm() {
  const f = $("#meal-form");
  if (!f) return;
  f.onsubmit = async e => {
    e.preventDefault();
    const num = k => f[k].value === "" ? null : +f[k].value;
    const item = { name: f.name.value, qty: 1, unit: "serving", kcal: num("kcal"), protein_g: num("protein_g"), carbs_g: num("carbs_g"), fat_g: num("fat_g") };
    try { await save("POST", "entries/nutrition.meals", { t: inputToIso(f.t.value), meal: f.meal.value, name: f.name.value, items: [item] }, "Meal saved"); }
    catch (err) { /* shown */ }
  };
}

function nutDiary() {
  const days = D.nutrition.days.slice().reverse().slice(0, 21);
  return `<div class="stack">${days.map(d => `<div class="card">${cardHead(`${fmt.dow(d.date)} ${fmt.date(d.date)}`, `<span class="small muted">${isNum(d.kcal) ? fmt.n(d.kcal) + " kcal" : "—"} · ${isNum(d.protein_g) ? fmt.n(d.protein_g) + " g protein" : "—"}${d.complete === false ? " · incomplete" : d.complete === null ? " · in progress" : ""}</span>${AG.online ? `<button class="btn sm secondary" data-open="day-copy" data-arg="${d.date}">Copy</button>` : ""}`)}
    <div class="list">${d.per_meal.map(m => `<div class="li">${AG.online ? `<input type="checkbox" data-meal-pick value="${esc(m.id)}" aria-label="Select ${esc(m.name || m.meal)}" style="width:20px;height:20px;flex:none">` : ""}<div class="grow" ${AG.online ? `role="button" tabindex="0" data-open="meal-edit" data-arg="${esc(m.id)}"` : ""}><div class="t small">${esc(m.name || fmt.sport(m.meal))}</div><div class="s">${fmt.time(m.t)} · ${esc(m.items.join(", "))}</div></div><div class="r small">${fmt.n(m.protein_g)} g</div></div>`).join("")}</div></div>`).join("")}
    ${AG.online ? `<div class="actions"><button class="btn" data-open="recipe-from-selected">Make recipe from selected</button></div>` : ""}</div>`;
}

function nutTrends() {
  const rng = chipVal("nut-range", "30");
  const days = sliceDays(D.nutrition.days.filter(d => d.complete !== false || d.date === D.meta.build_date), rangeDays(rng));
  const pt = D.nutrition.targets.protein_g, kt = D.nutrition.targets.kcal;
  return `<div class="page-tools">${seg("nut-range", RANGES_DWMY, rng)}</div><div class="cols"><div class="stack">
    <div class="card">${cardHead("Protein")}${chart({ id: "n-p", type: "bar", label: "Daily protein", x: days.map(d => d.date), h: 150, series: [{ name: "Protein", color: (i, v) => pt && v >= pt ? "var(--protein)" : "color-mix(in srgb, var(--protein) 55%, transparent)", values: days.map(d => d.protein_g) }], refLines: pt ? [{ y: pt, label: "target" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " g" })}</div>
    <div class="card">${cardHead("Calories")}${chart({ id: "n-k", type: "bar", label: "Daily calories", x: days.map(d => d.date), h: 150, series: [{ name: "Calories", color: "var(--carbs)", values: days.map(d => d.kcal) }], refLines: kt ? [{ y: kt, label: "target" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " kcal" })}</div></div>
    <div class="stack"><div class="card">${cardHead("Macro split")}${chart({ id: "n-m", type: "bar", stacked: true, label: "Macro percentages", x: days.map(d => d.date), h: 150, yMin: 0, yMax: 100, series: [["fat_g", "Fat", "var(--fat)"], ["carbs_g", "Carbs", "var(--carbs)"], ["protein_g", "Protein", "var(--protein)"]].map(([k, n, c]) => ({ name: n, color: c, values: days.map(d => d.macro_pct ? d.macro_pct[k] : null) })), fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + "%" })}</div>
    <div class="card">${cardHead("Net energy")}${chart({ id: "n-net", type: "bar", label: "Net energy", x: days.map(d => d.date), h: 150, series: [{ name: "Net", color: (i, v) => v < 0 ? "var(--ok)" : "var(--warn)", values: days.map(d => isNum(d.net_kcal) ? d.net_kcal : null) }], fmtX: d => fmt.date(d), fmtY: v => fmt.signed(v) + " kcal" })}</div>
    <div class="card">${cardHead("Nutrition score")}${chart({ id: "n-s", label: "Nutrition score", x: days.map(d => d.date), h: 130, yMin: 0, yMax: 100, series: [{ name: "Score", color: "var(--ok)", values: days.map(d => d.score ? d.score.score : null), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) })}</div></div></div>`;
}

function nutPlan() {
  const N = D.nutrition;
  return `<div class="cols"><div class="stack"><div class="card">${cardHead("Recipes")}${N.recipes.length ? `<div class="list">${N.recipes.map(r => `<div class="li" ${AG.online ? `role="button" tabindex="0" data-open="recipe" data-arg="${esc(r.id)}"` : ""}><div class="grow"><div class="t">${esc(r.name)}${r.favorite ? `<span class="fav">${icon("star-filled")}</span>` : ""}</div><div class="s">${r.items.map(i => esc(i.name)).join(", ")}</div></div><div class="r small">${fmt.n(r.items.reduce((s, i) => s + (i.protein_g || 0), 0))} g P</div></div>`).join("")}</div>` : empty("No recipes yet")}
</div><div class="card">${cardHead("Favorites")}${N.favorites.length ? `<div class="list">${N.favorites.map(i => `<div class="li"><div class="grow"><div class="t">${esc(i.name)}</div></div><div class="r small">${fmt.n(i.kcal)} kcal</div></div>`).join("")}</div>` : empty("No favorites yet")}</div></div>
    <div class="card">${cardHead("Planned meals")}${N.planned.length ? `<div class="list">${N.planned.map(p => `<div class="li"><div class="grow"><div class="t">${fmt.dow(p.date)} ${fmt.date(p.date)} · ${esc(p.meal || "")}</div><div class="s">${esc((N.recipes.find(r => r.id === p.recipe_id) || {}).name || p.items.map(i => i.name).join(", "))}</div></div>${AG.online && p.id ? `<button type="button" class="icon-btn" data-open="planned-meal" data-arg="${esc(p.id)}" aria-label="Remove planned meal">${icon("x")}</button>` : ""}</div>`).join("")}</div>` : empty("Nothing planned", "Open a recipe and choose Plan it")}</div></div>`;
}

/* ---------------- Body ---------------- */
AG.screens.body = {
  title: "Body",
  render(r) {
    const tab = r.params.tab || chipVal("body-tab", "overview");
    if (r.params.tab) uiSet("chip:body-tab", r.params.tab);
    const body = { overview: bodyOverview, weight: bodyWeight, vo2: bodyVO2, charts: bodyCharts, bp: bodyBP, bioage: bodyBioAge, records: bodyRecords }[tab] || bodyWeight;
    const add = ["weight", "bp"].includes(tab) && AG.online ? `<div class="page-tools">${editBtn("measure-add", undefined, tab === "bp" ? "Add reading" : "Add measurement")}</div>` : "";
    return `${tabs("body-tab", [["overview", "Overview"], ["weight", "Weight"], ["vo2", "VO2 max"], ["charts", "Charts"], ["bp", "Blood pressure"], ["bioage", "Biological Age"], ["records", "Health records"]], tab)}${add}${body()}`;
  },
  after() { drawCharts(); },
};

function bodyOverview() {
  const m = D.body.metrics, W = D.body.weight, V = D.body.vo2max, B = D.health.bioage, comp = (W.composition || {});
  const tail = (pts, n = 60) => seriesTail(pts, "v", n);
  const go = t => `#/body?tab=${t}`;
  const latestLine = x => x && x.latest_date ? statusLine(`${x.latest_date === D.meta.build_date ? "" : fmt.date(x.latest_date) + " · "}7-day avg ${fmt.n(x.avg_7, x.avg_7 < 100 ? 1 : 0)} ${x.unit}`, null) : statusLine("No data", null);
  const rows = [
    W.status !== "missing" ? trendRow({ label: "Weight · 7-day median", value: fmt.kgNum(W.current.v), unit: fmt.wUnit(), href: go("weight"), spark: tail(W.median_7d, 90), color: "var(--accent)",
      status: isNum(W.trend_kg_per_week.v) ? statusLine(`${fmt.signed(IMPERIAL ? W.trend_kg_per_week.v * 2.20462 : W.trend_kg_per_week.v, 2)} ${fmt.wUnit()} a week`, null, W.trend_kg_per_week.v < 0 ? "down" : "up") : "" }) : "",
    m.hrv_sdnn_ms ? trendRow({ label: "HRV", value: fmt.n(m.hrv_sdnn_ms.latest, 1), unit: "ms", href: "#/recovery", spark: tail(m.hrv_sdnn_ms.points), color: "var(--recovery)", status: latestLine(m.hrv_sdnn_ms) }) : "",
    m.resting_hr_bpm ? trendRow({ label: "Resting HR", value: fmt.n(m.resting_hr_bpm.latest, 1), unit: "bpm", href: "#/recovery", spark: tail(m.resting_hr_bpm.points), color: "var(--bad)", status: latestLine(m.resting_hr_bpm) }) : "",
    V.current && isNum(V.current.v) ? trendRow({ label: "VO₂ max", value: fmt.n(V.current.v, 1), unit: "ml/kg/min", href: go("vo2"), spark: tail(V.smoothed || V.points, 90), color: "var(--ok)", status: statusLine(`${fmt.date(V.current.as_of.slice(0, 10))} · ${fmt.signed(V.delta_90, 1)} in 90 days`, null) }) : "",
    comp.body_fat_pct ? trendRow({ label: "Body fat", value: fmt.n(comp.body_fat_pct.current, 1), unit: "%", href: go("weight"), spark: tail(comp.body_fat_pct.points), color: "var(--warn)", status: statusLine(fmt.date(comp.body_fat_pct.as_of.slice(0, 10)), null) }) : "",
    D.body.bp && D.body.bp.systolic ? trendRow({ label: "Blood pressure", value: `${fmt.n(D.body.bp.systolic.latest)}/${fmt.n(D.body.bp.diastolic.latest)}`, unit: "mmHg", href: go("bp"), spark: tail(D.body.bp.systolic.points), color: "var(--info)", status: statusLine(fmt.date(D.body.bp.systolic.latest_date), null) }) : "",
    m.respiratory_rate_brpm ? trendRow({ label: "Respiratory rate", value: fmt.n(m.respiratory_rate_brpm.latest, 1), unit: "br/min", href: go("charts"), spark: tail(m.respiratory_rate_brpm.points), color: "var(--sleep-2)", status: latestLine(m.respiratory_rate_brpm) }) : "",
    m.spo2_pct ? trendRow({ label: "Blood oxygen", value: fmt.n(m.spo2_pct.latest, 1), unit: "%", href: go("charts"), spark: tail(m.spo2_pct.points), color: "var(--st-rem)", status: latestLine(m.spo2_pct) }) : "",
  ].filter(Boolean);
  const bio = B.status === "ok" ? `<a class="card bio-hero" href="${go("bioage")}"><span class="go">${icon("arrow")}</span><div class="tile-h"><span>Biological age</span><span class="est-tag">Estimate</span></div>
    <div class="bio-v">${fmt.n(B.value, 1)}<small>years</small></div>${statusLine(`${fmt.n(Math.abs(B.chronological - B.value), 1)} years ${B.chronological >= B.value ? "younger" : "older"} than your age`, B.chronological >= B.value)}</a>` : "";
  return `${bio}<div class="body-biomarkers">${sectionTitle("Biomarkers")}<div class="biomarker-grid">${rows.join("") || empty(STR.noData)}</div></div>`;
}

function bodyWeight() {
  const W = D.body.weight;
  if (W.status === "missing") return empty(STR.noWeight, "Weight comes from HealthKit body mass or your own entries (Add measurement)");
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
  return `<div class="cols"><div class="stack"><div class="card">${cardHead("Weight", "", `7-day median of your weigh-ins.${isNum(W.current.latest) ? ` Latest weigh-in ${fmt.kg(W.current.latest)} on ${fmt.dateY(W.current.latest_date)}.` : ""}`, W.current)}<div class="spread" style="align-items:flex-end"><div class="stat hero"><span class="v">${fmt.kgNum(W.current.v)}<small>${fmt.wUnit()}</small></span></div>
      <div style="text-align:right">${stat("4-week trend", isNum(W.trend_kg_per_week.v) ? fmt.signed(conv(W.trend_kg_per_week.v), 2) : "—", fmt.wUnit() + "/wk", { d: !isNum(W.trend_kg_per_week.v) ? `<span class="cap">${esc(W.trend_kg_per_week.note)}</span>` : "" })}</div></div>${stLine(W.current)}</div>
    ${g ? `<div class="card">${cardHead(`Goal · ${fmt.kg(g.target)} by ${fmt.date(g.target_date, { day: "numeric", month: "short", year: "numeric" })}`, goalStatusBadge(g.status), `${isNum(g.weeks_left) ? fmt.n(g.weeks_left) + " weeks left. " : ""}The projection uses your current 4-week trend.`)}
      <div class="stats-grid s3">${stat("Remaining", fmt.kg(Math.abs(g.remaining_kg)))}${stat("Needed", isNum(g.required_kg_per_week) ? fmt.signed(conv(g.required_kg_per_week), 2) : "—", fmt.wUnit() + "/wk")}${stat("Projected", g.projected_date ? fmt.date(g.projected_date, { month: "short", year: "numeric" }) : "—")}</div>
      ${isNum(g.progress_pct) ? `<div style="margin-top:12px">${bar(g.progress_pct, "var(--accent)")}</div>` : ""}</div>` : `<div class="card">${empty(STR.noGoals, "Add a body-weight goal to see the trajectory")}</div>`}</div>
    <div class="stack"><div class="card">${cardHead("Trend", seg("w-range", [["30", "1M"], ["90", "3M"], ["180", "6M"], ["365", "1Y"], ["all", "All"]], rng))}
      ${chart({ id: "wt", label: "Weight with weekly median", x: pts.map(p => p.date), h: 210, gapMs: 10 * 86400000,
        series: [{ name: "Daily", color: "var(--text-3)", values: pts.map(p => conv(p.v)), dots: true, noLine: true, dotR: 2 }, { name: "Weekly median", color: "var(--accent)", values: medSeries, width: 2.4 }],
        refLines: g ? [{ y: conv(g.target), label: "goal", color: "var(--ok)" }] : [], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + fmt.wUnit(), range: rangeLabel(pts) })}</div>
    ${Object.keys(W.composition || {}).length ? `<div class="card">${cardHead("Body composition")}<div class="stats-grid">${Object.entries(W.composition).map(([k, c]) => stat(fmt.sport(k.replace(/_pct|_kg|_cm/, "")), fmt.n(c.current, 1), k.endsWith("pct") ? "%" : k.endsWith("kg") ? fmt.wUnit() : "cm", { d: `<span class="cap">${fmt.date(c.as_of)}</span>` })).join("")}</div></div>` : ""}</div></div>`;
}

function bodyVO2() {
  const V = D.body.vo2max;
  if (V.status === "missing") return `<div class="card">${empty(STR.noVO2, "VO2 max comes only from HealthKit cardio-fitness samples; AGame never estimates it from pace.")}</div>`;
  const rng = chipVal("vo2-range", "365");
  const pts = sliceDays(V.points, rangeDays(rng)), sm = sliceDays(V.smoothed, rangeDays(rng));
  const smMap = {}; sm.forEach(s => smMap[s.date] = s.v);
  return `<div class="cols"><div class="stack"><div class="card">${cardHead("VO2 max", "", "", V.current)}<div class="stat hero"><span class="v">${fmt.n(V.current.v, 1)}<small>ml/kg/min</small></span><span class="cap">${fmt.date(V.current.as_of)}</span></div>
      <div class="stats-grid s4" style="margin-top:16px">${stat("Trend", fmt.n(V.smoothed_current, 1))}${stat("30 days", isNum(V.delta_30) ? fmt.signed(V.delta_30, 1) : "—")}${stat("90 days", isNum(V.delta_90) ? fmt.signed(V.delta_90, 1) : "—")}${stat("Confidence", esc(fmt.sport(V.confidence)), "", { d: `<span class="cap">${V.samples_90d} in 90 days</span>` })}</div>${stLine(V.current)}</div>
    ${V.gaps.length ? `<div class="card">${cardHead("Data gaps")}<div class="list">${V.gaps.map(g => `<div class="li"><div class="grow small">${fmt.date(g.from)} → ${fmt.date(g.to)}</div><div class="r small">${g.days} days</div></div>`).join("")}</div></div>` : ""}</div>
    <div class="card">${cardHead("Trend", seg("vo2-range", RANGES_DWMY.slice(1), rng), "Raw HealthKit cardio-fitness samples with a ±21-day rolling mean. AGame never estimates VO2 max from pace.")}${chart({ id: "vo2", label: "VO2 max samples and trend", x: pts.map(p => p.date), h: 210,
      series: [{ name: "Samples", color: "var(--text-3)", values: pts.map(p => p.v), dots: true, noLine: true }, { name: "Smoothed trend", color: "var(--info)", values: pts.map(p => smMap[p.date] !== undefined ? smMap[p.date] : null), width: 2.4 }],
      fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1), range: rangeLabel(pts) })}</div></div>`;
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
  const isPinned = pinned.includes(m.id);
  const pins = pinned.filter(x => M[x]);
  return `<div class="stack"><div class="card">${cardHead("Pinned", "", "Star a chart to pin it here. Use the arrows to reorder.")}<div class="grid g4">${pins.map((x, i) => `<div class="card tight flat"><button class="grow" style="text-align:left;width:100%" data-chip="cc-metric" data-val="${esc(x)}"><div class="cap">${esc(M[x].label)}</div><b>${fmt.n(M[x].latest, M[x].latest % 1 ? 1 : 0)} <small class="muted">${esc(M[x].unit)}</small></b>${sparkline(M[x].points.slice(-30).map(p => p.v), "var(--accent)")}</button>${AG.online ? `<div class="row" style="justify-content:space-between;margin-top:4px"><button type="button" class="icon-btn" data-pin-move="${esc(x)}" data-dir="-1" aria-label="Move ${esc(M[x].label)} earlier" ${i === 0 ? "disabled" : ""}>${icon("back")}</button><button type="button" class="icon-btn" data-pin-move="${esc(x)}" data-dir="1" aria-label="Move ${esc(M[x].label)} later" ${i === pins.length - 1 ? "disabled" : ""}>${icon("next")}</button></div>` : ""}</div>`).join("") || `<p class="small muted" style="margin:0">Nothing pinned</p>`}</div></div>
    ${chips("cc-metric", ids.map(id => [id, M[id].label]), m.id)}
    <div class="card">${cardHead(`${esc(m.label)}${AG.online ? ` <button type="button" class="icon-btn" data-chart-pin="${esc(m.id)}" aria-pressed="${isPinned}" aria-label="${isPinned ? "Unpin" : "Pin"} ${esc(m.label)}">${icon(isPinned ? "star-filled" : "star")}</button>` : ""}`, `${seg("cc-agg", [["day", "Day"], ["week", "Week"]], agg)}${seg("cc-range", RANGES_DWMY, rng)}`)}
      <div class="stats-grid s3" style="margin-bottom:12px">${stat("Latest", fmt.n(m.latest, m.latest % 1 ? 1 : 0), m.unit, { d: `<span class="cap">${fmt.date(m.latest_date)}</span>` })}${stat("7-day avg", fmt.n(m.avg_7, 1), m.unit)}${stat(ytd.length ? (m.agg === "sum" ? "Year total" : "Year avg") : "Prior 4 weeks", ytd.length ? (m.agg === "sum" ? fmt.n(ytd.reduce((a, p) => a + p.v, 0)) : fmt.n(ytd.reduce((a, p) => a + p.v, 0) / ytd.length, 1)) : fmt.n(m.avg_prev_28, 1), m.unit)}</div>
      ${chart({ id: "cc", type: m.agg === "sum" ? "bar" : "line", label: m.label + " history", x: pts.map(p => p.date), h: 200, gapMs: agg === "week" ? 15 * 86400000 : 3.5 * 86400000,
        series: [{ name: m.label, color: "var(--accent)", values: pts.map(p => p.v), dots: m.agg !== "sum" && pts.length < 60 }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + m.unit, range: rangeLabel(pts) })}
</div></div>`;
}

document.addEventListener("click", e => {
  const pin = e.target.closest("[data-chart-pin]"), mv = e.target.closest("[data-pin-move]");
  if (!pin && !mv) return;
  let list = ((P.ui || {}).pinned_charts || []).slice();
  if (pin) list = pin.getAttribute("aria-pressed") === "true" ? list.filter(x => x !== pin.dataset.chartPin) : list.concat([pin.dataset.chartPin]);
  if (mv) { const i = list.indexOf(mv.dataset.pinMove), j = i + +mv.dataset.dir; if (i < 0 || j < 0 || j >= list.length) return; [list[i], list[j]] = [list[j], list[i]]; }
  save("PATCH", "profile", { ui: Object.assign({}, P.ui || {}, { pinned_charts: list }) }, "Charts updated").catch(() => {});
});
function bodyBP() {
  const bp = D.body.bp;
  if (!bp.systolic || !bp.diastolic) return `<div class="card">${empty("No blood pressure readings", "From HealthKit or manual entries. AGame shows readings only, with no categories or diagnosis.")}</div>`;
  const sMap = {}; bp.diastolic.points.forEach(p => sMap[p.date] = p.v);
  const pts = bp.systolic.points;
  return `<div class="cols"><div class="card">${cardHead("Latest reading", "", "Readings only, with no categories or diagnosis. Talk to a clinician about what your numbers mean.")}<div class="stat hero"><span class="v">${fmt.n(bp.systolic.latest)}/${fmt.n(bp.diastolic.latest)}<small>mmHg</small></span><span class="cap">${fmt.date(bp.systolic.latest_date)} · 7-day average ${fmt.n(bp.systolic.avg_7)}/${fmt.n(bp.diastolic.avg_7)}</span></div></div>
    <div class="card">${cardHead("History")}${chart({ id: "bp", label: "Blood pressure readings", x: pts.map(p => p.date), h: 190, series: [{ name: "Systolic", color: "var(--bad)", values: pts.map(p => p.v), dots: true }, { name: "Diastolic", color: "var(--info)", values: pts.map(p => sMap[p.date] !== undefined ? sMap[p.date] : null), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " mmHg" })}</div></div>`;
}

function bodyBioAge() {
  const B = D.health.bioage;
  if (B.status !== "ok") return `<div class="card">${cardHead("Biological Age", badge("Estimate", "est"), esc(B.methodology))}${empty("Not enough inputs yet", "Needed: " + (B.needed || []).join(" · "))}</div>`;
  const diff = B.chronological - B.value;
  const pct = Math.max(0, Math.min(1, (B.value - (B.chronological - 10)) / 20));
  const ang = Math.PI * (1 - pct);
  return `<div class="cols"><div class="stack"><div class="card">${cardHead(`Biological Age`, badge(fmt.date(B.as_of) + " · Estimate", "est"), esc(B.methodology))}<div style="text-align:center">
      <div class="gauge"><svg viewBox="0 0 220 130" aria-hidden="true"><path d="M20 115 A90 90 0 0 1 200 115" fill="none" stroke="var(--surface-3)" stroke-width="12" stroke-linecap="round"/><path d="M20 115 A90 90 0 0 1 ${110 + 90 * Math.cos(ang)} ${115 - 90 * Math.sin(ang)}" fill="none" stroke="var(--recovery)" stroke-width="12" stroke-linecap="round"/><circle cx="${110 + 90 * Math.cos(ang)}" cy="${115 - 90 * Math.sin(ang)}" r="7" fill="var(--surface)" stroke="var(--recovery)" stroke-width="3"/></svg>
      <div class="val"><b>${fmt.n(B.value, 1)}</b><span class="small" style="color:${diff >= 0 ? "var(--ok)" : "var(--warn)"}">${fmt.n(Math.abs(diff), 1)} years ${diff >= 0 ? "younger" : "older"}</span></div></div>
</div>
      <div class="stats-grid s3" style="margin-top:12px">${stat("This week", isNum(B.vs_last_week) ? fmt.signed(B.vs_last_week, 1) : "—", "yrs")}${stat("Confidence", B.confidence_pct + "%")}${stat("Next update", B.next_update_days + (B.next_update_days === 1 ? " day" : " days"))}</div>
      ${B.blood_missing.length ? `<div class="st-line partial"><span class="dot"></span>No blood markers: ${esc(B.blood_missing.join(", "))}</div>` : ""}</div></div>
    <div class="stack"><div class="card">${cardHead("By category")}<div class="list">${Object.values(B.categories).map(c => `<div class="li"><div class="grow"><div class="t">${esc(c.label)}</div><div class="s">${Object.entries(c.inputs).filter(([, v]) => v !== null).map(([k, v]) => esc(fmt.sport(k)) + " " + esc(String(v))).join(" · ")}</div></div><div class="r" style="color:${c.delta_years <= 0 ? "var(--ok)" : "var(--warn)"}">${fmt.n(Math.abs(c.delta_years), 1)} yrs ${c.delta_years <= 0 ? "younger" : "older"}</div></div>`).join("")}</div></div>
    ${B.this_week_changes.length ? `<div class="card">${cardHead("This week's changes")}<div class="list">${B.this_week_changes.map(c => `<div class="li"><div class="grow small">${esc(c.label)}</div><div class="r small">${fmt.signed(c.delta, 1)} yrs</div></div>`).join("")}</div></div>` : ""}
</div></div>`;
}

function bodyRecords() {
  const H = D.health.records;
  if (!H.enabled) return empty("Health records module is off", "Enable it in profile.modules");
  const bms = Object.entries(H.biomarkers);
  return `<div class="cols"><div class="card">${cardHead("Records", editBtn("record-add", undefined, "Add"), "Records stay private, behind sign-in, and out of coaching unless you opt in.")}${H.records.length ? `<div class="list">${H.records.map(r => `<div class="li"><div class="grow"><div class="t">${esc(r.title)}</div><div class="s">${fmt.date(r.date, { day: "numeric", month: "short", year: "numeric" })} · ${esc(fmt.sport(r.type))}${r.provider ? " · " + esc(r.provider) : ""}${r.file && AG.online ? ` · <a href="records/${encodeURIComponent(r.file)}">open file</a>` : r.file ? " · file (server only)" : ""}</div></div><div class="r small">${(r.biomarkers || []).length} markers</div>${AG.online && r.kind === "user_entered" ? `<button type="button" class="icon-btn" data-open="record-del" data-arg="${esc(r.id)}" aria-label="Delete record">${icon("x")}</button>` : ""}</div>`).join("")}</div>` : empty(STR.noRecords, "Add labs, notes or PDFs")}</div>
    <div class="card">${cardHead("Biomarkers", "", "Ranges are the lab's own. AGame does not interpret or diagnose.")}${bms.length ? `<table class="tbl"><tr><th>Marker</th><th class="r">Latest</th><th class="r">Lab range</th></tr>${bms.map(([k, list]) => { const l = list[list.length - 1]; return `<tr><td>${esc(l.name)}</td><td class="r">${fmt.n(l.value, 1)} ${esc(l.unit)}</td><td class="r faint">${isNum(l.ref_low) && isNum(l.ref_high) ? `${l.ref_low}–${l.ref_high}` : esc(l.ref_text || "—")}</td></tr>`; }).join("")}</table>` : empty("No biomarkers yet")}</div></div>`;
}
