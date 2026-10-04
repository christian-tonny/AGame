/* Edit sheets. Every write goes to the AGame server (entries API or a named Python action), which validates it,
   keeps before/after history, and rebuilds. Nothing here calculates a metric: values are typed in or picked
   from options Python already computed. Unit conversions (km/mi, kg/lb, mm:ss) are display only. */
"use strict";

const TYPE_LABELS = D.meta.type_labels || {};
const typeOptions = () => Object.entries(TYPE_LABELS).filter(([k]) => k !== "NPU").map(([k, v]) => [k, `${v} (${k})`]);
const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"];
const todayISO = () => D.meta.build_date;
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const nextDays = (n, from = todayISO()) => Array.from({ length: n }, (_, i) => addDays(from, i)).map(d => [d, `${fmt.dow(d)} ${fmt.date(d)}`]);
const kgIn = v => isNum(v) ? +(IMPERIAL ? v * 2.20462 : v).toFixed(1) : null;
const kgOut = v => isNum(v) ? (IMPERIAL ? v / 2.20462 : v) : null;
const paceIn = s => { if (!isNum(s)) return ""; const x = Math.round(IMPERIAL ? s * 1.609344 : s); return Math.floor(x / 60) + ":" + String(x % 60).padStart(2, "0"); };
const paceOut = v => { if (!v) return null; const m = String(v).trim().match(/^(\d{1,2}):(\d{2})$/); if (!m) throw new Error("Pace must look like 4:30"); const s = +m[1] * 60 + +m[2]; return IMPERIAL ? Math.round(s / 1.609344) : s; };
const csv = v => (v || "").split(",").map(x => x.trim()).filter(Boolean);

/* ================= Profile ================= */
AG.sheets["edit-athlete"] = () => formSheet("Athlete", [
  { name: "display_name", label: "Name", value: P.display_name, full: true },
  { name: "sex", label: "Sex (for TRIMP constants)", type: "select", value: P.sex || "", options: [["", "Not set"], ["female", "Female"], ["male", "Male"]] },
  { name: "birth_year", label: "Birth year", type: "number", value: P.birth_year, min: 1900, max: 2100, hint: "Used for biological age only, never for HR max" },
  { name: "height_cm", label: "Height (cm)", type: "number", value: P.height_cm, min: 50, max: 260 },
], v => save("PATCH", "profile", { athlete: { display_name: v.display_name, sex: v.sex || null, birth_year: v.birth_year, height_cm: v.height_cm } }, "Athlete saved"));

AG.sheets["edit-physiology"] = () => {
  const ph = P.physiology || {};
  const m = (k, method) => ({ value: ph[k] ? ph[k].value : null, method: ph[k] ? ph[k].method : method });
  const fields = [
    { name: "hr_max", label: "HR max (bpm)", type: "number", value: m("hr_max").value, min: 120, max: 230, hint: "Observed or tested. AGame never guesses it from age." },
    { name: "hr_rest", label: "Resting HR (bpm)", type: "number", value: m("hr_rest").value, min: 25, max: 110, hint: "Leave empty to use your 14-day HealthKit median" },
    { name: "lthr", label: "LTHR (bpm)", type: "number", value: m("lthr").value, min: 100, max: 220 },
    { name: "threshold_pace", label: `Threshold pace (min${fmt.paceUnit()})`, value: paceIn(m("threshold_pace_s_per_km").value), placeholder: "4:30" },
    { name: "ftp_w", label: "FTP (W)", type: "number", value: m("ftp_w").value, min: 50, max: 600 },
    { name: "sleep_need", label: "Base sleep need (min)", type: "number", value: m("sleep_need_base_min").value, min: 300, max: 660 },
    { name: "method", label: "How you got these", value: "", placeholder: "e.g. lab test, field test, race", full: true },
    { name: "model", label: "Zone model", type: "select", value: (P.zones_config || {}).model || "5zone", options: [["5zone", "5 zones (% of HR max)"], ["7zone", "7 zones (% of LTHR)"]], full: true },
  ];
  formSheet("Physiology & zones", fields, v => {
    const out = {};
    const put = (key, val) => {
      const cur = ph[key];
      if (val === null) { if (cur) out[key] = null; return; }
      if (cur && cur.value === val && !v.method) return;
      out[key] = { value: val, date: todayISO(), method: v.method || "set in app", kind: "configured", note: null };
    };
    put("hr_max", v.hr_max); put("hr_rest", v.hr_rest); put("lthr", v.lthr); put("ftp_w", v.ftp_w); put("sleep_need_base_min", v.sleep_need);
    let pace; try { pace = paceOut(v.threshold_pace); } catch (e) { toast(e.message); return Promise.reject(e); }
    put("threshold_pace_s_per_km", pace);
    if (isNum(v.hr_max) && isNum(v.lthr) && v.lthr >= v.hr_max) { toast("LTHR must be below HR max"); return Promise.reject(new Error("lthr")); }
    return save("PATCH", "profile", { physiology: out, zones: { model: v.model } }, "Physiology saved");
  });
};

AG.sheets["edit-locale"] = () => formSheet("Units & time", [
  { name: "timezone", label: "Time zone", value: (P.locale || {}).timezone || TZ, hint: "IANA name, e.g. Africa/Kigali", full: true },
  { name: "units", label: "Units", type: "select", value: (P.locale || {}).units || "metric", options: [["metric", "Metric (km, kg)"], ["imperial", "Imperial (mi, lb)"]] },
  { name: "week_start", label: "Week starts", type: "select", value: (P.locale || {}).week_start || "monday", options: [["monday", "Monday"], ["sunday", "Sunday"], ["saturday", "Saturday"]] },
], v => save("PATCH", "profile", { locale: v }, "Units saved"));

AG.sheets["edit-targets"] = () => {
  const t = P.targets || {};
  const n = (name, label, hint) => ({ name, label, type: "number", value: t[name], hint });
  formSheet("Daily targets", [n("protein_g", "Protein (g)"), n("kcal", "Calories (kcal)"), n("carbs_g", "Carbs (g)"), n("fat_g", "Fat (g)"), n("fiber_g", "Fiber (g)"),
    n("vegetables_g", "Vegetables (g)"), n("water_ml", "Water (ml)"), n("caffeine_mg_max", "Caffeine max (mg)"),
    { name: "caffeine_cutoff", label: "Caffeine cutoff", type: "time", value: t.caffeine_cutoff }, n("steps", "Steps"),
    n("sleep_min", "Sleep (min)"), { name: "wake_time", label: "Usual wake time", type: "time", value: t.wake_time }],
    v => save("PATCH", "profile", { targets: v }, "Targets saved"), { intro: "Leave a field empty for no target. AGame never fills in a default." });
};

AG.sheets["edit-appearance"] = () => {
  const ui = P.ui || {};
  const tabs = (ui.mobile_tabs || ["today", "training", "activities", "coach", "more"]).filter(x => x !== "more");
  const opts = DESTS.map(d => [d.id, d.label]);
  formSheet("Appearance", [
    { name: "theme", label: "Theme", type: "select", value: ui.theme || "system", options: [["system", "System"], ["dark", "Dark"], ["light", "Light"]] },
    { name: "app_icon", label: "App icon", type: "select", value: ui.app_icon || "default", options: [["default", "Orange (default)"], ["dark", "Dark"], ["light", "Light"]], hint: "Applied at the next build; re-add to home screen on iOS" },
    ...[0, 1, 2, 3].map(i => ({ name: "tab" + i, label: `Tab ${i + 1}`, type: "select", value: tabs[i] || DESTS[i].id, options: opts })),
  ], v => {
    const t = [v.tab0, v.tab1, v.tab2, v.tab3].filter((x, i, a) => x && a.indexOf(x) === i);
    uiSet("theme", v.theme); uiSet("chip:theme", v.theme);
    return save("PATCH", "profile", { ui: Object.assign({}, ui, { theme: v.theme, app_icon: v.app_icon, mobile_tabs: t.concat(["more"]) }) }, "Appearance saved");
  }, { intro: "The fifth tab is always More." });
};

