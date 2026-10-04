/* Routes, Goals, Coach, Profile */
"use strict";

AG.screens.routes = {
  title: "Routes",
  render() {
    const tab = chipVal("rt-tab", "library");
    const body = { library: rtLibrary, heatmap: rtHeatmap, segments: rtSegments, builder: rtBuilder }[tab]();
    return `${chips("rt-tab", [["library", "Library"], ["heatmap", "Heatmap"], ["segments", "Segments"], ["builder", "Route builder"]], tab)}<div style="margin-top:12px">${body}</div>`;
  },
  after() { drawCharts(); bindRouteImport(); },
};
function rtLibrary() {
  const lib = D.routes.library;
  if (!lib.length) return empty(STR.noRoute, "Routes come from routes.geojson (your saved routes and GPS traces)");
  const f = chipVal("rt-filter", "all");
  let rows = lib;
  if (f === "fav") rows = rows.filter(r => r.favorite);
  if (f === "offline") rows = rows.filter(r => r.offline);
  if (f === "short") rows = rows.filter(r => r.distance_m < 8000);
  if (f === "long") rows = rows.filter(r => r.distance_m >= 12000);
  if (f === "hilly") rows = rows.slice().sort((a, b) => (b.elevation_gain_m || 0) / b.distance_m - (a.elevation_gain_m || 0) / a.distance_m);
  const sf = chipVal("rt-surface", "any"), df = chipVal("rt-diff", "any");
  if (sf === "paved") rows = rows.filter(r => r.surface && r.surface.paved_pct >= 50);
  if (sf === "unpaved") rows = rows.filter(r => r.surface && r.surface.unpaved_pct >= 50);
  if (df !== "any") rows = rows.filter(r => (r.difficulty || "").toLowerCase() === df);
  const diffs = [...new Set(lib.map(r => (r.difficulty || "").toLowerCase()).filter(Boolean))];
  const rec = D.routes.recommendations;
  return `<div class="cols"><div class="stack">${chips("rt-filter", [["all", "All"], ["fav", "Favorites"], ["offline", "Saved offline"], ["short", "Length < 8 km"], ["long", "Length ≥ 12 km"], ["hilly", "Elevation"]], f)}
    ${lib.some(r => r.surface) ? chips("rt-surface", [["any", "Any surface"], ["paved", "Mostly paved"], ["unpaved", "Mostly unpaved"]], sf) : ""}
    ${diffs.length ? chips("rt-diff", [["any", "Any difficulty"]].concat(diffs.map(d => [d, fmt.sport(d)])), df) : ""}
    <div class="card tight"><div class="list">${rows.map(r => `<a class="li" href="#/route/${encodeURIComponent(r.id)}">${routeThumb(r.lines)}<div class="grow"><div class="t">${esc(r.name || r.id)} ${r.favorite ? "★" : ""}</div>
      <div class="s">${fmt.dist(r.distance_m)} · ${fmt.elev(r.elevation_gain_m)}${r.est_time_s ? " · " + fmt.mins(r.est_time_s) : ""}</div><div class="s">${r.times_run} runs${r.difficulty ? " · " + esc(r.difficulty) : ""}${r.offline ? " · offline" : ""}</div></div></a>`).join("") || empty("No routes match")}</div></div></div>
    <div class="stack"><div class="card"><h3>Made for you</h3>${rec.length ? `<div class="list">${rec.map(r => `<a class="li" href="#/route/${encodeURIComponent(r.route_id)}"><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${esc(r.why)}</div></div><div class="r small">${fmt.dist(r.distance_m)}</div></a>`).join("")}</div>` : empty(STR.noData)}<p class="cap">Recommended only from your own route library.</p></div>
    <div class="card"><h3>Offline</h3><p class="small">${lib.filter(r => r.offline).length} route(s) saved offline. The app caches the whole snapshot, so every route here opens without a connection.</p></div></div></div>`;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-route-flag]");
  if (!b) return;
  const r = parseHash();
  act("route.flag", { route_id: r.arg, [b.dataset.routeFlag]: b.dataset.val === "1" }, "Route updated").catch(() => {});
});
AG.screens.route = {
  title: r => { const x = D.routes.library.find(y => y.id === r.arg); return x ? x.name : "Route"; }, parent: "#/routes", nav: "routes",
  render(r) {
    const x = D.routes.library.find(y => y.id === r.arg);
    if (!x) return empty("Route not found");
    const tools = AG.online ? `<div class="edit-row"><button class="btn sm secondary" data-route-flag="favorite" data-val="${x.favorite ? 0 : 1}">${x.favorite ? "★ Favorite" : "☆ Add to favorites"}</button><button class="btn sm secondary" data-route-flag="offline" data-val="${x.offline ? 0 : 1}">${x.offline ? "Saved offline ✓" : "Save offline"}</button>${x.imported ? `<button class="btn sm danger" data-open="route-del" data-arg="${esc(x.id)}">Delete</button>` : ""}</div>` : "";
    return `<div class="cols"><div class="stack"><div class="card">${mapSvg(x.lines, { label: x.name, noEnds: false })}${tools}</div>
      <div class="card"><div class="stats-grid s4">${stat("Distance", fmt.dist(x.distance_m))}${stat("Elevation", fmt.elev(x.elevation_gain_m))}${stat("Est. time", x.est_time_s ? fmt.mins(x.est_time_s) : "—")}${stat("Runs", x.times_run)}</div>${x.est_basis ? `<p class="cap">Estimate: ${esc(x.est_basis)}.</p>` : ""}
      ${x.surface ? `<div style="margin-top:10px">${surfaceBar(x.surface)}</div>` : ""}</div></div>
      <div class="stack">${x.profile ? `<div class="card"><h3>Elevation profile</h3>${chart({ id: "rt-prof", type: "profile", label: "Elevation profile", points: x.profile, h: 140 })}</div>` : ""}
      <div class="card"><h3>Your efforts</h3>${x.efforts.length ? `<table class="tbl"><tr><th>Date</th><th class="r">Time</th><th class="r">Pace</th></tr>${x.efforts.slice().reverse().map(e => `<tr><td><a href="#/activity/${encodeURIComponent(e.workout_id)}">${fmt.date(e.date, { day: "numeric", month: "short", year: "numeric" })}</a></td><td class="r">${fmt.dur(e.time_s)}</td><td class="r">${fmt.pace(e.pace_s_per_km)}</td></tr>`).join("")}</table>` : empty("Not run yet")}</div></div></div>`;
  },
  after() { drawCharts(); },
};
function rtHeatmap() {
  const H = D.routes.heatmap;
  if (H.status !== "ok") return empty(STR.noRoute, "The personal heatmap is built from your own GPS traces");
  const rng = chipVal("hm-range", "all"), fam = chipVal("hm-fam", "all"), night = chipVal("hm-night", "all");
  const v = H.variants[`${rng}|${fam}|${night}`];
  const cells = v ? v.cells : [];
  let svg = empty("No activities for this filter");
  if (cells.length) {
    const pr = project([cells.map(c => [c[0], c[1]])], 640, 400, 14);
    const max = Math.max(...cells.map(c => c[2]));
    svg = `<div class="map" style="aspect-ratio:16/10;background:${night === "night" ? "#05060a" : "var(--surface-2)"}" role="img" aria-label="Personal heatmap"><svg viewBox="0 0 640 400">${cells.map(c => { const p = pr([c[0], c[1]]); const a = 0.25 + 0.75 * Math.sqrt(c[2] / max); return `<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="2.2" fill="${night === "night" ? "#7f8cff" : "var(--accent)"}" opacity="${a.toFixed(2)}"/>`; }).join("")}</svg><span class="attrib">Your GPS traces · privacy zones applied</span></div>`;
  }
  return `<div class="stack">${chips("hm-range", [["all", "All time"], ["365", "Past year"], ["90", "90 days"]], rng)}${chips("hm-fam", [["all", "All sports"], ["run", "Run"], ["ride", "Ride"], ["walk", "Walk"]], fam)}${chips("hm-night", [["all", "Day & night"], ["night", "Night only"]], night, "accent")}
    <div class="card">${svg}<p class="cap">${v ? v.activities + " activities" : ""}. Night = started between local sunset and sunrise (computed from coordinates).</p></div></div>`;
}
function rtSegments() {
  const S = D.routes.segments;
  if (!S.length) return empty("No segments yet", "Define segments on your routes in routes.geojson (kind: segment)");
  return `<div class="stack">${S.map(s => `<div class="card"><div class="spread"><h3 style="margin:0">${esc(s.name)}</h3><span class="small muted">${fmt.dist(s.distance_m)} · ${fmt.elev(s.elevation_gain_m)}</span></div>
    <div class="cols" style="margin-top:10px"><div>${mapSvg(s.lines, { label: s.name, h: 140 })}</div><div>
    <div class="stats-grid s3">${stat("PR", s.pr ? fmt.dur(s.pr.time_s) : "—")}${stat("Efforts", s.count)}${stat("Last", s.efforts.length ? fmt.dur(s.efforts[s.efforts.length - 1].time_s) : "—")}</div>
    ${s.efforts.length > 1 ? chart({ id: "seg-" + s.id, label: "Segment times", x: s.efforts.map(e => e.date), h: 120, invertY: true, series: [{ name: "Time", color: "var(--accent)", values: s.efforts.map(e => e.time_s), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.dur(v) }) : ""}
    <div class="empty inline" style="margin-top:10px"><b>Leaderboard</b><span class="cap">${s.leaderboard_status === "connected" ? s.leaderboard.length + " efforts" : STR.noLeaderboard}</span></div>
    <p class="cap">Live segment progress: ${STR.companion}.</p></div></div></div>`).join("")}</div>`;
}
function rtBuilder() {
  const tiles = D.routes.tiles;
  return `<div class="card">${tiles ? `<p class="small">Tile provider configured. Draw a route by adding points; points snap to your own traces.</p>` : empty(STR.noMap, "Set integrations.map_tiles_url in profile.json to draw on a map. GPX/GeoJSON import works without tiles.")}
    <form class="form" style="margin-top:12px" onsubmit="return false"><label>Route name (optional) <input id="route-name" placeholder="Uses the file name if empty"></label><label>Import GPX or GeoJSON <input type="file" id="route-file" accept=".gpx,.geojson,.json" ${AG.online ? "" : "disabled"}></label>${offlineNote()}</form>
    <p class="cap">Imported routes are added to routes.geojson through your AGame server.</p></div>`;
}

/* ---------------- Goals ---------------- */
AG.screens.goals = {
  title: "Goals",
  render() {
    const G = D.goals;
    const st = D.streak;
    return `<div class="cols"><div class="stack"><div class="card"><div class="spread"><div><div class="cap">Weekly streak</div><div class="stat"><span class="v">${st.current}<small>weeks</small></span></div><div class="cap">Longest ${st.longest} · this week ${st.this_week_done ? "done" : st.this_week_count + " so far"}</div></div>${icon("flame")}</div></div>
      <div class="card">${G.length ? G.map(g => goalRow(g, { edit: true })).join("") : empty(STR.noGoals, "Add one with New goal")}</div></div>
      <div class="stack"><div class="card"><h3>Add a goal</h3><p class="small muted">Distance, time, elevation, sessions, load, calories, records, strength, body weight, protein days, streaks and habits.</p>
        ${AG.online ? `<button class="btn" data-open="goal-new">New goal</button>` : offlineNote()}<p class="cap">Targets are never defaulted; goals are stored in goals.json with edit history and undo.</p></div>
      ${consistencyCard()}</div></div>`;
  },
  after() { drawCharts(); },
};

/* ---------------- Coach ---------------- */
AG.screens.coach = {
  title: "Coach",
  render() {
    const C = D.coach;
    const mode = chipVal("coach-mode", (C.settings || {}).mode || "adaptive");
    const ghost = chipVal("coach-ghost", "off") === "on";
    const win = chipVal("hh-win", "90");
    const r = C.recommendation;
    const threads = (C.threads || []).slice(-1)[0];
    return `<div class="cols c21"><div class="stack">
      <div class="coach-hero"><div class="orb" aria-hidden="true"></div><div class="cap">${fmt.dateLong(D.meta.build_date)}</div><div style="font-size:22px;font-weight:800">${D.profile.display_name ? "Welcome back, " + esc(D.profile.display_name.split(" ")[0]) : "Your coach"}</div></div>
      <div class="row wrap" style="justify-content:center">${C.suggestions.map(s => `<button class="chip" data-ask="${esc(s)}">${esc(s)}</button>`).join("")}</div>
      <div class="card"><div class="chat" id="chat">
        ${C.brief && C.brief.line1 ? `<div class="msg coach">${esc(C.brief.line1)}. ${esc(C.brief.line2)}.</div>` : ""}
        <div class="msg coach">${esc((CALL_LABEL[r.call] || [r.call])[0])} — ${esc(r.why)}.${r.factors.length ? " Top factors: " + r.factors.slice(0, 3).map(f => esc(f.label) + " (" + esc(f.direction) + ")").join(", ") + "." : ""}</div>
        ${threads ? threads.messages.slice(-6).map(m => `<div class="msg ${m.role === "user" ? "user" : "coach"}">${esc(m.text)}</div>`).join("") : ""}</div>
      <form class="composer" style="margin-top:12px" data-coach-form><label class="sr" for="coach-q">Ask your coach</label><textarea id="coach-q" name="q" placeholder="Ask AGame anything about your data"></textarea>
        <div class="spread" style="flex-wrap:wrap"><div class="row wrap">${seg("coach-mode", [["fast", "Fast"], ["thinking", "Thinking"], ["adaptive", "Adaptive"]], mode)}<button type="button" class="chip ${ghost ? "" : ""}" data-chip="coach-ghost" data-val="${ghost ? "off" : "on"}" aria-pressed="${ghost}">Ghost</button></div><button class="btn sm">Ask</button></div>
        ${ghost ? `<p class="cap">Ghost Mode: this chat is not saved and is not written to logs.</p>` : ""}
        ${AG.llm ? "" : `<p class="cap">${STR.noCoachLLM}. Deterministic insights above always work; conversational answers need AGAME_LLM_PROVIDER on your server.</p>`}</form></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Helping & hurting</h3>${seg("hh-win", [["7", "7d"], ["30", "30d"], ["90", "90d"]], win)}</div>${helpingList(win)}<p class="cap">Correlations between your behaviours and next-morning recovery, shown only with enough observations.</p></div></div>
      <div class="stack"><div class="card"><h3>Personality</h3>${chips("coach-pers", [["data_nerd", "Data Nerd"], ["guardian", "Guardian"], ["friend", "Friend"], ["commander", "Commander"]], chipVal("coach-pers", (C.settings || {}).personality || "data_nerd"))}<p class="cap">Changes tone only — the facts stay the same. ${AG.online ? `<a href="#" data-open="edit-coach">Save as default</a>` : ""}</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Check-ins</h3>${editBtn("checkin-edit", "", "Add")}</div>${C.checkins.length ? `<div class="list">${C.checkins.map(c => `<${AG.online ? `button type="button" data-open="checkin-edit" data-arg="${esc(c.id)}"` : "div"} class="li"><div class="grow"><div class="t">${esc(fmt.sport(c.type))}${c.text ? " · " + esc(c.text) : ""}</div><div class="s">${esc(c.time)} · ${esc((c.days || []).join(" "))}</div></div>${badge(c.enabled ? "On" : "Off", c.enabled ? "ok" : "")}</${AG.online ? "button" : "div"}>`).join("")}</div>` : empty("No check-ins scheduled")}<p class="cap">Delivered by ${esc(AGENT)} on schedule.</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Memory</h3>${editBtn("memory-edit", "", "Add")}</div>${C.memory.length ? `<div class="list">${C.memory.map(m => `<${AG.online ? `button type="button" data-open="memory-edit" data-arg="${esc(m.id)}"` : "div"} class="li"><div class="grow"><div class="t small">${esc(m.text)}</div><div class="s">${esc(fmt.sport(m.type))}</div></div></${AG.online ? "button" : "div"}>`).join("")}</div>` : empty("Nothing remembered yet")}<p class="cap">Preferences, goals and corrections you keep. Editable, deletable, with history. Last maintenance ${C.last_maintenance ? fmt.date(C.last_maintenance) : "never"}.</p>${offlineNote()}</div>
      <div class="card"><h3>Research</h3><p class="small muted">Citations appear only when an external research source is supplied with an answer. AGame never invents citations.</p></div></div></div>`;
  },
};
document.addEventListener("click", e => {
  const b = e.target.closest("[data-ask]");
  if (b) { const t = $("#coach-q"); if (t) { t.value = b.dataset.ask; t.focus(); } }
});
document.addEventListener("submit", async e => {
  const f = e.target.closest("[data-coach-form]");
  if (!f) return;
  e.preventDefault();
  const q = f.q.value.trim();
  if (!q) return;
  const chat = $("#chat") || f.parentElement.querySelector(".chat");
  chat.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(q)}</div>`);
  f.q.value = "";
  if (!AG.online || !AG.llm) { chat.insertAdjacentHTML("beforeend", `<div class="msg coach">${esc(STR.noCoachLLM)}. Here is what your data says today: ${esc(D.today.action ? D.today.action.text : "")}.</div>`); return; }
  try {
    const res = await api("POST", "coach/ask", { q, mode: chipVal("coach-mode", "adaptive"), ghost: chipVal("coach-ghost", "off") === "on", activity_id: f.dataset.activity || null, personality: chipVal("coach-pers", "data_nerd") });
    chat.insertAdjacentHTML("beforeend", `<div class="msg coach">${esc(res.text)}${res.citations && res.citations.length ? `<div class="cap" style="margin-top:6px">${res.citations.map(c => esc(c.title || c.url)).join(" · ")}</div>` : ""}</div>`);
  } catch (err) { chat.insertAdjacentHTML("beforeend", `<div class="msg coach">${esc(err.message)}</div>`); }
});

/* ---------------- Profile ---------------- */
AG.screens.profile = {
  title: "Profile",
  render() {
    const p = D.profile;
    const ph = p.physiology || {};
    const m = (o, f) => o ? `${f(o.value)} <span class="cap">· ${esc(o.method || "")}${o.date ? " · " + fmt.date(o.date, { day: "numeric", month: "short", year: "numeric" }) : ""}</span>` : `<span class="faint">Not set</span>`;
    const tg = p.targets || {};
    const ds = D.meta.data_status;
    const integ = p.integrations || {};
    const theme = uiGet("theme", (p.ui || {}).theme || "system");
    return `<div class="cols"><div class="stack">
      <div class="card"><div class="row"><span class="icon-dot" style="width:52px;height:52px;border-radius:50%">${icon("profile")}</span><div class="grow"><div style="font-size:20px;font-weight:800">${esc(p.display_name || "Athlete")}</div><div class="cap">${esc(TZ)} · ${IMPERIAL ? "Imperial" : "Metric"} · week starts ${esc(D.meta.week_start)}</div></div></div>
        <div class="edit-row">${editBtn("edit-athlete", undefined, "Edit athlete")}${editBtn("edit-locale", undefined, "Units & time")}</div></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Physiology</h3>${editBtn("edit-physiology")}</div><table class="tbl">
        <tr><td>HR max</td><td>${m(ph.hr_max, v => v + " bpm")}</td></tr><tr><td>Resting HR</td><td>${m(ph.hr_rest, v => v + " bpm")}${ph.hr_rest ? "" : ` <span class="cap">· using 14-day HealthKit median</span>`}</td></tr>
        <tr><td>LTHR</td><td>${m(ph.lthr, v => v + " bpm")}</td></tr><tr><td>Threshold pace</td><td>${m(ph.threshold_pace_s_per_km, v => fmt.pace(v))}</td></tr>
        <tr><td>FTP</td><td>${m(ph.ftp_w, v => v + " W")}</td></tr><tr><td>Sleep need</td><td>${m(ph.sleep_need_base_min, v => fmt.hm(v))}</td></tr></table>
        <p class="cap">Zones: ${esc((p.zones_config || {}).model || "5zone")}. No age-based HR max is ever used. Threshold auto-accept: ${p.auto_accept_thresholds ? "on" : "off"}.</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Targets</h3>${editBtn("edit-targets")}</div><div class="stats-grid s3" style="margin-top:8px">${[["protein_g", "Protein", "g"], ["kcal", "Calories", "kcal"], ["fiber_g", "Fiber", "g"], ["water_ml", "Water", "ml"], ["caffeine_mg_max", "Caffeine max", "mg"], ["steps", "Steps", ""], ["vegetables_g", "Vegetables", "g"], ["sleep_min", "Sleep", "min"]].map(([k, l, u]) => stat(l, isNum(tg[k]) ? fmt.n(tg[k]) : "—", isNum(tg[k]) ? u : "")).join("")}</div>${tg.caffeine_cutoff ? `<p class="cap">Caffeine cutoff ${esc(tg.caffeine_cutoff)} · wake ${esc(tg.wake_time || "—")}</p>` : ""}</div>
      <div class="card"><div class="spread"><h3 style="margin:0">Weekly template</h3>${editBtn("edit-schedule")}</div>${(p.schedule || []).length ? `<div class="list">${p.schedule.map(s => `<div class="li"><div class="grow"><div class="t">${esc(fmt.sport(s.weekday))}</div></div><div class="r small">${esc(fmt.sport(s.intent))}${s.duration_s ? " · " + fmt.mins(s.duration_s) : ""}</div></div>`).join("")}</div>` : empty("No weekly template", "Add one with Edit")}</div></div>
      <div class="stack"><div class="card"><div class="spread"><h3 style="margin:0">Appearance</h3>${editBtn("edit-appearance")}</div>${seg("theme", [["system", "System"], ["dark", "Dark"], ["light", "Light"]], theme)}<p class="cap">App icon: ${esc((p.ui || {}).app_icon || "default")}. Mobile tabs: ${esc(mobileTabs().join(", "))}.</p></div>
      <div class="card"><h3>Data & sync</h3><p class="small">Last sync ${ds.last_sync ? fmt.dt(ds.last_sync) : "never"} · ${esc(statusLabel(ds.overall))}</p><button class="btn sm secondary" data-open="data-status">Per-domain freshness</button>
        <div class="row wrap" style="margin-top:10px"><a class="btn sm secondary ${AG.online ? "" : "disabled"}" href="api/export" ${AG.online ? "" : 'aria-disabled="true" onclick="return false"'}>Export my data</a><button class="btn sm secondary" data-open="history" ${AG.online ? "" : "disabled"}>Edit history & undo</button>${AG.online ? `<button class="btn sm danger" data-open="delete-all">Delete my entries</button>` : ""}</div>${offlineNote()}</div>
      <div class="card"><h3>Integrations</h3><div class="list">
        <div class="li"><div class="grow"><div class="t">Apple HealthKit via ${esc(AGENT)}</div><div class="s">Source of truth · ${ds.last_sync ? "last import " + fmt.dt(ds.last_sync) : "no import yet"}</div></div>${badge(ds.last_sync ? "Connected" : "Waiting", ds.last_sync ? "ok" : "")}</div>
        ${[["Map tiles", integ.map_tiles_url], ["Nutrition source", integ.nutrition_source], ["Calendar", integ.calendar_source], ["Food database", integ.food_database], ["Photo recognition", integ.vision_service], ["Coach LLM", AG.llm], ["Companion app (watch, alarm, Beacon)", integ.companion_app]].map(([l, v]) => `<div class="li"><div class="grow"><div class="t">${esc(l)}</div></div>${badge(v ? "Connected" : "Not connected", v ? "ok" : "")}</div>`).join("")}</div>
        <p class="cap">No Strava or Bevel data is ingested. Statuses reflect configuration only.</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Privacy</h3>${editBtn("edit-privacy")}</div><p class="small">Hide ${fmt.n((p.privacy || {}).hide_start_end_m)} m at the start and end of every map · ${((p.privacy || {}).zones || []).length} privacy zone(s)${((p.privacy || {}).zones || []).map(z => " · " + esc(z.label || z.id) + " " + z.radius_m + " m").join("")}.</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Companion features</h3>${editBtn("edit-companion")}</div><div class="list"><div class="li"><div class="grow"><div class="t">Smart alarm</div><div class="s">${(p.smart_alarm || {}).enabled ? "Configured" : "Off"}</div></div>${badge(STR.companion, "")}</div><div class="li"><div class="grow"><div class="t">Beacon live sharing</div><div class="s">${(p.beacon || {}).contacts || 0} contacts</div></div>${badge(STR.companion, "")}</div></div><p class="cap">These need a native companion app; this dashboard never pretends to track live.</p></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Modules & automation</h3>${editBtn("edit-modules")}</div><div class="list">${Object.entries(p.modules || {}).map(([k, v]) => `<div class="li"><div class="grow"><div class="t">${esc(fmt.sport(k))}</div></div>${badge(v ? "On" : "Off", v ? "ok" : "")}</div>`).join("")}</div></div>
      <div class="card"><div class="spread"><h3 style="margin:0">Coach</h3>${editBtn("edit-coach")}</div><p class="small">${esc(fmt.sport((p.coach || {}).personality || "data_nerd"))} · ${esc(fmt.sport((p.coach || {}).language || "standard"))} language · health records ${(p.coach || {}).include_health_records ? "shared" : "not shared"} with Coach</p></div>
      <a class="card chev row" href="#/widgets">${icon("today")} <b>Widgets</b></a><a class="card chev row" href="#/journal">${icon("timeline")} <b>Journal & status</b></a>
      <p class="cap">AGame ${esc(D.meta.version)} · schema ${esc(D.meta.schema_version)} · build ${esc(D.meta.build_date)}. Fitness information, not medical advice.</p></div></div>`;
  },
};
AG.sheets.history = async function () {
  try {
    const r = await api("GET", "history?limit=40");
    const label = i => i.op === "undo" ? "Undo" : fmt.sport(i.op);
    const what = i => esc(fmt.sport((i.collection || i.domain || "").replace(".", " · ")));
    const diff = i => {
      if (i.op !== "update" || !i.before || !i.after) return "";
      const keys = Object.keys(Object.assign({}, i.before, i.after)).filter(k => JSON.stringify(i.before[k]) !== JSON.stringify(i.after[k]) && !["updated_at"].includes(k)).slice(0, 4);
      return keys.map(k => `${esc(fmt.sport(k))}: ${esc(short(i.before[k]))} → ${esc(short(i.after[k]))}`).join(" · ");
    };
    const short = v => v === null || v === undefined ? "—" : typeof v === "object" ? "…" : String(v).slice(0, 40);
    openSheet("Edit history", `${r.items.length ? `<div class="list">${r.items.map(i => `<div class="li"><div class="grow"><div class="t small">${label(i)} · ${what(i)}</div><div class="s">${fmt.dt(i.ts)}${i.group ? " · one action" : ""}</div>${diff(i) ? `<div class="s">${diff(i)}</div>` : ""}</div></div>`).join("")}</div>
      <button class="btn" id="undo-btn" style="margin-top:12px;width:100%">Undo last change</button>` : `<p class="small muted">No edits yet</p>`}`,
      { after: sh => { const b = $("#undo-btn", sh); if (b) b.onclick = undoLast; } });
  } catch (err) { toast(err.message); }
};

const WIDGETS = {
  scores: ["Scores", w => `<div class="rings" style="transform:scale(.62);transform-origin:left top;width:160%">${ring("strain", w.rings.strain, { label: "Strain" })}${ring("recovery", w.rings.recovery, { label: "Recovery" })}${ring("sleep", w.rings.sleep, { label: "Sleep" })}</div>`],
  recovery: ["Recovery", w => `<b style="font-size:28px">${val(w.rings.recovery, 0, "%")}</b>${stLine(w.rings.recovery)}`],
  sleep: ["Sleep", w => `<b style="font-size:28px">${val(w.rings.sleep, 0, "%")}</b>${stLine(w.rings.sleep)}`],
  strain: ["Strain", w => `<b style="font-size:28px">${val(w.rings.strain, 0, "%")}</b><span class="cap">so far today</span>`],
  energy: ["Energy", w => `<b style="font-size:28px">${w.energy ? w.energy.current + "%" : "—"}</b><div class="energy"><i style="width:${w.energy ? w.energy.current : 0}%"></i></div>`],
  protein: ["Protein", w => `<b style="font-size:28px">${w.protein && isNum(w.protein.v) ? fmt.n(w.protein.v) + " g" : "—"}</b>${w.protein_target ? bar(w.protein && isNum(w.protein.v) ? w.protein.v / w.protein_target * 100 : 0, "var(--protein)") : `<span class="cap">${STR.noNutrition}</span>`}`],
  hydration: ["Hydration", w => `<b style="font-size:28px">${isNum(w.water_ml) ? fmt.n(w.water_ml) + " ml" : "—"}</b>${isNum(w.water_target) ? bar(isNum(w.water_ml) ? w.water_ml / w.water_target * 100 : 0, "var(--info)") : ""}`],
  plan: ["Today's plan", w => w.plan.length ? `<b>${esc(w.plan[0].title || w.plan[0].type)}</b><span class="cap">${w.plan[0].duration_s ? fmt.mins(w.plan[0].duration_s) : ""}</span>` : `<span class="small muted">${STR.noPlan}</span>`],
  weight: ["Weight", w => `<b style="font-size:28px">${w.weight && isNum(w.weight.v) ? fmt.kgNum(w.weight.v) : "—"}</b><span class="cap">${w.weight_goal ? "goal " + fmt.kg(w.weight_goal.target) : fmt.wUnit()}</span>`],
  load: ["Weekly load", w => `<b style="font-size:28px">${isNum(w.weekly_load) ? fmt.n(w.weekly_load) : "—"}</b><span class="cap">${w.weekly_band ? "range " + fmt.n(w.weekly_band.low) + "–" + fmt.n(w.weekly_band.high) : ""}</span>`],
  goal: ["Goal", w => w.goal ? `<b class="small">${esc(w.goal.title)}</b>${goalStatusBadge(w.goal.status_label)}` : `<span class="small muted">${STR.noGoals}</span>`],
};
function widgetCard(key, pinBtn) {
  const [title, render] = WIDGETS[key];
  const pinned = ((P.ui || {}).today_widgets || []).includes(key);
  return `<div class="card tight" style="aspect-ratio:1;display:flex;flex-direction:column;justify-content:space-between;min-width:0"><div class="spread"><span class="cap">${esc(title)}</span>${pinBtn && AG.online ? `<button type="button" class="icon-btn" data-pin="${key}" aria-pressed="${pinned}" aria-label="${pinned ? "Unpin from" : "Pin to"} Today" title="${pinned ? "Unpin from" : "Pin to"} Today">${pinned ? "★" : "☆"}</button>` : ""}</div>${render(D.widgets)}</div>`;
}
function todayWidgetRow() {
  const keys = ((P.ui || {}).today_widgets || []).filter(k => WIDGETS[k]);
  return keys.length ? `<div class="grid g4 hide-m" style="margin-bottom:12px">${keys.map(k => widgetCard(k, false)).join("")}</div>` : "";
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-pin]");
  if (!b) return;
  const cur = ((P.ui || {}).today_widgets || []).filter(k => k !== b.dataset.pin);
  if (b.getAttribute("aria-pressed") !== "true") cur.push(b.dataset.pin);
  save("PATCH", "profile", { ui: Object.assign({}, P.ui || {}, { today_widgets: cur }) }, "Today row updated").catch(() => {});
});
AG.screens.widgets = {
  title: "Widgets", parent: "#/profile", nav: "profile",
  render() {
    const w = D.widgets;
    return `<div class="grid g4">${Object.keys(WIDGETS).map(k => widgetCard(k, true)).join("")}</div>
      <p class="cap" style="margin-top:12px">☆ pins a widget to a custom row at the top of Today on desktop. Home-screen widgets need a native companion; dist/widgets.json is the documented payload. Data as of ${w.as_of ? fmt.dt(w.as_of) : "—"}. Health records never appear in widgets.</p>`;
  },
};

AG.screens.journal = {
  title: "Journal", parent: "#/profile", nav: "profile",
  render() {
    const J = D.journal;
    return `<div class="cols"><div class="stack"><div class="card"><h3>Activity status</h3><div class="stat"><span class="v" style="font-size:24px">${J.status ? esc(fmt.sport(J.status.status)) : "Normal"}</span></div>${J.status ? `<p class="cap">Since ${fmt.date(J.status.start)}${J.status.end ? " until " + fmt.date(J.status.end) : ""} · set by ${esc(J.status.source || "you")}</p>` : `<p class="cap">Set by you or source data only</p>`}
      <div class="edit-row">${editBtn("status-set", undefined, "Set status")}${J.status && J.status.id && !J.status.end && J.status.status !== "normal" ? editBtn("status-end", J.status.id, "End today") : ""}</div>
      <div class="list">${J.status_history.slice(0, 6).map(s => `<div class="li"><div class="grow small">${esc(fmt.sport(s.status))}</div><div class="r small">${fmt.date(s.start)}${s.end ? "–" + fmt.date(s.end) : ""}</div></div>`).join("")}</div></div>
      <div class="card"><div class="spread"><h3 style="margin:0">New entry</h3>${editBtn("habit-add", undefined, "New habit")}</div><form class="form" id="journal-form" style="margin-top:8px"><div class="grid g2"><label>Date <input name="date" type="date" value="${D.meta.build_date}" required></label><label>Habit <select name="habit"><option value="">—</option>${J.habits.map(h => `<option value="${esc(h.id)}">${esc(h.name)}</option>`).join("")}</select></label><label>Type <select name="type">${["mood", "hydration", "sunlight", "screen_time", "caffeine", "alcohol", "symptom", "travel", "sickness", "supplement", "note", "habit"].map(t => `<option value="${t}">${esc(fmt.sport(t))}</option>`).join("")}</select></label><label>Value <input name="value" inputmode="decimal"></label></div><label>Note <input name="text"></label><button class="btn" ${AG.online ? "" : "disabled"}>Add</button>${offlineNote()}</form></div>
      ${J.cycle.enabled ? `<div class="card"><h3>Cycle tracking</h3>${J.cycle.latest ? `<p class="small">Latest log ${fmt.date(J.cycle.latest.date)}${J.cycle.latest.phase ? " · " + esc(J.cycle.latest.phase) : ""}</p>` : `<p class="small muted">No logs yet</p>`}<p class="cap">From your logs or HealthKit only; no predictions shown as fact.</p></div>` : ""}</div>
      <div class="card"><h3>Recent entries</h3>${J.entries.length ? `<div class="list">${J.entries.slice(0, 40).map(e => `<div class="li"><div class="grow"><div class="t small">${esc(fmt.sport(e.type))}${e.habit_id ? " · " + esc((J.habits.find(h => h.id === e.habit_id) || {}).name || e.habit_id) : ""}</div><div class="s">${fmt.date(e.date)}${e.text ? " · " + esc(e.text) : ""}</div></div><div class="r small">${isNum(e.value) ? fmt.n(e.value, e.value % 1 ? 1 : 0) + " " + esc(e.unit || "") : ""}</div>${AG.online && e.kind === "user_entered" ? `<button type="button" class="icon-btn" data-open="journal-del" data-arg="${esc(e.id)}" aria-label="Delete entry">×</button>` : ""}</div>`).join("")}</div>` : empty("No journal entries yet")}</div></div>`;
  },
  after() {
    const f = $("#journal-form");
    if (f) f.onsubmit = async e => { e.preventDefault(); try { await save("POST", "entries/journal.entries", { date: f.date.value, type: f.habit.value ? "habit" : f.type.value, habit_id: f.habit.value || null, value: f.value.value ? +f.value.value : (f.habit.value ? 1 : null), text: f.text.value || null }, "Entry saved"); } catch (err) { /* shown */ } };
  },
};

AG.screens.more = {
  title: "More",
  render() {
    const tabs = mobileTabs();
    const rest = DESTS.filter(d => !tabs.includes(d.id));
    const extra = [{ id: "timeline", label: "Timeline", icon: "timeline" }, { id: "journal", label: "Journal", icon: "timeline" }, { id: "widgets", label: "Widgets", icon: "today" }];
    return `<div class="more-grid">${rest.concat(extra).map(d => `<a href="#/${d.id}">${icon(d.icon)}<span>${esc(d.label)}</span></a>`).join("")}</div>`;
  },
};
