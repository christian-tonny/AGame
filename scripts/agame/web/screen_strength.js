/* Strength: muscle status, history, exercise progress, records, Strength Builder */
"use strict";

AG.screens.strength = {
  title: "Strength",
  render(r) {
    const tab = r.params.tab || chipVal("str-tab", "overview");
    if (r.params.tab) uiSet("chip:str-tab", r.params.tab);
    const body = { overview: strOverview, history: strHistory, exercises: strExercises, builder: strBuilder, records: strRecords }[tab] || strOverview;
    return `${chips("str-tab", [["overview", "Overview"], ["history", "History"], ["exercises", "Exercises"], ["builder", "Builder"], ["records", "Records"]], tab)}<div style="margin-top:12px">${body()}</div>`;
  },
  after() { drawCharts(); bindBuilder(); },
};

function strOverview() {
  const M = D.strength.muscles;
  const mode = chipVal("mm-mode", "freshness");
  const W = D.strength.weekly;
  const groups = Object.entries(M.groups).filter(([, g]) => g.last_trained);
  const legend = mode === "freshness"
    ? `<span><i style="background:var(--recovery)"></i>Recovered</span><span><i style="background:var(--warn)"></i>Fatigued</span><span><i style="background:var(--bad)"></i>Depleted</span><span><i style="background:url(#hatch);border:1px solid var(--text-3)"></i>Calibrating</span>`
    : `<span><i style="background:var(--recovery)"></i>Productive/maintaining</span><span><i style="background:var(--warn)"></i>Overtraining</span><span><i style="background:var(--surface-3);border:1px solid var(--line-2)"></i>Detraining/no data</span>`;
  return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Muscle ${mode === "freshness" ? "freshness" : "load"}</h3>${seg("mm-mode", [["freshness", "Freshness"], ["load", "Load"]], mode)}</div>
      ${M.has_exercise_logs ? muscleMap(M.groups, mode) + `<div class="legend" style="margin-top:8px;justify-content:center">${legend}</div>` : empty(STR.noExercise, "Per-muscle load needs exercise-level logs (Strength Builder). HealthKit strength workouts alone don't say which muscles you trained.")}
      ${M.unlogged_strength_workouts ? `<p class="cap">${M.unlogged_strength_workouts} strength workout(s) in the last 6 weeks have no exercise log and are not counted per muscle.</p>` : ""}
      ${M.cardio_mapping_enabled ? `<p class="cap">Running and other cardio add an approximate leg load from a configurable activity-to-muscle mapping.</p>` : ""}</div>
    <div class="card"><h3>Weekly strength</h3>${chart({ id: "str-w", type: "bar", label: "Weekly strength volume", x: W.map(w => w.week), h: 150, partialIndex: W.length - 1,
      series: [{ name: "Volume", color: "var(--strength)", values: W.map(w => w.logged_sessions ? (IMPERIAL ? w.volume_kg * 2.20462 : w.volume_kg) : null) }],
      fmtX: d => "Week of " + fmt.date(d), fmtXAxis: d => fmt.date(d), fmtY: v => fmt.n(v) + " " + fmt.wUnit(), tipExtra: i => `<div class="k">${W[i].sessions} sessions · ${W[i].sets} sets · ${W[i].minutes} min</div>` })}
      <p class="cap">Volume = weight × reps on working sets. Weeks without logs show no bar (not zero).</p></div></div>
    <div class="stack"><div class="card"><h3>By muscle group</h3>${groups.length ? `<table class="tbl"><tr><th>Muscle</th><th>Load</th><th>Freshness</th><th class="r">Sets 7d</th></tr>${groups.map(([m, g]) => `<tr><td>${esc(fmt.sport(m))}${g.approximate ? " *" : ""}</td><td>${esc(fmt.sport(g.load_status))}</td><td>${esc(fmt.sport(g.freshness))}</td><td class="r">${fmt.n(g.sets_7d, 1)}</td></tr>`).join("")}</table><p class="cap">* approximate (cardio mapping only). Calibration: load needs ${M.calibration.load_min_sessions} logged sessions per muscle in ${M.calibration.load_weeks} weeks; freshness needs ${M.calibration.freshness_min_sessions}.</p>` : empty(STR.noData)}</div>
    <div class="card"><h3>Recent sessions</h3><div class="list">${D.strength.sessions.slice(0, 5).map(strSessionRow).join("") || empty(STR.noData)}</div></div></div></div>`;
}
function strSessionRow(s) {
  return `<button class="li" data-open="str-session" data-arg="${esc(s.workout_id || s.session_id)}"><span class="icon-dot" style="color:var(--strength)">${icon("strength")}</span><div class="grow"><div class="t">${esc(s.name || "Strength")}</div>
    <div class="s">${fmt.dow(s.date)} ${fmt.date(s.date)}${s.duration_s ? " · " + fmt.mins(s.duration_s) : ""}${s.logged ? ` · ${s.sets} sets · ${fmt.kg(s.volume_kg, 0)}` : " · not logged"}</div></div>${s.logged ? "" : badge("No sets", "")}</button>`;
}
AG.sheets["str-session"] = function (id) {
  const s = D.strength.sessions.find(x => (x.workout_id || x.session_id) === id);
  if (!s) return;
  openSheet(s.name || "Strength", `<div class="stats-grid s4">${stat("Elapsed", s.duration_s ? fmt.dur(s.duration_s) : "—")}${stat("Volume", s.logged ? fmt.kg(s.volume_kg, 0) : "—")}${stat("Sets", s.logged ? s.sets : "—")}${stat("Avg HR", isNum(s.avg_hr) ? s.avg_hr : "—", isNum(s.avg_hr) ? "bpm" : "")}</div>
    ${s.logged ? muscleMap({}, "freshness", s.muscles) + s.exercises.map(ex => `<div style="margin-top:10px"><b>${esc(ex.name)}</b><table class="tbl">${ex.sets.map((st, i) => `<tr><td>${st.warmup ? "W" : i}</td><td>${isNum(st.weight_kg) ? fmt.kg(st.weight_kg) : "BW"} × ${st.reps}</td><td class="r">${isNum(st.rpe) ? "RPE " + st.rpe : ""}${isNum(st.rir) ? " RIR " + st.rir : ""}</td></tr>`).join("")}</table></div>`).join("") : empty(STR.noExercise)}
    ${s.workout_id ? `<a class="btn secondary" style="width:100%;margin-top:12px" href="#/activity/${encodeURIComponent(s.workout_id)}">Open workout</a>` : ""}`);
};

function strHistory() {
  const S = D.strength.sessions;
  return S.length ? `<div class="card tight"><div class="list">${S.map(strSessionRow).join("")}</div></div>` : empty(STR.noData, "Strength workouts appear after import; log sets in the Builder");
}

function strExercises() {
  const stats = Object.values(D.strength.stats).sort((a, b) => b.count - a.count);
  if (!stats.length) return empty("No exercise logs yet", "Log sets in the Builder to track e1RM, volume and PRs");
  const sel = chipVal("str-ex", stats[0].id);
  const ex = D.strength.stats[sel] || stats[0];
  const rows = ex.sessions;
  return `<div class="stack">${chips("str-ex", stats.map(s => [s.id, s.name]), ex.id)}
    <div class="cols"><div class="stack"><div class="card"><div class="stats-grid s4">${stat("Best e1RM", ex.best_e1rm ? fmt.kg(ex.best_e1rm.value) : "—")}${stat("Heaviest", ex.heaviest ? fmt.kg(ex.heaviest.value) : "—")}${stat("Best session volume", ex.best_session_volume ? fmt.kg(ex.best_session_volume.value, 0) : "—")}${stat("Sessions", ex.count)}</div>
      ${ex.progression_hint ? insightCard(ex.progression_hint.text, "Next session · from last session's RPE") : ""}<p class="cap">e1RM = Epley estimate (labelled estimate), computed from your logged sets.</p></div>
      <div class="card"><h3>Progressive overload</h3>${chart({ id: "ex-e1", label: "Estimated 1RM over time", x: rows.map(r => r.date), h: 160, series: [{ name: "e1RM", color: "var(--strength)", values: rows.map(r => isNum(r.e1rm_kg) ? (IMPERIAL ? r.e1rm_kg * 2.20462 : r.e1rm_kg) : null), dots: true }, { name: "Heaviest", color: "var(--text-2)", values: rows.map(r => isNum(r.heaviest_kg) ? (IMPERIAL ? r.heaviest_kg * 2.20462 : r.heaviest_kg) : null), dots: true, dash: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v, 1) + " " + fmt.wUnit() })}</div></div>
      <div class="stack"><div class="card"><h3>Volume per session</h3>${chart({ id: "ex-vol", type: "bar", label: "Volume per session", x: rows.map(r => r.date), h: 140, series: [{ name: "Volume", color: "var(--strength)", values: rows.map(r => IMPERIAL ? r.volume_kg * 2.20462 : r.volume_kg) }], fmtX: d => fmt.date(d), fmtY: v => fmt.n(v) + " " + fmt.wUnit() })}</div>
      <div class="card"><h3>History</h3><table class="tbl"><tr><th>Date</th><th class="r">Sets</th><th class="r">Reps</th><th class="r">Top</th><th class="r">RPE</th></tr>${rows.slice().reverse().slice(0, 15).map(r => `<tr><td>${fmt.date(r.date)}</td><td class="r">${r.sets}</td><td class="r">${r.reps}</td><td class="r">${isNum(r.heaviest_kg) ? fmt.kgNum(r.heaviest_kg) : "BW"}</td><td class="r">${isNum(r.avg_rpe) ? r.avg_rpe : "—"}</td></tr>`).join("")}</table></div></div></div></div>`;
}

function strRecords() {
  const prs = D.strength.prs;
  if (!prs.length) return empty("No strength records yet", "Records come from logged sets");
  const by = {};
  prs.forEach(p => (by[p.exercise] = by[p.exercise] || []).push(p));
  return `<div class="cols">${Object.entries(by).map(([ex, list]) => `<div class="card"><h3>${esc(ex)}</h3><div class="list">${list.map(p => `<div class="li"><div class="grow"><div class="t">${esc(p.label)}</div><div class="s">${fmt.date(p.date, { day: "numeric", month: "short", year: "numeric" })}</div></div><div class="r">${p.record === "max_reps" ? p.value + " reps" : fmt.kg(p.value, p.record.includes("volume") ? 0 : 1)}</div></div>`).join("")}</div></div>`).join("")}</div>`;
}

function strBuilder() {
  const lib = D.strength.library;
  const routines = D.strength.routines;
  const plates = D.strength.plates || {};
  return `<div class="cols"><div class="stack"><div class="card"><h3>Log a workout</h3>
      <form class="form" id="str-log">
        <label>Name <input name="name" placeholder="e.g. Lower body"></label>
        <label>Date & time <input name="start" type="datetime-local" required></label>
        <div id="str-ex-list"></div>
        <div class="row wrap"><select id="str-add" aria-label="Exercise to add" style="flex:1">${lib.map(x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("")}</select><button class="btn sm secondary" type="button" id="str-add-btn">Add exercise</button></div>
        <label>Notes <textarea name="notes" rows="2"></textarea></label>
        <button class="btn" type="submit" ${AG.online ? "" : "disabled"}>Save workout</button>${offlineNote()}
      </form><p class="cap">Log live or after the fact. Saved to strength.json with edit history and undo.</p></div>
    <div class="card"><h3>Routines</h3>${routines.length ? `<div class="list">${routines.map(r => `<div class="li"><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${r.exercises.map(e => esc((lib.find(x => x.id === e.exercise_id) || {}).name || e.exercise_id) + ` ${e.sets || ""}×${esc(e.reps || "")}${e.rpe ? " @RPE" + e.rpe : ""}`).join(" · ")}</div></div><button class="btn sm secondary" type="button" data-use-routine="${esc(r.id)}">Use</button></div>`).join("")}</div>` : empty("No routines yet")}</div></div>
    <div class="stack"><div class="card"><h3>Rest timer</h3><div class="spread"><div class="stat hero"><span class="v num" id="rest-t" aria-live="polite">0:00</span></div><div class="row wrap">${[60, 90, 120, 180].map(s => `<button class="btn sm secondary" type="button" data-rest="${s}">${s < 120 ? s + "s" : s / 60 + "m"}</button>`).join("")}</div></div><p class="cap">Runs in the page, offline too.</p></div>
    <div class="card"><h3>Plate calculator</h3>${isNum(plates.bar_kg) && plates.plates_kg && plates.plates_kg.length ? `<form class="form" id="plate-form"><label>Target (${fmt.wUnit()}) <input name="target" type="number" step="0.5" inputmode="decimal" value=""></label></form><div id="plate-out" class="small" aria-live="polite"></div><p class="cap">Bar ${fmt.kg(plates.bar_kg, 1)} · plates ${plates.plates_kg.map(p => fmt.kgNum(p, 2)).join(", ")} (from strength.json).</p>` : empty("Plates not configured", "Set bar and plate weights in strength.json")}</div>
    <div class="card"><h3>Live workout & watch sync</h3><p class="small">${D.strength.live_state ? "In progress: exercise " + (D.strength.live_state.exercise_index + 1) : "No live session"}</p><p class="cap">${STR.companion}. The live-state contract (strength.json → live_state) is documented for a future phone/watch app.</p></div>
    <div class="card"><h3>Exercise library</h3><p class="small muted">${lib.length} exercises (${lib.filter(x => x.source === "user").length} added by you)</p><div class="list" style="max-height:260px;overflow:auto">${lib.map(x => `<div class="li"><div class="grow"><div class="t">${esc(x.name)}</div><div class="s">${(x.primary || []).map(m => esc(fmt.sport(m))).join(", ")}${x.cue ? " · " + esc(x.cue) : ""}</div></div></div>`).join("")}</div></div></div></div>`;
}

function bindBuilder() {
  const form = $("#str-log");
  if (form) {
    const lib = D.strength.library;
    const list = $("#str-ex-list");
    const addEx = (id, sets = 3, reps = "", rpe = "") => {
      const x = lib.find(l => l.id === id);
      const div = document.createElement("div");
      div.className = "card flat tight";
      div.dataset.ex = id;
      div.innerHTML = `<div class="spread"><b>${esc(x ? x.name : id)}</b><button type="button" class="btn sm secondary" data-rm>Remove</button></div><div data-sets></div><button type="button" class="btn sm secondary" data-add-set style="margin-top:6px">Add set</button>`;
      const setsEl = div.querySelector("[data-sets]");
      const addSet = () => { const r = document.createElement("div"); r.className = "row"; r.style.marginTop = "6px"; r.innerHTML = `<input aria-label="Weight ${fmt.wUnit()}" placeholder="${fmt.wUnit()}" inputmode="decimal" data-w style="width:30%"><input aria-label="Reps" placeholder="reps" inputmode="numeric" data-r value="${esc(String(reps).split("-")[0])}" style="width:25%"><input aria-label="RPE" placeholder="RPE" inputmode="decimal" data-rpe value="${esc(rpe)}" style="width:22%"><label class="small" style="flex-direction:row;display:flex;gap:4px;align-items:center"><input type="checkbox" data-wu style="width:auto">W</label>`; setsEl.appendChild(r); };
      for (let i = 0; i < sets; i++) addSet();
      div.querySelector("[data-add-set]").onclick = addSet;
      div.querySelector("[data-rm]").onclick = () => div.remove();
      list.appendChild(div);
    };
    $("#str-add-btn").onclick = () => addEx($("#str-add").value);
    $$("[data-use-routine]").forEach(b => b.onclick = () => { const r = D.strength.routines.find(x => x.id === b.dataset.useRoutine); form.name.value = r.name; list.innerHTML = ""; r.exercises.forEach(e => addEx(e.exercise_id, e.sets || 3, e.reps || "", e.rpe || "")); });
    form.onsubmit = async e => {
      e.preventDefault();
      const toKg = v => v === "" || v === null ? null : (IMPERIAL ? +v / 2.20462 : +v);
      const exercises = $$("[data-ex]", list).map(div => ({ exercise_id: div.dataset.ex, sets: $$("[data-sets] .row", div).filter(r => $("[data-r]", r).value).map(r => ({ reps: +$("[data-r]", r).value, weight_kg: toKg($("[data-w]", r).value), rpe: $("[data-rpe]", r).value ? +$("[data-rpe]", r).value : null, rir: null, warmup: $("[data-wu]", r).checked })) })).filter(x => x.sets.length);
      if (!exercises.length) { toast("Add at least one set"); return; }
      const start = new Date(form.start.value);
      try { await api("POST", "entries/strength.sessions", { name: form.name.value || null, start: start.toISOString(), exercises, notes: form.notes.value || null }); toast("Saved · rebuilding"); setTimeout(() => location.reload(), 900); }
      catch (err) { toast(err.message); }
    };
  }
  $$("[data-rest]").forEach(b => b.onclick = () => {
    clearInterval(AG._rest);
    let left = +b.dataset.rest;
    const el = $("#rest-t");
    const tick = () => { el.textContent = fmt.dur(left); if (left <= 0) { clearInterval(AG._rest); el.textContent = "Go"; try { navigator.vibrate && navigator.vibrate(200); } catch (e) { } } left--; };
    tick(); AG._rest = setInterval(tick, 1000);
  });
  const pf = $("#plate-form");
  if (pf) pf.oninput = () => {
    const p = D.strength.plates;
    let target = +pf.target.value;
    if (!target) { $("#plate-out").textContent = ""; return; }
    if (IMPERIAL) target = target / 2.20462;
    let side = (target - p.bar_kg) / 2;
    if (side < 0) { $("#plate-out").textContent = "Below bar weight"; return; }
    const out = [];
    p.plates_kg.slice().sort((a, b) => b - a).forEach(pl => { while (side >= pl - 1e-9) { out.push(pl); side -= pl; } });
    $("#plate-out").innerHTML = `Per side: <b>${out.length ? out.map(x => fmt.kgNum(x, 2)).join(" + ") : "none"}</b>${side > 0.01 ? ` <span class="faint">(${fmt.kg(side * 2, 2)} short)</span>` : ""}`;
  };
}