AG.sheets["edit-schedule"] = () => {
  const tpl = {}; (P.schedule || []).forEach(s => tpl[s.weekday] = s);
  const intents = [["", "Nothing"], ["run", "Run"], ["lift", "Lift"], ["rest", "Rest"], ["optional_run", "Optional run"], ["cross_train", "Cross-train"], ["mobility", "Mobility"]];
  const fields = WEEKDAYS.flatMap(d => [
    { name: d, label: fmt.sport(d), type: "select", value: (tpl[d] || {}).intent || "", options: intents },
    { name: d + "_min", label: "Minutes", type: "number", value: tpl[d] && isNum(tpl[d].duration_s) ? tpl[d].duration_s / 60 : null, min: 0, max: 600 }]);
  formSheet("Weekly template", fields, v => save("PATCH", "profile", { schedule: { template: WEEKDAYS.filter(d => v[d]).map(d => ({ weekday: d, intent: v[d], duration_s: isNum(v[d + "_min"]) ? v[d + "_min"] * 60 : null, type: (tpl[d] || {}).type || null, available_from: (tpl[d] || {}).available_from || null, available_to: (tpl[d] || {}).available_to || null })) } }, "Template saved"),
    { intro: "Days with nothing planned in plans.json fall back to this template." });
};

AG.sheets["edit-privacy"] = () => {
  const pr = P.privacy || {};
  const zones = (pr.zones || []).map(z => `<div class="li"><div class="grow"><div class="t">${esc(z.label || z.id)}</div><div class="s">${fmt.n(z.radius_m)} m radius</div></div><button type="button" class="btn sm danger" data-zone-rm="${esc(z.id)}">Remove</button></div>`).join("");
  formSheet("Map privacy", [
    { name: "hide", label: "Hide start/end of every map (m)", type: "number", value: pr.hide_start_end_m, min: 0, max: 2000 },
    { name: "private", label: "New activities private by default", type: "checkbox", value: pr.default_activity_private },
    { name: "zl", type: "html", full: true, html: `<div class="cap" style="margin-top:6px">Privacy zones</div><div class="list">${zones || `<p class="small muted">None yet</p>`}</div><div class="cap" style="margin-top:10px">Add a zone (coordinates stay on your server; maps never show points inside)</div>` },
    { name: "label", label: "Label", placeholder: "Home" }, { name: "radius", label: "Radius (m)", type: "number", value: 250, min: 50, max: 5000 },
    { name: "lat", label: "Latitude", type: "number", step: "any", min: -90, max: 90 }, { name: "lon", label: "Longitude", type: "number", step: "any", min: -180, max: 180 },
  ], v => isNum(v.lat) && isNum(v.lon) ? act("privacy.zone_add", { label: v.label, lat: v.lat, lon: v.lon, radius_m: v.radius || 250 }, "Zone added")
    : save("PATCH", "profile", { privacy: { hide_start_end_m: v.hide, default_activity_private: v.private } }, "Privacy saved"),
  { intro: "Fill latitude and longitude to add a zone; otherwise this saves the trimming settings.",
    bind: sh => $$("[data-zone-rm]", sh).forEach(b => b.onclick = () => act("privacy.zone_remove", { id: b.dataset.zoneRm }, "Zone removed")) });
};

AG.sheets["edit-modules"] = () => {
  const m = P.modules || {};
  formSheet("Modules & automation", [
    { name: "nutrition", label: "Nutrition", type: "checkbox", value: m.nutrition, full: true },
    { name: "health_records", label: "Health records", type: "checkbox", value: m.health_records, full: true },
    { name: "social", label: "Social", type: "checkbox", value: m.social, full: true },
    { name: "cycle_tracking", label: "Cycle tracking", type: "checkbox", value: m.cycle_tracking, full: true },
    { name: "auto", label: "Auto-accept threshold updates", type: "checkbox", value: P.auto_accept_thresholds, full: true },
    { name: "ot", label: "Overtraining warning", type: "checkbox", value: (D.today.overtraining || {}).enabled !== false, full: true },
  ], v => save("PATCH", "profile", { modules: { nutrition: v.nutrition, health_records: v.health_records, social: v.social, cycle_tracking: v.cycle_tracking }, auto_accept_thresholds: v.auto, overtraining_warning: v.ot }, "Settings saved"));
};

AG.sheets["edit-coach"] = () => {
  const c = P.coach || {};
  formSheet("Coach settings", [
    { name: "personality", label: "Personality", type: "select", value: c.personality || "data_nerd", options: [["data_nerd", "Data Nerd"], ["guardian", "Guardian"], ["friend", "Friend"], ["commander", "Commander"]] },
    { name: "language", label: "Language", type: "select", value: c.language || "standard", options: [["simple", "Simple"], ["standard", "Standard"], ["technical", "Technical"]] },
    { name: "mode", label: "Default mode", type: "select", value: c.mode || "adaptive", options: [["fast", "Fast"], ["thinking", "Thinking"], ["adaptive", "Adaptive"]] },
    { name: "hr", label: "Let Coach read health records", type: "checkbox", value: c.include_health_records, full: true },
  ], v => save("PATCH", "profile", { coach: { personality: v.personality, language: v.language, mode: v.mode, include_health_records: v.hr } }, "Coach settings saved"), { intro: "Tone changes the wording only. The facts stay the same." });
};

AG.sheets["edit-companion"] = () => {
  const sa = P.smart_alarm || {};
  formSheet("Companion settings", [
    { name: "sa", label: "Smart alarm", type: "checkbox", value: sa.enabled, full: true },
    { name: "wake", label: "Target wake", type: "time", value: sa.target_wake }, { name: "win", label: "Window (min)", type: "number", value: sa.window_min, min: 5, max: 90 },
    { name: "beacon", label: "Beacon live sharing", type: "checkbox", value: (P.beacon || {}).enabled, full: true },
    { name: "contacts", label: "Beacon contacts (comma-separated)", full: true, hint: `${(P.beacon || {}).contacts || 0} saved · leave empty to keep them` },
  ], v => save("PATCH", "profile", Object.assign({ smart_alarm: { enabled: v.sa, target_wake: v.wake, window_min: v.win } }, { beacon: Object.assign({ enabled: v.beacon }, v.contacts ? { contacts: csv(v.contacts) } : {}) }), "Saved"),
  { intro: `${STR.companion}. These settings are stored for a future phone app; this page cannot wake you or share live location.` });
};

AG.sheets["delete-all"] = () => formSheet("Delete my entries", [
  { name: "confirm", label: "Type DELETE-MY-ENTRIES to confirm", required: true, full: true },
], v => v.confirm === "DELETE-MY-ENTRIES" ? save("POST", "delete-all", { confirm: v.confirm }, "Your entries were deleted") : (toast("Confirmation text does not match"), Promise.reject(new Error("confirm"))),
{ submit: "Delete everything I entered", intro: "Removes every user-entered record (goals, meals, journal, plans, logs, manual measurements). HealthKit imports stay. Export first if you want a copy; each deletion is in the edit history." });

/* ================= Goals ================= */
const GOAL_TYPES = [["distance", "Distance"], ["time", "Time"], ["elevation", "Elevation"], ["sessions", "Sessions"], ["load", "Training load"], ["calories", "Calories"],
  ["kilojoules", "Kilojoules"], ["record", "Record by date"], ["strength", "Strength (e1RM)"], ["body_weight", "Body weight"], ["nutrition", "Protein days"], ["streak", "Weekly streak"], ["habit", "Habit"], ["segment", "Segment"]];
const goalUnit = t => ({ distance: fmt.distUnit(), time: "hours", elevation: IMPERIAL ? "ft" : "m", body_weight: fmt.wUnit(), strength: fmt.wUnit(), record: "minutes", nutrition: "g protein", calories: "kcal", kilojoules: "kJ" })[t] || "";
const goalIn = (t, v) => !isNum(v) ? null : t === "distance" ? +(v / (IMPERIAL ? 1609.344 : 1000)).toFixed(2) : t === "time" ? +(v / 3600).toFixed(2) : t === "record" ? +(v / 60).toFixed(2) : t === "elevation" ? Math.round(IMPERIAL ? v * 3.28084 : v) : (t === "body_weight" || t === "strength") ? kgIn(v) : v;
const goalOut = (t, v) => !isNum(v) ? null : t === "distance" ? v * (IMPERIAL ? 1609.344 : 1000) : t === "time" ? v * 3600 : t === "record" ? v * 60 : t === "elevation" ? (IMPERIAL ? v / 3.28084 : v) : (t === "body_weight" || t === "strength") ? kgOut(v) : v;
function goalFields(g = {}) {
  return [
    { name: "type", label: "Type", type: "select", value: g.type || "distance", options: GOAL_TYPES },
    { name: "title", label: "Title", value: g.title, required: true },
    { name: "target", label: `Target (${goalUnit(g.type || "distance") || "count"})`, type: "number", step: "any", value: goalIn(g.type, g.target), full: true, hint: "Distance in " + fmt.distUnit() + ", time in hours, record in minutes, weight in " + fmt.wUnit() },
    { name: "period", label: "Period", type: "select", value: g.period_type || (g.end && !g.partial ? "by_date" : "week"), options: [["week", "Week"], ["month", "Month"], ["year", "Year"], ["by_date", "By date"]] },
    { name: "end", label: "End date (for by date)", type: "date", value: g.end },
    { name: "sport", label: "Sport", type: "select", value: g.sport || "", options: [["", "Any"], ["run", "Run"], ["ride", "Ride"], ["swim", "Swim"], ["walk", "Walk"], ["strength", "Strength"]] },
    { name: "distance", label: `Record distance (${fmt.distUnit()})`, type: "number", step: "any", hint: "For record goals" },
    { name: "exercise_id", label: "Exercise (strength goals)", type: "select", value: g.exercise_id || "", options: [["", "—"]].concat((D.strength.library || []).map(x => [x.id, x.name])) },
    { name: "start_value", label: "Starting value (optional)", type: "number", step: "any" },
  ];
}
function goalBody(v) {
  const b = { type: v.type, title: v.title, target: goalOut(v.type, v.target), sport: v.sport, exercise_id: v.exercise_id,
    period: { type: v.period, start: null, end: v.end }, start_value: goalOut(v.type, v.start_value) };
  if (v.type === "body_weight" && isNum(b.target) && isNum(b.start_value)) b.direction = b.target < b.start_value ? "decrease" : "increase";
  if (isNum(v.distance)) b.distance_m = v.distance * (IMPERIAL ? 1609.344 : 1000);
  Object.keys(b).forEach(k => (b[k] === null || b[k] === undefined) && delete b[k]);
  return b;
}
AG.sheets["goal-new"] = () => formSheet("New goal", goalFields(), v => save("POST", "entries/goals.goals", Object.assign(goalBody(v), { status: "active" }), "Goal added"), { intro: "Targets are never defaulted." });
AG.sheets["goal-edit"] = id => {
  const g = D.goals.find(x => x.id === id);
  if (!g) return;
  formSheet("Edit goal", goalFields(g).concat([{ name: "status", label: "Status", type: "select", value: "active", options: [["active", "Active"], ["done", "Done"], ["archived", "Archived"]] }]),
    v => save("PATCH", "entries/goals.goals/" + encodeURIComponent(id), Object.assign(goalBody(v), { status: v.status }), "Goal saved"),
    { danger: { label: "Delete", run: () => save("DELETE", "entries/goals.goals/" + encodeURIComponent(id), null, "Goal deleted") } });
};

/* ================= Activity quick edit ================= */
AG.sheets["act-edit"] = id => {
  const a = D.activities.list.find(x => x.id === id);
  if (!a) return;
  const ann = (D.activities.details[id] || {}).annotation || {};
  formSheet("Quick edit", [
    { name: "title", label: "Title", value: ann.title || a.name, full: true },
    { name: "race", label: "Race", type: "checkbox", value: a.race },
    { name: "private", label: "Private", type: "checkbox", value: a.private },
    { name: "tags", label: "Tags (comma-separated)", value: (ann.tags || []).join(", "), full: true, hint: "e.g. tempo, intervals, threshold. Used for pace calibration" },
  ], v => save("POST", "entries/load.annotations", { workout_id: id, title: v.title === a.name && !ann.title ? null : v.title, race: v.race, private: v.private, tags: csv(v.tags) }, "Activity updated"),
  { intro: "An overlay on the HealthKit workout. The imported record itself never changes." });
};

/* ================= Nutrition ================= */
const allMeals = () => [].concat(...D.nutrition.days.map(d => d.per_meal.map(m => Object.assign({ day: d.date }, m))));
AG.sheets["water-add"] = () => formSheet("Log water", [
  { name: "ml", label: "Amount (ml)", type: "number", value: 250, min: 10, max: 3000, required: true }, { name: "t", label: "Time", type: "datetime-local", value: nowInput(), required: true },
], v => save("POST", "entries/nutrition.water", { t: inputToIso(v.t), ml: v.ml }, "Water logged"));
AG.sheets["caffeine-add"] = () => formSheet("Log caffeine", [
  { name: "mg", label: "Amount (mg)", type: "number", value: 95, min: 1, max: 1000, required: true, hint: "Coffee ≈ 95 mg, espresso ≈ 65 mg (your own estimate)" }, { name: "t", label: "Time", type: "datetime-local", value: nowInput(), required: true },
], v => save("POST", "entries/nutrition.caffeine", { t: inputToIso(v.t), mg: v.mg }, "Caffeine logged"));
AG.sheets["meal-edit"] = id => {
  const m = allMeals().find(x => x.id === id);
  if (!m) return;
  const single = m.items.length <= 1;
  formSheet("Meal", [
    { name: "name", label: "Name", value: m.name, full: true },
    { name: "meal", label: "Meal", type: "select", value: m.meal || "snack", options: ["breakfast", "lunch", "dinner", "snack", "pre_workout", "post_workout"].map(x => [x, fmt.sport(x)]) },
    { name: "t", label: "Time", type: "datetime-local", value: isoToInput(m.t), required: true },
    ...(single ? [{ name: "kcal", label: "kcal", type: "number", value: m.kcal }, { name: "protein_g", label: "Protein g", type: "number", value: m.protein_g },
      { name: "carbs_g", label: "Carbs g", type: "number", value: m.carbs_g }, { name: "fat_g", label: "Fat g", type: "number", value: m.fat_g }]
      : [{ name: "items", type: "html", full: true, html: `<p class="small muted">${m.items.length} items: ${esc(m.items.join(", "))}</p>` }]),
    { name: "copy_to", label: "Copy to date", type: "date", value: todayISO() },
  ], v => save("PATCH", "entries/nutrition.meals/" + encodeURIComponent(id), Object.assign({ name: v.name, meal: v.meal, t: inputToIso(v.t) },
    single ? { items: [{ name: v.name || m.items[0] || "Meal", qty: 1, unit: "serving", kcal: v.kcal, protein_g: v.protein_g, carbs_g: v.carbs_g, fat_g: v.fat_g }] } : {}), "Meal saved"),
  { danger: { label: "Delete", run: () => save("DELETE", "entries/nutrition.meals/" + encodeURIComponent(id), null, "Meal deleted") },
    extra: [{ label: "Copy", run: v => act("meal.copy", { meal_id: id, date: v.copy_to }, "Meal copied") }, { label: "Save as recipe", run: v => act("recipe.from_meals", { meal_ids: [id], name: v.name || "Recipe" }, "Recipe saved") }] });
};
AG.sheets["day-copy"] = date => formSheet(`Copy ${fmt.date(date)}`, [{ name: "to", label: "Copy every meal to", type: "date", value: todayISO(), required: true }],
  v => act("day.copy", { from: date, to: v.to }, "Day copied"), { submit: "Copy day" });
AG.sheets["recipe-from-selected"] = () => {
  const ids = $$("[data-meal-pick]:checked").map(x => x.value);
  if (!ids.length) { toast("Select meals first"); return; }
  formSheet("New recipe", [{ name: "name", label: "Recipe name", required: true, full: true }, { name: "favorite", label: "Favorite", type: "checkbox" }],
    v => act("recipe.from_meals", { meal_ids: ids, name: v.name, favorite: v.favorite }, "Recipe saved"), { intro: `${ids.length} meal(s) selected.` });
};
AG.sheets["recipe"] = id => {
  const r = D.nutrition.recipes.find(x => x.id === id);
  if (!r) return;
  formSheet(r.name, [
    { name: "t", label: "Log at", type: "datetime-local", value: nowInput() }, { name: "meal", label: "Meal", type: "select", value: "lunch", options: ["breakfast", "lunch", "dinner", "snack"].map(x => [x, fmt.sport(x)]) },
    { name: "plan_date", label: "Or plan for", type: "date", value: addDays(todayISO(), 1) },
    { name: "favorite", label: "Favorite", type: "checkbox", value: r.favorite },
  ], v => act("recipe.log", { recipe_id: id, t: inputToIso(v.t), meal: v.meal }, "Meal logged"),
  { submit: "Log now", extra: [{ label: "Plan it", run: v => act("recipe.plan", { recipe_id: id, date: v.plan_date, meal: v.meal }, "Meal planned") },
    { label: "Save favorite", run: v => save("PATCH", "entries/nutrition.recipes/" + encodeURIComponent(id), { favorite: v.favorite }, "Recipe saved") }],
  danger: { label: "Delete", run: () => save("DELETE", "entries/nutrition.recipes/" + encodeURIComponent(id), null, "Recipe deleted") },
  intro: esc(r.items.map(i => i.name).join(", ")) });
};
AG.sheets["planned-meal"] = id => confirmSheet("Planned meal", "Remove this planned meal?", "Remove", () => save("DELETE", "entries/nutrition.planned_meals/" + encodeURIComponent(id), null, "Removed"));

/* ================= Quick log (Today header) ================= */
AG.sheets["quick-log"] = () => {
  const items = [["meal-add", "nutrition", "Meal"], ["water-add", "droplet", "Water"], ["caffeine-add", "coffee", "Caffeine"], ["measure-add", "scale", "Weight"], ["mood-add", "mood", "Mood"], ["note-add", "note", "Note"]];
  const recipes = (D.nutrition.recipes || []).filter(r => r.favorite);
  const q = D.nutrition.quick || { recent: [], frequent: [] };
  const again = (title, rows) => rows.length ? sectionTitle(title) + `<div class="list">${rows.map(m => `<button type="button" class="li" data-relog="${esc(m.meal_id)}"><div class="grow"><div class="t">${esc(m.name)}</div><div class="s">${[isNum(m.kcal) ? fmt.n(m.kcal) + " kcal" : "", isNum(m.protein_g) ? fmt.n(m.protein_g) + " g protein" : "", m.count > 1 ? m.count + "× in 60 days" : ""].filter(Boolean).join(" · ")}</div></div><span class="go" aria-hidden="true">${icon("plus")}</span></button>`).join("")}</div>` : "";
  openSheet("Log", `<div class="more-grid">${items.map(([id, ic, label]) => `<button type="button" data-open="${id}">${icon(ic)}<span>${label}</span></button>`).join("")}</div>
    ${again("Recent", q.recent)}${again("Often", q.frequent)}
    ${recipes.length ? sectionTitle("Favorite meals") + `<div class="list">${recipes.map(r => `<button type="button" class="li" data-open="recipe" data-arg="${esc(r.id)}"><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${r.items.map(i => esc(i.name)).join(", ")}</div></div><span class="go" aria-hidden="true">${icon("arrow")}</span></button>`).join("")}</div>` : ""}`);
};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-relog]");
  if (b) act("meal.copy", { meal_id: b.dataset.relog, date: nowInput().slice(0, 10), t: new Date().toISOString() }, "Meal logged").catch(() => {});
});
AG.sheets["meal-add"] = () => openSheet("Add meal", mealForm(), { after: bindMealForm });
AG.sheets["mood-add"] = () => {
  const labels = ["Awful", "Low", "Okay", "Good", "Great"];
  openSheet("Mood", `<div class="mood-row" role="group" aria-label="Mood">${labels.map((l, i) => `<button type="button" data-mood="${i + 1}" aria-label="${l}">${icon("mood-" + (i + 1))}<span>${l}</span></button>`).join("")}</div>`);
};
document.addEventListener("click", e => {
  const m = e.target.closest("[data-mood]");
  if (m) save("POST", "entries/journal.entries", { date: nowInput().slice(0, 10), type: "mood", value: +m.dataset.mood, habit_id: null, text: null }, "Mood logged").catch(() => {});
});
AG.sheets["note-add"] = () => formSheet("Note", [{ name: "text", label: "Note", required: true, full: true }],
  v => save("POST", "entries/journal.entries", { date: nowInput().slice(0, 10), type: "note", value: null, habit_id: null, text: v.text }, "Note saved"));

/* ================= Apple Health export (one-time backfill) ================= */
AG.sheets["health-export"] = () => openSheet("Import Apple Health export", `<form class="form" id="hx-form"><label>export.zip <input type="file" id="hx-file" accept=".zip,application/zip" required></label>
  <div class="actions" style="margin-top:0"><button class="btn" type="submit">Upload</button></div><p class="small muted" id="hx-status" role="status"></p></form>`, { after: sh => {
  const f = $("#hx-form", sh), out = $("#hx-status", sh);
  f.onsubmit = async e => {
    e.preventDefault();
    const file = $("#hx-file", sh).files[0];
    if (!file) return;
    f.querySelector("button").disabled = true;
    out.textContent = "Uploading…";
    try {
      const r = await fetch("api/import/apple-health-export", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/zip" }, body: file });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || "HTTP " + r.status);
      const poll = async () => {
        const s2 = await fetch("api/agent/job?id=" + encodeURIComponent(j.job), { credentials: "same-origin" }).then(x => x.json());
        if (s2.status === "running") { out.textContent = s2.step || "Importing…"; setTimeout(poll, 3000); return; }
        if (s2.status === "done") { toast("Apple Health history imported"); setTimeout(() => location.reload(), 700); return; }
        out.textContent = s2.error || "Import failed";
        f.querySelector("button").disabled = false;
      };
      poll();
    } catch (err) { out.textContent = err.message; f.querySelector("button").disabled = false; }
  };
} });

/* ================= Body ================= */
AG.sheets["measure-add"] = () => formSheet("Add measurement", [
  { name: "type", label: "Type", type: "select", value: "weight_kg", options: [["weight_kg", `Weight (${fmt.wUnit()})`], ["body_fat_pct", "Body fat (%)"], ["lean_mass_kg", `Lean mass (${fmt.wUnit()})`], ["waist_cm", "Waist (cm)"], ["bp", "Blood pressure (mmHg)"]] },
  { name: "t", label: "Time", type: "datetime-local", value: nowInput(), required: true },
  { name: "v", label: "Value (systolic for BP)", type: "number", step: "any", required: true }, { name: "v2", label: "Diastolic (BP only)", type: "number", step: "any" },
], async v => {
  const t = inputToIso(v.t);
  if (v.type === "bp") {
    if (!isNum(v.v2)) { toast("Enter both systolic and diastolic"); throw new Error("bp"); }
    await api("POST", "entries/body.measurements", { t, type: "bp_systolic_mmhg", v: v.v });
    return save("POST", "entries/body.measurements", { t, type: "bp_diastolic_mmhg", v: v.v2 }, "Blood pressure saved");
  }
  const val = v.type === "weight_kg" || v.type === "lean_mass_kg" ? kgOut(v.v) : v.v;
  return save("POST", "entries/body.measurements", { t, type: v.type, v: val }, "Measurement saved");
}, { intro: "Saved as your own entry next to HealthKit data. Readings only, with no categories or diagnosis." });

/* ================= Health records ================= */
AG.sheets["record-add"] = () => formSheet("Add health record", [
  { name: "title", label: "Title", required: true, full: true }, { name: "date", label: "Date", type: "date", value: todayISO(), required: true },
  { name: "type", label: "Type", type: "select", value: "lab", options: [["lab", "Lab results"], ["note", "Note"], ["document", "Document"], ["imaging", "Imaging"], ["vaccination", "Vaccination"]] },
  { name: "provider", label: "Provider", full: true },
  { name: "markers", label: "Biomarkers, one per line: name, value, unit, low-high", type: "textarea", full: true, placeholder: "Albumin, 45, g/L, 35-50\nCRP, 0.8, mg/L, 0-5" },
  { name: "text", label: "Notes", type: "textarea", full: true, rows: 2 },
  { name: "file", type: "html", full: true, html: `<label>Attach a file (PDF or image, 15 MB max)<input type="file" id="rec-file" accept=".pdf,.png,.jpg,.jpeg,.txt"></label>` },
], async v => {
  const markers = (v.markers || "").split("\n").map(l => l.trim()).filter(Boolean).map(l => {
    const [name, value, unit, range] = l.split(",").map(x => (x || "").trim());
    if (!name || !isFinite(+value) || !unit) throw new Error(`Biomarker line needs name, value, unit: "${l}"`);
    const [lo, hi] = (range || "").split("-").map(x => x.trim() === "" ? null : +x);
    const code = name.toLowerCase().replace(/[^a-z]/g, "");
    const known = { albumin: "albumin", creatinine: "creatinine", glucose: "glucose", crp: "crp", hscrp: "crp", lymphocytes: "lymphocyte_pct", lymphocyte: "lymphocyte_pct", mcv: "mcv", rdw: "rdw", alp: "alp", alkalinephosphatase: "alp", wbc: "wbc", whitebloodcells: "wbc" };
    return { name, code: known[code] || null, value: +value, unit, ref_low: isNum(lo) ? lo : null, ref_high: isNum(hi) ? hi : null, ref_text: null };
  });
  const body = { title: v.title, date: v.date, type: v.type, provider: v.provider, text: v.text, biomarkers: markers };
  const f = $("#rec-file") && $("#rec-file").files[0];
  if (f) {
    if (f.size > 15 * 1024 * 1024) { toast("File too large (15 MB max)"); throw new Error("size"); }
    const b64 = await new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(String(r.result).split(",")[1]); r.onerror = rej; r.readAsDataURL(f); });
    return act("record.upload", Object.assign(body, { filename: f.name, content_b64: b64 }), "Record saved");
  }
  return save("POST", "entries/health_records.records", body, "Record saved");
}, { intro: "Kept in your private data folder behind sign-in. Excluded from Coach unless you allow it, and never cached offline or shown in widgets." });
AG.sheets["record-del"] = id => confirmSheet("Delete record", "Delete this health record? (Undo is available.)", "Delete", () => save("DELETE", "entries/health_records.records/" + encodeURIComponent(id), null, "Record deleted"));

/* ================= Journal & status ================= */
AG.sheets["status-set"] = () => formSheet("Activity status", [
  { name: "status", label: "Status", type: "select", value: "sick", options: [["sick", "Sick"], ["traveling", "Traveling"], ["injured", "Injured"], ["recovering", "Recovering"], ["normal", "Normal"]] },
  { name: "start", label: "From", type: "date", value: todayISO(), required: true }, { name: "end", label: "Until (optional)", type: "date" },
  { name: "note", label: "Note", full: true },
], v => save("POST", "entries/journal.activity_status", { status: v.status, start: v.start, end: v.end, note: v.note, source: "you" }, "Status set"),
{ intro: "Plans adapt (\"Not feeling 100%\") while a non-normal status is active." });
AG.sheets["status-end"] = id => save("PATCH", "entries/journal.activity_status/" + encodeURIComponent(id), { end: todayISO() }, "Status ended");
AG.sheets["habit-add"] = () => formSheet("New habit", [{ name: "name", label: "Habit", required: true, full: true, placeholder: "e.g. Creatine 5 g" },
  { name: "unit", label: "Unit (optional)" }, { name: "boolean", label: "Yes/no habit", type: "checkbox", value: true }],
v => save("POST", "entries/journal.habits", { name: v.name, unit: v.unit, boolean: v.boolean }, "Habit added"));
AG.sheets["journal-del"] = id => confirmSheet("Delete entry", "Delete this journal entry?", "Delete", () => save("DELETE", "entries/journal.entries/" + encodeURIComponent(id), null, "Entry deleted"));

/* ================= Coach ================= */
AG.sheets["memory-edit"] = id => {
  const m = id ? D.coach.memory.find(x => x.id === id) : null;
  formSheet(m ? "Edit memory" : "Remember something", [
    { name: "type", label: "Type", type: "select", value: m ? m.type : "preference", options: [["preference", "Preference"], ["goal", "Goal"], ["correction", "Correction"], ["fact", "Fact"]] },
    { name: "text", label: "Text", type: "textarea", value: m ? m.text : "", required: true, full: true },
  ], v => m ? save("PATCH", "entries/coach.memory/" + encodeURIComponent(id), v, "Memory saved") : save("POST", "entries/coach.memory", v, "Remembered"),
  m ? { danger: { label: "Forget", run: () => save("DELETE", "entries/coach.memory/" + encodeURIComponent(id), null, "Forgotten") } } : {});
};
AG.sheets["checkin-edit"] = id => {
  const c = id ? D.coach.checkins.find(x => x.id === id) : null;
  const days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  formSheet(c ? "Edit check-in" : "New check-in", [
    { name: "type", label: "Type", type: "select", value: c ? c.type : "reminder", options: [["morning_report", "Morning report"], ["reminder", "Reminder"], ["goal_progress", "Goal progress"], ["weekly_summary", "Weekly summary"], ["monthly_summary", "Monthly summary"], ["nudge", "Nudge"]] },
    { name: "time", label: "Time", type: "time", value: c ? c.time : "07:00", required: true },
    { name: "text", label: "Message", value: c ? c.text : "", full: true, placeholder: "e.g. Creatine" },
    ...days.map(d => ({ name: "d_" + d, label: fmt.sport(d), type: "checkbox", value: c ? (c.days || []).includes(d) : true })),
    { name: "enabled", label: "Enabled", type: "checkbox", value: c ? c.enabled : true, full: true },
  ], v => { const body = { type: v.type, time: v.time, text: v.text, enabled: v.enabled, days: days.filter(d => v["d_" + d]) };
    return c ? save("PATCH", "entries/coach.checkins/" + encodeURIComponent(id), body, "Check-in saved") : save("POST", "entries/coach.checkins", body, "Check-in added"); },
  Object.assign({ intro: `${AGENT} delivers check-ins on this schedule.` }, c ? { danger: { label: "Delete", run: () => save("DELETE", "entries/coach.checkins/" + encodeURIComponent(id), null, "Check-in deleted") } } : {}));
};

/* ================= Plans ================= */
AG.sheets["session-new"] = date => formSheet("Add session", [
  { name: "date", label: "Date", type: "date", value: date || todayISO(), required: true },
  { name: "from", label: "From template", type: "select", value: "", options: [["", "Custom"]].concat((D.plans.templates || []).map(t => [t.id, t.name])) },
  { name: "type", label: "Type", type: "select", value: "AER", options: typeOptions() }, { name: "title", label: "Title" },
  { name: "min", label: "Duration (min)", type: "number", min: 0, max: 600 }, { name: "priority", label: "Priority", type: "select", value: "normal", options: [["normal", "Normal"], ["key", "Key"], ["optional", "Optional"]] },
  { name: "sport", label: "Sport", type: "select", value: "run", options: [["run", "Run"], ["ride", "Ride"], ["swim", "Swim"], ["strength", "Strength"], ["walk", "Walk"], ["", "Other"]] },
  { name: "objective", label: "Objective", full: true },
], v => act("plan.schedule", v.from ? { date: v.date, template_id: v.from, priority: v.priority } : { date: v.date, type: v.type, title: v.title, duration_s: isNum(v.min) ? v.min * 60 : null, priority: v.priority, sport: v.sport || null, objective: v.objective }, "Session added"));
AG.sheets["session-edit"] = id => {
  const s = [].concat(D.plans.upcoming, D.plans.this_week.sessions, D.plans.next_week.sessions).find(x => x.id === id);
  if (!s) return;
  formSheet("Edit session", [
    { name: "date", label: "Date", type: "date", value: s.date, required: true }, { name: "type", label: "Type", type: "select", value: s.type, options: typeOptions() },
    { name: "title", label: "Title", value: s.title }, { name: "min", label: "Duration (min)", type: "number", value: isNum(s.duration_s) ? s.duration_s / 60 : null },
    { name: "priority", label: "Priority", type: "select", value: s.priority || "normal", options: [["normal", "Normal"], ["key", "Key"], ["optional", "Optional"]] },
    { name: "objective", label: "Objective", value: s.objective, full: true },
  ], v => save("PATCH", "entries/plans.sessions/" + encodeURIComponent(id), { date: v.date, type: v.type, title: v.title, duration_s: isNum(v.min) ? v.min * 60 : null, priority: v.priority, objective: v.objective }, "Session saved"),
  { danger: { label: "Delete", run: () => save("DELETE", "entries/plans.sessions/" + encodeURIComponent(id), null, "Session deleted") } });
};
AG.sheets["session-move"] = id => {
  const session = [].concat(D.plans.today, D.plans.upcoming, D.plans.this_week.sessions, D.plans.next_week.sessions).find(x => x.id === id);
  const options = nextDays(21).filter(([date]) => date !== (session || {}).date);
  const tomorrow = addDays(todayISO(), 1);
  const value = options.some(([date]) => date === tomorrow) ? tomorrow : options[0][0];
  formSheet("Move session", [{ name: "date", label: "Move to", type: "select", value, options }],
    v => act("plan.move", { session_id: id, date: v.date }, "Session moved"), { submit: "Move" });
};
AG.sheets["session-template"] = id => formSheet("Save as template", [{ name: "name", label: "Template name", required: true, full: true }],
  v => act("plan.save_template", { session_id: id, name: v.name }, "Template saved"));
AG.sheets["template-edit"] = id => {
  const t = (D.plans.templates || []).find(x => x.id === id);
  if (!t) return;
  formSheet("Template", [{ name: "name", label: "Name", value: t.name, required: true }, { name: "type", label: "Type", type: "select", value: t.type, options: typeOptions() },
    { name: "min", label: "Duration (min)", type: "number", value: isNum(t.duration_s) ? t.duration_s / 60 : null },
    { name: "future", label: "Also update future sessions built from it", type: "checkbox", value: true, full: true },
    { name: "date", label: "Schedule on", type: "date", value: addDays(todayISO(), 1) }],
  v => act("plan.update_template", { template_id: id, fields: { name: v.name, type: v.type, duration_s: isNum(v.min) ? v.min * 60 : null }, apply_future: v.future }, "Template saved"),
  { extra: [{ label: "Schedule", run: v => act("plan.schedule", { date: v.date, template_id: id }, "Session added") }],
    danger: { label: "Delete", run: () => save("DELETE", "entries/plans.templates/" + encodeURIComponent(id), null, "Template deleted") } });
};
AG.sheets["instant-schedule"] = i => formSheet("Schedule workout", [{ name: "date", label: "Date", type: "select", value: todayISO(), options: nextDays(14) }],
  v => act("plan.schedule", { date: v.date, instant: +i }, "Workout scheduled"), { intro: esc((D.plans.instant.options[+i] || {}).why || "") });
AG.sheets["race-edit"] = id => {
  const r = id ? D.plans.races.races.find(x => x.id === id) : null;
  formSheet(r ? "Edit race" : "Add race", [
    { name: "name", label: "Name", value: r ? r.name : "", required: true, full: true }, { name: "date", label: "Date", type: "date", value: r ? r.date : addDays(todayISO(), 60), required: true },
    { name: "priority", label: "Priority", type: "select", value: r ? r.priority : "B", options: [["A", "A: goal race, with taper"], ["B", "B"], ["C", "C: training race"]] },
    { name: "dist", label: `Distance (${fmt.distUnit()})`, type: "number", step: "any", value: r && r.distance_m ? +(r.distance_m / (IMPERIAL ? 1609.344 : 1000)).toFixed(2) : null },
    { name: "goal", label: "Goal time (h:mm:ss)", value: r && r.goal_time_s ? fmt.dur(r.goal_time_s) : "" }, { name: "location", label: "Location", value: r ? r.location : "" },
  ], v => {
    let goal = null;
    if (v.goal) { const p = v.goal.split(":").map(Number); if (p.some(x => !isFinite(x))) { toast("Goal time like 1:45:00"); return Promise.reject(new Error("goal")); } goal = p.reduce((a, x) => a * 60 + x, 0); }
    const body = { name: v.name, date: v.date, priority: v.priority, distance_m: isNum(v.dist) ? v.dist * (IMPERIAL ? 1609.344 : 1000) : null, goal_time_s: goal, location: v.location };
    return r ? save("PATCH", "entries/plans.races/" + encodeURIComponent(id), body, "Race saved") : save("POST", "entries/plans.races", body, "Race added");
  }, r ? { danger: { label: "Delete", run: () => save("DELETE", "entries/plans.races/" + encodeURIComponent(id), null, "Race deleted") } } : {});
};
AG.sheets["event-add"] = () => formSheet("Calendar event", [
  { name: "title", label: "Title", required: true, full: true }, { name: "start", label: "Start", type: "datetime-local", value: nowInput(), required: true },
  { name: "end", label: "End", type: "datetime-local", required: true }, { name: "busy", label: "Busy (blocks training)", type: "checkbox", value: true, full: true },
], v => save("POST", "entries/plans.calendar", { title: v.title, start: inputToIso(v.start), end: inputToIso(v.end), busy: v.busy, source: "manual" }, "Event added"),
{ intro: "Manual events until a calendar source is connected. Conflicts with planned sessions show on Today and in Plan." });
AG.sheets["plan-new"] = () => formSheet("New training plan", [
  { name: "name", label: "Name", required: true, full: true, placeholder: "e.g. Autumn 10K" }, { name: "goal", label: "Goal", full: true },
  { name: "mode", label: "Mode", type: "select", value: "race", options: [["race", "Race"], ["build", "Build"], ["maintain", "Maintain"]] },
  { name: "race_id", label: "Target race", type: "select", value: "", options: [["", "None"]].concat(D.plans.races.races.map(r => [r.id, r.name])) },
  { name: "start", label: "Start", type: "date", value: todayISO() }, { name: "end", label: "End", type: "date" },
  { name: "phases", label: "Phases, one per line: name, start, end, focus", type: "textarea", full: true, placeholder: "Base, YYYY-MM-DD, YYYY-MM-DD, aerobic volume\nBuild, YYYY-MM-DD, YYYY-MM-DD, threshold" },
], v => {
  let phases;
  try { phases = (v.phases || "").split("\n").map(l => l.trim()).filter(Boolean).map(l => { const [name, start, end, focus] = l.split(",").map(x => x.trim()); if (!/^\d{4}-\d\d-\d\d$/.test(start || "") || !/^\d{4}-\d\d-\d\d$/.test(end || "")) throw new Error(`Phase dates must be YYYY-MM-DD: "${l}"`); return { name, start, end, focus: focus || null }; }); }
  catch (e) { toast(e.message); return Promise.reject(e); }
  return save("POST", "entries/plans.plans", { name: v.name, goal: v.goal, mode: v.mode, race_id: v.race_id, start: v.start, end: v.end, phases, created_by: "owner" }, "Plan saved");
}, { intro: "A plan is a goal plus phases. Add sessions to it from the week view or the session form." });

/* Routine builder: warm-up / work / recovery / repeat / cool-down with targets */
AG.sheets["routine-new"] = () => {
  const row = (kind = "work") => `<div class="step-row" data-step><select aria-label="Step" data-k>${["warmup", "work", "recovery", "cooldown"].map(k => `<option ${k === kind ? "selected" : ""} value="${k}">${fmt.sport(k)}</option>`).join("")}</select>
    <input aria-label="Minutes" placeholder="min" inputmode="decimal" data-min><select aria-label="Target" data-t><option value="open">Open</option><option value="zone">HR zone</option><option value="hr">HR range</option><option value="pace">Pace range</option><option value="power">Power</option></select>
    <button type="button" class="icon-btn" data-rm aria-label="Remove step">${icon("x")}</button><input aria-label="Target low / zone" placeholder="low or zone" data-lo style="grid-column:2"><input aria-label="Target high" placeholder="high" data-hi></div>`;
  formSheet("New routine", [
    { name: "name", label: "Name", required: true, full: true }, { name: "sport", label: "Sport", type: "select", value: "run", options: [["run", "Run"], ["ride", "Ride"], ["swim", "Swim"], ["row", "Row"], ["strength", "Strength"]] },
    { name: "guiding", label: "Guide by", type: "select", value: "hr", options: [["hr", "Heart rate"], ["pace", "Pace"], ["power", "Power"], ["rpe", "RPE"]] },
    { name: "repeat", label: "Repeat the work + recovery steps ×", type: "number", value: 1, min: 1, max: 30 },
    { name: "steps", type: "html", full: true, html: `<div class="cap">Steps (pace as m:ss${fmt.paceUnit()})</div><div id="rt-steps">${row("warmup")}${row("work")}${row("recovery")}${row("cooldown")}</div><button type="button" class="btn sm secondary" id="rt-add" style="margin-top:8px">Add step</button>` },
    { name: "notes", label: "Notes", full: true },
  ], v => {
    let steps;
    try {
      steps = $$("[data-step]").map(r => {
        const kind = $("[data-k]", r).value, min = +$("[data-min]", r).value || null, t = $("[data-t]", r).value, lo = $("[data-lo]", r).value, hi = $("[data-hi]", r).value;
        const target = t === "open" ? { metric: "open" } : t === "zone" ? { metric: "zone", zone: +lo || 2 } : t === "pace" ? { metric: "pace", low: paceOut(lo), high: paceOut(hi) } : { metric: t, low: +lo || null, high: +hi || null };
        return { kind, duration_s: min ? min * 60 : null, target, label: null };
      });
    } catch (e) { toast(e.message); return Promise.reject(e); }
    const n = v.repeat || 1;
    const work = steps.filter(s => s.kind === "work" || s.kind === "recovery");
    const out = n > 1 && work.length ? [].concat(steps.filter(s => s.kind === "warmup"), [{ kind: "repeat", repeat: n, steps: work }], steps.filter(s => s.kind === "cooldown")) : steps;
    return save("POST", "entries/plans.routines", { name: v.name, sport: v.sport, guiding_metric: v.guiding, steps: out, notes: v.notes }, "Routine saved");
  }, { bind: sh => {
    $("#rt-add", sh).onclick = () => $("#rt-steps", sh).insertAdjacentHTML("beforeend", row());
    $("#rt-steps", sh).addEventListener("click", e => { const b = e.target.closest("[data-rm]"); if (b) b.closest("[data-step]").remove(); });
  } });
};
AG.sheets["routine-schedule"] = id => formSheet("Schedule routine", [{ name: "date", label: "Date", type: "select", value: addDays(todayISO(), 1), options: nextDays(21) },
  { name: "type", label: "Session type", type: "select", value: "INT", options: typeOptions() }],
v => act("plan.schedule", { date: v.date, routine_id: id, type: v.type }, "Routine scheduled"),
{ danger: { label: "Delete routine", run: () => save("DELETE", "entries/plans.routines/" + encodeURIComponent(id), null, "Routine deleted") } });

/* ================= Prehab ================= */
AG.sheets["prehab-new"] = () => formSheet("New prehab routine", [
  { name: "name", label: "Name", required: true, full: true }, { name: "focus", label: "Focus", placeholder: "Hips, calves" },
  { name: "min", label: "Minutes", type: "number", min: 1, max: 120 }, { name: "ex", label: "Exercises (comma-separated)", full: true },
], v => save("POST", "entries/plans.prehab", { name: v.name, focus: v.focus, duration_min: v.min, exercises: csv(v.ex) }, "Routine added"),
{ intro: "Routines and completion history only. No medical claims." });

/* ================= Strength ================= */
AG.sheets["exercise-new"] = () => formSheet("New exercise", [
  { name: "name", label: "Name", required: true, full: true }, { name: "equipment", label: "Equipment" }, { name: "pattern", label: "Pattern", placeholder: "squat, hinge, push…" },
  { name: "primary", type: "html", full: true, html: `<div class="cap">Primary muscles</div><div class="chips">${(D.meta.muscle_groups || []).map(m => `<label class="chip"><input type="checkbox" value="${m}" data-mprim style="width:auto"> ${esc(fmt.sport(m))}</label>`).join("")}</div>` },
  { name: "secondary", type: "html", full: true, html: `<div class="cap">Secondary muscles</div><div class="chips">${(D.meta.muscle_groups || []).map(m => `<label class="chip"><input type="checkbox" value="${m}" data-msec style="width:auto"> ${esc(fmt.sport(m))}</label>`).join("")}</div>` },
  { name: "cue", label: "Form cue", full: true },
], v => {
  const primary = $$("[data-mprim]:checked").map(x => x.value), secondary = $$("[data-msec]:checked").map(x => x.value);
  if (!primary.length) { toast("Pick at least one primary muscle"); return Promise.reject(new Error("muscles")); }
  return save("POST", "entries/strength.exercises", { name: v.name, equipment: v.equipment, pattern: v.pattern, primary, secondary, cue: v.cue }, "Exercise added");
});
AG.sheets["str-routine-save"] = () => {
  const exs = $$("#str-ex-list [data-ex]").map(div => { const rows = $$("[data-sets] .row", div); const r0 = rows[0]; return { exercise_id: div.dataset.ex, sets: rows.length, reps: r0 ? $("[data-r]", r0).value || null : null, rpe: r0 && $("[data-rpe]", r0).value ? +$("[data-rpe]", r0).value : null }; });
  if (!exs.length) { toast("Add exercises in the builder first"); return; }
  formSheet("Save as routine", [{ name: "name", label: "Routine name", required: true, full: true, value: ($("#str-log") || {}).name ? $("#str-log").name.value : "" }],
    v => save("POST", "entries/strength.routines", { name: v.name, exercises: exs }, "Routine saved"), { intro: `${exs.length} exercise(s), set counts and first-set reps/RPE as targets.` });
};
AG.sheets["str-del"] = id => confirmSheet("Delete log", "Delete this strength log? The HealthKit workout (if any) stays.", "Delete", () => save("DELETE", "entries/strength.sessions/" + encodeURIComponent(id), null, "Log deleted"));

/* ================= Routes ================= */
function bindRouteImport() {
  const inp = $("#route-file");
  if (!inp) return;
  inp.onchange = () => {
    const f = inp.files[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { toast("Route file too large (5 MB max)"); return; }
    const r = new FileReader();
    r.onload = () => act("route.import", { filename: f.name, text: String(r.result), name: ($("#route-name") || {}).value || null }, "Route imported").catch(() => {});
    r.readAsText(f);
  };
}
AG.sheets["route-del"] = id => confirmSheet("Delete route", "Delete this imported route?", "Delete", () => save("DELETE", "entries/routes.features/" + encodeURIComponent(id), null, "Route deleted"));

/* ================= Dev gallery (#/dev/gallery) =================
   Every component in ok / partial / stale / missing / estimate. Uses this snapshot's own values; the
   other states are the same value object with only its status changed, so no number is invented. */
AG.screens.dev = {
  title: "Component gallery", parent: "#/profile", nav: "profile",
  render() {
    const base = D.today.rings.recovery && isNum(D.today.rings.recovery.v) ? D.today.rings.recovery : D.today.rings.sleep;
    const states = ["ok", "partial", "stale", "calibrating", "missing"].map(st => Object.assign({}, base, { status: st, note: st === "partial" ? "Partial data" : base.note, v: st === "missing" ? null : base.v }));
    const est = Object.assign({}, base, { kind: "estimated" });
    const f = (D.today.recommendation.factors || [])[0];
    const g = (D.goals || [])[0];
    const lib = (D.routes.library || [])[0];
    const pmc = (D.training.pmc.series || []).slice(-30);
    const sec = (t, body) => `<div class="card"><h3>${esc(t)}</h3>${body}</div>`;
    return `<p class="cap">Developer view. Values come from this snapshot; each state differs only in its status field.</p><div class="cols"><div class="stack">
      ${sec("ScoreRing", `<div class="row wrap">${states.map(v => `<div style="text-align:center">${ring("recovery", v, { label: v.status, sub: v.status })}<div class="cap">${v.status}</div></div>`).join("")}</div>`)}
      ${sec("StatTile + status line", states.map(v => `<div style="margin-bottom:8px">${stat(v.status, val(v, 0, "%"), "", { d: prov(v, v.status) })}${stLine(v)}</div>`).join("") + `<div>${stat("estimate", val(est, 0, "%"))} ${estBadge(est)}</div>`)}
      ${sec("Badges & chips", `<div class="row wrap">${["ok", "warn", "bad", "info", "accent", "est", ""].map(c => badge(c || "neutral", c)).join("")}</div><div style="margin-top:8px">${chips("gal-chip", [["a", "Chip A"], ["b", "Chip B"]], chipVal("gal-chip", "a"))}</div><div style="margin-top:8px">${seg("gal-seg", [["x", "One"], ["y", "Two"]], chipVal("gal-seg", "x"))}</div>`)}
      ${sec("FactorRow / InsightCard", `${f ? factorRow(f) : empty(STR.noData)}${insightCard(D.today.action ? D.today.action.text : STR.noData, D.today.action ? D.today.action.detail : null, "action")}${insightCard("Plain insight", "Second line")}`)}
      ${sec("EmptyState strings", Object.values(STR).slice(0, 8).map(t => empty(t)).join(""))}
      ${sec("GoalRow", g ? goalRow(g) : empty(STR.noGoals))}
    </div><div class="stack">
      ${sec("Line chart", pmc.length ? chart({ id: "gal-line", label: "Fitness", x: pmc.map(r => r.date), series: [{ name: "Fitness", color: "var(--info)", values: pmc.map(r => r.ctl) }], fmtX: d => fmt.date(d), h: 120 }) : empty(STR.noData))}
      ${sec("Bar chart", pmc.length ? chart({ id: "gal-bar", type: "bar", label: "Daily load", x: pmc.map(r => r.date), series: [{ name: "Load", color: "var(--accent)", values: pmc.map(r => r.known ? r.load : null) }], fmtX: d => fmt.date(d), h: 110 }) : empty(STR.noData))}
      ${sec("Calendar heat grid", heatGrid(pmc.map(r => ({ date: r.date, v: r.known ? r.load : null })), { label: "Daily load" }))}
      ${sec("Sparkline / bar / energy", `${sparkline(pmc.map(r => r.ctl), "var(--accent)")}${bar(base && isNum(base.v) ? base.v : 0, "var(--recovery)", 50)}<div class="energy" style="margin-top:8px"><i style="width:${base && isNum(base.v) ? base.v : 0}%"></i></div>`)}
      ${sec("Muscle map", muscleMap(D.strength.muscles.groups, "freshness"))}
      ${sec("Route thumb & map", lib ? `<div class="row">${routeThumb(lib.lines)}${surfaceBar(lib.surface)}</div>${mapSvg(lib.lines, { label: lib.name, h: 140 })}` : empty(STR.noRoute))}
      ${sec("Step list", (D.plans.routines[0] ? stepList(D.plans.routines[0].steps) : empty("No routines yet")))}
      ${sec("Sheets & toast", `<div class="row wrap"><button class="btn sm secondary" data-open="data-status">Data freshness sheet</button><button class="btn sm secondary" data-open="factors">Factors sheet</button><button class="btn sm secondary" id="gal-toast">Toast</button></div>`)}
    </div></div>`;
  },
  after() { drawCharts(); const b = $("#gal-toast"); if (b) b.onclick = () => toast("This is a toast", { label: "Undo", run: () => toast("Undo pressed") }); },
};
