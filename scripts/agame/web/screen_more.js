/* Routes, Goals, Coach, Profile */
"use strict";

AG.screens.routes = {
  title: "Routes",
  render() {
    const tab = chipVal("rt-tab", "library");
    const body = { library: rtLibrary, heatmap: rtHeatmap, segments: rtSegments, builder: rtBuilder }[tab]();
    return `${tabs("rt-tab", [["library", "Library"], ["heatmap", "Heatmap"], ["segments", "Segments"], ["builder", "Route builder"]], tab)}${body}`;
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
  const sel = (name, opts, cur) => `<select data-select="${name}" aria-label="${esc(opts[0][1])}">${opts.map(([v, l]) => `<option value="${v}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  return `<div class="toolbar" style="margin-bottom:16px">${chips("rt-filter", [["all", "All"], ["fav", "Favorites"], ["offline", "Offline"], ["short", "Under 8 km"], ["long", "12 km+"], ["hilly", "Hilliest"]], f)}
    ${lib.some(r => r.surface) ? sel("rt-surface", [["any", "Any surface"], ["paved", "Mostly paved"], ["unpaved", "Mostly unpaved"]], sf) : ""}
    ${diffs.length ? sel("rt-diff", [["any", "Any difficulty"]].concat(diffs.map(d => [d, fmt.sport(d)])), df) : ""}</div><div class="cols c21"><div class="stack">
    <div class="card"><div class="list">${rows.map(r => `<a class="li" href="#/route/${encodeURIComponent(r.id)}">${routeThumb(r.lines)}<div class="grow"><div class="t">${esc(r.name || r.id)}${r.favorite ? `<span class="fav">${icon("star-filled")}</span>` : ""}</div>
      <div class="s">${fmt.dist(r.distance_m)} · ${fmt.elev(r.elevation_gain_m)}${r.est_time_s ? " · " + fmt.mins(r.est_time_s) : ""}</div><div class="s">${r.times_run} runs${r.difficulty ? " · " + esc(fmt.sport(r.difficulty)) : ""}${r.offline ? " · Offline" : ""}</div></div></a>`).join("") || empty("No routes match")}</div></div></div>
    <div class="stack"><div class="card">${cardHead("Made for you", "", "Picked only from your own route library, by target distance, surface and how recently you ran them.")}${rec.length ? `<div class="list">${rec.map(r => `<a class="li" href="#/route/${encodeURIComponent(r.route_id)}"><div class="grow"><div class="t">${esc(r.name)}</div><div class="s">${esc(r.why)}</div></div><div class="r small">${fmt.dist(r.distance_m)}</div></a>`).join("")}</div>` : empty(STR.noData)}</div></div></div>`;
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
    const tools = AG.online ? `<div class="actions"><button class="btn sm secondary" data-route-flag="favorite" data-val="${x.favorite ? 0 : 1}">${icon(x.favorite ? "star-filled" : "star")}${x.favorite ? "Favorite" : "Add to favorites"}</button><button class="btn sm secondary" data-route-flag="offline" data-val="${x.offline ? 0 : 1}">${x.offline ? "Saved offline ✓" : "Save offline"}</button>${x.imported ? `<button class="btn sm danger" data-open="route-del" data-arg="${esc(x.id)}">Delete</button>` : ""}</div>` : "";
    return `<div class="cols"><div class="stack"><div class="card">${mapSvg(x.lines, { label: x.name, noEnds: false })}${tools}</div>
      <div class="card">${cardHead("Overview", "", x.est_basis ? "Estimated time: " + esc(x.est_basis) + "." : "")}<div class="stats-grid s4">${stat("Distance", fmt.dist(x.distance_m))}${stat("Elevation", fmt.elev(x.elevation_gain_m))}${stat("Est. time", x.est_time_s ? fmt.mins(x.est_time_s) : "—")}${stat("Runs", x.times_run)}</div>
      ${x.surface ? `<div style="margin-top:10px">${surfaceBar(x.surface)}</div>` : ""}</div></div>
      <div class="stack">${x.profile ? `<div class="card">${cardHead("Elevation profile")}${chart({ id: "rt-prof", type: "profile", label: "Elevation profile", points: x.profile, h: 140 })}</div>` : ""}
      <div class="card">${cardHead("Your efforts")}${x.efforts.length ? `<table class="tbl"><tr><th>Date</th><th class="r">Time</th><th class="r">Pace</th></tr>${x.efforts.slice().reverse().map(e => `<tr><td><a href="#/activity/${encodeURIComponent(e.workout_id)}">${fmt.date(e.date, { day: "numeric", month: "short", year: "numeric" })}</a></td><td class="r">${fmt.dur(e.time_s)}</td><td class="r">${fmt.pace(e.pace_s_per_km)}</td></tr>`).join("")}</table>` : empty("Not run yet")}</div></div></div>`;
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
  return `<div class="stack"><div class="toolbar">${chips("hm-fam", [["all", "All sports"], ["run", "Run"], ["ride", "Ride"], ["walk", "Walk"]], fam)}${seg("hm-night", [["all", "Day & night"], ["night", "Night"]], night)}${seg("hm-range", [["all", "All time"], ["365", "Year"], ["90", "90 days"]], rng)}</div>
    <div class="card">${cardHead("Heatmap", v ? `<span class="small muted">${v.activities} activities</span>` : "", "Built from your own GPS traces with privacy zones applied. Night means the activity started between local sunset and sunrise.")}${svg}</div></div>`;
}
function rtSegments() {
  const S = D.routes.segments;
  if (!S.length) return empty("No segments yet", "Define segments on your routes in routes.geojson (kind: segment)");
  return `<div class="stack">${S.map(s => `<div class="card">${cardHead(esc(s.name), `<span class="small muted">${fmt.dist(s.distance_m)} · ${fmt.elev(s.elevation_gain_m)}</span>`)}
    <div class="cols"><div>${mapSvg(s.lines, { label: s.name, h: 140 })}</div><div>
    <div class="stats-grid s3">${stat("PR", s.pr ? fmt.dur(s.pr.time_s) : "—")}${stat("Efforts", s.count)}${stat("Last", s.efforts.length ? fmt.dur(s.efforts[s.efforts.length - 1].time_s) : "—")}</div>
    ${s.efforts.length > 1 ? chart({ id: "seg-" + s.id, label: "Segment times", x: s.efforts.map(e => e.date), h: 120, invertY: true, series: [{ name: "Time", color: "var(--accent)", values: s.efforts.map(e => e.time_s), dots: true }], fmtX: d => fmt.date(d), fmtY: v => fmt.dur(v) }) : ""}
    ${s.leaderboard_status === "connected" ? `<div class="list" style="margin-top:8px"><div class="li"><div class="grow"><div class="t">Leaderboard</div><div class="s">${s.leaderboard.length} efforts</div></div></div></div>` : ""}</div></div></div>`).join("")}</div>`;
}
function rtBuilder() {
  const tiles = D.routes.tiles;
  return `<div class="cols"><div class="card">${cardHead("Import a route")}<form class="form" onsubmit="return false"><label>Name <input id="route-name" placeholder="Uses the file name if empty"></label><label>GPX or GeoJSON file <input type="file" id="route-file" accept=".gpx,.geojson,.json" ${AG.online ? "" : "disabled"}></label></form></div>
    <div class="card">${cardHead("Draw a route")}${tiles ? `<p class="small" style="margin:0">Add points on the map. They snap to your own traces.</p>` : empty(STR.noMap, "Set a map tile URL in Profile to draw routes. Importing works without one.")}</div></div>`;
}

/* ---------------- Goals ---------------- */
AG.screens.goals = {
  title: "Goals",
  headRight() { return AG.online ? `<button class="btn sm" data-open="goal-new">New goal</button>` : ""; },
  render() {
    const G = D.goals;
    return `<div class="cols"><div class="stack">${sectionTitle("Active", `<span class="small muted">${G.length} ${G.length === 1 ? "goal" : "goals"}</span>`)}<div class="card">${G.length ? G.map(g => goalRow(g, { edit: true })).join("") : empty(STR.noGoals, "Add one with New goal")}</div></div>
      <div class="stack">${sectionTitle("Consistency")}${consistencyCard()}</div></div>`;
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
    const win = ["30", "90"].includes(chipVal("hh-win", "90")) ? chipVal("hh-win", "90") : "90";
    const r = C.recommendation;
    const threads = (C.threads || []).slice(-1)[0];
    const first = (D.profile.display_name || "").split(" ")[0];
    const facts = r.factors.slice(0, 4).map(factorRow).join("");
    return `<div class="cols c21"><div class="stack">
      <div class="card coach-card"><div class="coach-hero"><div class="orb" aria-hidden="true"></div><div class="coach-hi">${first ? "Morning, " + esc(first) : "Your coach"}</div><div class="small muted">${fmt.dateLong(D.meta.build_date)}</div></div><div class="chat" id="chat">
        <div class="msg coach">${esc(D.today.coach_line)}</div>
        ${facts ? `<div class="msg coach card-msg"><div class="msg-k">What I looked at</div><div class="list">${facts}</div></div>` : ""}
        ${threads ? threads.messages.slice(-6).map(m => `<div class="msg ${m.role === "user" ? "user" : "coach"}">${esc(m.text)}</div>`).join("") : ""}</div>
      ${AG.llm ? `<div class="ask-chips">${C.suggestions.map(s => `<button class="chip" data-ask="${esc(s)}">${icon("sparkles")}${esc(s)}</button>`).join("")}</div>
      <form class="composer" data-coach-form><label class="sr" for="coach-q">Ask your coach</label><div class="composer-row"><textarea id="coach-q" name="q" rows="1" placeholder="${AG.llm ? "Ask anything about your data" : esc(STR.noCoachLLM)}"></textarea><button class="send" aria-label="Ask">${icon("up")}</button></div>
        <div class="composer-opts">${seg("coach-mode", [["fast", "Fast"], ["thinking", "Thinking"], ["adaptive", "Adaptive"]], mode)}<button type="button" class="chip" data-chip="coach-ghost" data-val="${ghost ? "off" : "on"}" aria-pressed="${ghost}" title="Ghost mode: nothing is saved or logged">Ghost</button></div></form>` : ""}</div>
      <div class="card">${cardHead("Helping & hurting", seg("hh-win", [["30", "30d"], ["90", "90d"]], win), "Links between your habits and next-morning recovery. A factor shows only once there are enough days to be sure.")}${helpingList(win)}</div></div>
      <div class="stack">${AG.llm ? `<div class="card">${cardHead("Personality", AG.online ? `<button class="link" data-open="edit-coach">Save as default</button>` : "", "Changes the tone only. The facts stay the same.")}${chips("coach-pers", [["data_nerd", "Data Nerd"], ["guardian", "Guardian"], ["friend", "Friend"], ["commander", "Commander"]], chipVal("coach-pers", (C.settings || {}).personality || "data_nerd"))}</div>` : ""}
      <div class="card">${cardHead("Check-ins", editBtn("checkin-edit", "", "Add"), `${esc(AGENT)} delivers these on schedule.`)}${C.checkins.length ? `<div class="list">${C.checkins.map(c => `<${AG.online ? `button type="button" data-open="checkin-edit" data-arg="${esc(c.id)}"` : "div"} class="li"><div class="grow"><div class="t">${esc(fmt.sport(c.type))}${c.text ? " · " + esc(c.text) : ""}</div><div class="s">${esc(c.time)} · ${esc(daysLabel(c.days))}</div></div>${c.enabled ? "" : badge("Off", "est")}</${AG.online ? "button" : "div"}>`).join("")}</div>` : empty("No check-ins scheduled")}</div>
      <div class="card">${cardHead("Memory", editBtn("memory-edit", "", "Add"), `Preferences, goals and corrections Coach keeps. Each one can be edited or deleted, with history. Last tidied ${C.last_maintenance ? fmt.date(C.last_maintenance) : "never"}.`)}${C.memory.length ? `<div class="list">${C.memory.map(m => `<${AG.online ? `button type="button" data-open="memory-edit" data-arg="${esc(m.id)}"` : "div"} class="li"><div class="grow"><div class="t" style="white-space:normal">${esc(m.text)}</div><div class="s">${esc(fmt.sport(m.type))}</div></div></${AG.online ? "button" : "div"}>`).join("")}</div>` : empty("Nothing remembered yet")}</div></div></div>`;
  },
};
function daysLabel(d) {
  const all = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  if (!d || !d.length || d.length === 7) return "Every day";
  if (d.length === 5 && all.slice(0, 5).every(x => d.includes(x))) return "Weekdays";
  return d.map(x => fmt.sport(x)).join(", ");
}
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
/* Settings row (Bevel): coloured icon tile, title and detail, value on the right, chevron when it opens something. */
function srow(o) {
  const tag = o.href ? `a href="${o.href}"` : o.open ? `button type="button" data-open="${esc(o.open)}"${o.arg !== undefined ? ` data-arg="${esc(o.arg)}"` : ""}` : "div";
  return `<${tag} class="srow-i ${o.href || o.open ? "tap" : ""}">${o.icon ? `<span class="sq" style="--c:${o.color || "var(--text-2)"}">${icon(o.icon)}</span>` : ""}<div class="grow"><div class="t"${o.danger ? ` style="color:var(--bad)"` : ""}>${o.title}</div>${o.sub ? `<div class="s">${o.sub}</div>` : ""}</div>${o.right ? `<span class="rv">${o.right}</span>` : ""}${o.href || o.open ? `<span class="chev-r">${icon("next")}</span>` : ""}</${tag.split(" ")[0]}>`;
}
const editLink = (sheet, label = "Edit") => AG.online ? `<button class="link" data-open="${esc(sheet)}">${esc(label)}</button>` : "";
AG.screens.profile = {
  title: "Profile",
  render() {
    const p = D.profile;
    const ph = p.physiology || {};
    const tg = p.targets || {};
    const ds = D.meta.data_status;
    const integ = p.integrations || {};
    const theme = uiGet("theme", (p.ui || {}).theme || "system");
    const name = p.display_name || "Athlete";
    const initials = name.split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
    const notSet = `<span class="faint">Not set</span>`;
    const pm = (title, ic, color, o, f, note) => srow({ icon: ic, color, title, sub: o ? [fmt.sport(o.method || ""), o.date ? fmt.date(o.date, { day: "numeric", month: "short", year: "numeric" }) : ""].filter(Boolean).map(esc).join(" · ") : esc(note || ""), right: o ? f(o.value) : notSet });
    const tv = (k, f) => isNum(tg[k]) ? f(tg[k]) : notSet;
    const conn = v => v ? `<span class="st ok"><i class="live-dot sm"></i>Connected</span>` : `<span class="faint">Not connected</span>`;
    const ident = `<div class="card ident"><span class="avatar">${esc(initials)}</span><div class="grow"><div class="ident-n">${esc(name)}</div><div class="small muted">${esc(TZ)} · ${IMPERIAL ? "Imperial" : "Metric"} · week starts ${esc(fmt.sport(D.meta.week_start).toLowerCase())}</div></div>${AG.online ? `<div class="row">${editBtn("edit-athlete", undefined, "Edit")}${editBtn("edit-locale", undefined, "Units")}</div>` : ""}</div>`;
    const physio = `${sectionTitle("Physiology", `<span class="row">${editLink("edit-physiology")}${info("Physiology", `${esc(fmt.sport(String((p.zones_config || {}).model || "5zone").replace(/^(\d)zone$/, "$1 zones")))}. No age-based HR max is ever used. Threshold auto-accept is ${p.auto_accept_thresholds ? "on" : "off"}.`)}</span>`)}<div class="card list-card">
      ${pm("HR max", "heart", "var(--bad)", ph.hr_max, v => v + " bpm")}${pm("Resting HR", "activities", "var(--protein)", ph.hr_rest, v => v + " bpm", "Using your 14-day HealthKit median")}
      ${pm("LTHR", "bolt", "var(--warn)", ph.lthr, v => v + " bpm")}${pm("Threshold pace", "run", "var(--run)", ph.threshold_pace_s_per_km, v => fmt.pace(v))}
      ${pm("FTP", "ride", "var(--ride)", ph.ftp_w, v => v + " W")}${pm("Sleep need", "sleep", "var(--sleep)", ph.sleep_need_base_min, v => fmt.hm(v))}</div>`;
    const targets = `${sectionTitle("Daily targets", `<span class="row">${editLink("edit-targets")}${tg.caffeine_cutoff ? info("Daily targets", `Caffeine cutoff ${esc(tg.caffeine_cutoff)}. Wake time ${esc(tg.wake_time || "not set")}.`) : ""}</span>`)}<div class="card list-card two">
      ${srow({ icon: "meal", color: "var(--protein)", title: "Protein", right: tv("protein_g", v => fmt.n(v) + " g") })}${srow({ icon: "flame", color: "var(--strain)", title: "Calories", right: tv("kcal", v => fmt.n(v) + " kcal") })}
      ${srow({ icon: "nutrition", color: "var(--ok)", title: "Fiber", right: tv("fiber_g", v => fmt.n(v) + " g") })}${srow({ icon: "nutrition", color: "var(--walk)", title: "Vegetables", right: tv("vegetables_g", v => fmt.n(v) + " g") })}
      ${srow({ icon: "droplet", color: "var(--info)", title: "Water", right: tv("water_ml", v => fmt.n(v) + " ml") })}${srow({ icon: "coffee", color: "var(--carbs)", title: "Caffeine max", right: tv("caffeine_mg_max", v => fmt.n(v) + " mg") })}
      ${srow({ icon: "walk", color: "var(--recovery)", title: "Steps", right: tv("steps", v => fmt.n(v)) })}${srow({ icon: "sleep", color: "var(--sleep)", title: "Sleep", right: tv("sleep_min", v => fmt.hm(v)) })}</div>`;
    const sched = `${sectionTitle("Weekly template", editLink("edit-schedule"))}<div class="card list-card">${(p.schedule || []).length ? p.schedule.map(x => srow({ title: esc(fmt.sport(x.weekday)), right: `${esc(fmt.sport(x.intent))}${x.duration_s ? `<span class="muted"> · ${fmt.mins(x.duration_s)}</span>` : ""}` })).join("") : empty("No weekly template", "Add one with Edit")}</div>`;
    const settings = `${sectionTitle("Settings")}<div class="card list-card">
      ${srow({ icon: "palette", color: "var(--sleep)", title: "Appearance", right: seg("theme", [["system", "System"], ["dark", "Dark"], ["light", "Light"]], theme) })}
      ${srow({ icon: "apps", color: "var(--accent)", title: "Phone tabs", sub: esc(mobileTabs().map(t => fmt.sport(t)).join(", ")), open: AG.online ? "edit-appearance" : null, right: AG.online ? "" : "" })}
      ${srow({ icon: "layout", color: "var(--info)", title: "Widgets", href: "#/widgets" })}
      ${srow({ icon: "note", color: "var(--warn)", title: "Journal & status", href: "#/journal" })}
      ${srow({ icon: "coach", color: "var(--sleep-2)", title: "Coach", sub: `${esc(fmt.sport((p.coach || {}).personality || "data_nerd"))} · health records ${(p.coach || {}).include_health_records ? "shared" : "not shared"}`, open: AG.online ? "edit-coach" : null })}
      ${srow({ icon: "shield", color: "var(--ok)", title: "Privacy", sub: `Trim ${fmt.n((p.privacy || {}).hide_start_end_m)} m · ${((p.privacy || {}).zones || []).length} privacy zones`, open: AG.online ? "edit-privacy" : null })}
      ${srow({ icon: "apps", color: "var(--strength)", title: "Modules", sub: `${Object.values(p.modules || {}).filter(Boolean).length} of ${Object.keys(p.modules || {}).length} on`, open: AG.online ? "edit-modules" : null })}</div>`;
    const data = `${sectionTitle("Data")}<div class="card list-card">
      ${srow({ icon: "cloud-check", color: "var(--ok)", title: "Freshness", sub: `Last sync ${ds.last_sync ? fmt.dt(ds.last_sync) : "never"} · ${esc(statusLabel(ds.overall))}`, open: "data-status" })}
      ${AG.online ? srow({ icon: "apple", color: "var(--bad)", title: "Import Apple Health export", open: "health-export" }) + srow({ icon: "download", color: "var(--info)", title: "Export my data", href: "api/export" }) + srow({ icon: "history", color: "var(--warn)", title: "Edit history & undo", open: "history" }) + srow({ icon: "trash", color: "var(--bad)", title: "Delete my entries", open: "delete-all", danger: true }) : ""}</div>`;
    const integs = `${sectionTitle("Integrations", info("Integrations", "No Strava or Bevel data is ever imported. These statuses reflect your configuration."))}<div class="card list-card">
      ${srow({ icon: "heart", color: "var(--bad)", title: `Apple Health via ${esc(AGENT)}`, sub: ds.last_sync ? "Last import " + fmt.dt(ds.last_sync) : "No import yet", right: ds.last_sync ? conn(true) : `<span class="faint">Waiting</span>` })}
      ${[["Map tiles", "routes", integ.map_tiles_url], ["Nutrition source", "nutrition", integ.nutrition_source], ["Calendar", "calendar", integ.calendar_source], ["Food database", "database", integ.food_database], ["Photo recognition", "cpu", integ.vision_service], ["Coach chat", "coach", AG.llm], ["Companion app", "watch", integ.companion_app]].filter(([, , v]) => v).map(([l, ic, v]) => srow({ icon: ic, color: "var(--text-2)", title: esc(l), right: conn(v) })).join("")}
      ${integ.companion_app ? srow({ icon: "bell", color: "var(--text-2)", title: "Smart alarm", sub: (p.smart_alarm || {}).enabled ? "On" : "Off", open: AG.online ? "edit-companion" : null }) + srow({ icon: "share2", color: "var(--text-2)", title: "Beacon live sharing", sub: `${Array.isArray((p.beacon || {}).contacts) ? p.beacon.contacts.length : ((p.beacon || {}).contacts || 0)} contacts`, open: AG.online ? "edit-companion" : null }) : ""}</div>`;
    return `<div class="flow2"><div class="flow-a"><div class="o" style="order:0">${ident}</div><div class="o" style="order:1">${physio}</div><div class="o" style="order:2">${targets}</div><div class="o" style="order:5">${sched}</div></div>
      <div class="flow-b"><div class="o" style="order:3">${settings}</div><div class="o" style="order:4">${data}</div><div class="o" style="order:6">${integs}</div>
      <div class="o" style="order:7"><p class="small faint" style="margin:8px 4px 0">AGame ${esc(D.meta.version)} · build ${esc(D.meta.build_date)} · Fitness information, not medical advice.</p></div></div></div>`;
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
  scores: ["Scores", w => `<div class="rings widget-rings">${ring("strain", w.rings.strain, { label: "Strain" })}${ring("recovery", w.rings.recovery, { label: "Recovery" })}${ring("sleep", w.rings.sleep, { label: "Sleep" })}</div>`],
  recovery: ["Recovery", w => `<b style="font-size:28px">${val(w.rings.recovery, 0, "%")}</b>${stLine(w.rings.recovery)}`],
  sleep: ["Sleep", w => `<b style="font-size:28px">${val(w.rings.sleep, 0, "%")}</b>${stLine(w.rings.sleep)}`],
  strain: ["Strain", w => `<b style="font-size:28px">${val(w.rings.strain, 0, "%")}</b><span class="cap">so far today</span>`],
  energy: ["Energy", w => `<b style="font-size:28px">${w.energy ? w.energy.current + "%" : "—"}</b><div class="energy"><i style="width:${w.energy ? w.energy.current : 0}%"></i></div>`],
  protein: ["Protein", w => `<b style="font-size:28px">${w.protein && isNum(w.protein.v) ? fmt.n(w.protein.v) + " g" : "—"}</b>${w.protein_target ? bar(w.protein && isNum(w.protein.v) ? w.protein.v / w.protein_target * 100 : 0, "var(--protein)") : `<span class="cap">${STR.noNutrition}</span>`}`],
  hydration: ["Hydration", w => `<b style="font-size:28px">${isNum(w.water_ml) ? fmt.n(w.water_ml) + " ml" : "—"}</b>${isNum(w.water_target) ? bar(isNum(w.water_ml) ? w.water_ml / w.water_target * 100 : 0, "var(--info)") : ""}`],
  plan: ["Today's plan", w => w.plan.length ? `<b>${esc(w.plan[0].title || w.plan[0].type)}</b><span class="cap">${w.plan[0].duration_s ? fmt.mins(w.plan[0].duration_s) : ""}</span>` : `<span class="small muted">${STR.noPlan}</span>`],
  weight: ["Weight", w => `<b style="font-size:28px">${w.weight && isNum(w.weight.v) ? fmt.kg(w.weight.v) : "—"}</b><span class="cap">${w.weight_goal ? "goal " + fmt.kg(w.weight_goal.target) : fmt.wUnit()}</span>`],
  load: ["Weekly load", w => `<b style="font-size:28px">${isNum(w.weekly_load) ? fmt.n(w.weekly_load) : "—"}</b><span class="cap">${w.weekly_band ? "range " + fmt.n(w.weekly_band.low) + "–" + fmt.n(w.weekly_band.high) : ""}</span>`],
  goal: ["Goal", w => w.goal ? `<b class="small">${esc(w.goal.title)}</b>${goalStatusBadge(w.goal.status_label)}` : `<span class="small muted">${STR.noGoals}</span>`],
};
function widgetCard(key, pinBtn) {
  const [title, render] = WIDGETS[key];
  const pinned = ((P.ui || {}).today_widgets || []).includes(key);
  return `<div class="card widget"><div class="spread"><span class="small muted" style="font-weight:600">${esc(title)}</span>${pinBtn && AG.online ? `<button type="button" class="icon-btn" data-pin="${key}" aria-pressed="${pinned}" aria-label="${pinned ? "Unpin from" : "Pin to"} Today" title="${pinned ? "Unpin from" : "Pin to"} Today">${icon(pinned ? "star-filled" : "star")}</button>` : ""}</div>${render(D.widgets)}</div>`;
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
    return `<div class="page-head"><span class="small muted">${w.as_of ? "As of " + fmt.dt(w.as_of) : ""}</span>${info("Widgets", "Star a widget to pin it to a row at the top of Today on desktop. Home-screen widgets need a native companion app. Health records never appear in widgets.")}</div><div class="grid g4">${Object.keys(WIDGETS).map(k => widgetCard(k, true)).join("")}</div>`;
  },
};

AG.screens.journal = {
  title: "Journal", parent: "#/profile", nav: "profile",
  render() {
    const J = D.journal;
    const end = D.meta.build_date;
    const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(end + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() - 6 + i); return d.toISOString().slice(0, 10); });
    const sel = days.includes(chipVal("jr-day", end)) ? chipVal("jr-day", end) : end;
    const byDay = d => J.entries.filter(e => e.date === d);
    const strip = `<div class="jr-strip" role="group" aria-label="Day">${days.map(d => { const n = byDay(d).length; return `<button data-chip="jr-day" data-val="${d}" aria-pressed="${d === sel}" class="jr-day"><span class="wk-dow">${fmt.dow(d)}</span><span class="wk-num">${fmt.date(d, { day: "numeric" })}</span><span class="jr-dot ${n ? "on" : ""}">${n ? icon("check") : ""}</span></button>`; }).join("")}</div>`;
    const JI = { mood: ["mood", "var(--warn)"], hydration: ["droplet", "var(--info)"], caffeine: ["coffee", "var(--carbs)"], alcohol: ["glass", "var(--protein)"], sunlight: ["sun", "var(--warn)"], screen_time: ["screen", "var(--text-2)"],
      symptom: ["alert", "var(--bad)"], travel: ["plane", "var(--ride)"], sickness: ["thermometer", "var(--bad)"], supplement: ["pill", "var(--ok)"], note: ["note", "var(--text-2)"], habit: ["check", "var(--recovery)"] };
    const valTxt = e => e.type === "mood" && isNum(e.value) ? `${fmt.n(e.value)} of 5` : e.type === "habit" ? "Done" : e.type === "alcohol" && isNum(e.value) ? `${fmt.n(e.value)} drink${e.value === 1 ? "" : "s"}` : isNum(e.value) ? `${fmt.n(e.value, e.value % 1 ? 1 : 0)}${e.unit ? " " + esc(e.unit) : ""}` : "";
    const entries = byDay(sel);
    const rows = entries.map(e => { const [ic, col] = JI[e.type] || ["note", "var(--text-2)"]; const habit = e.habit_id ? (J.habits.find(h => h.id === e.habit_id) || {}).name || e.habit_id : null;
      return srow({ icon: ic, color: col, title: esc(habit || fmt.sport(e.type)), sub: e.text ? esc(e.text) : "", right: valTxt(e) + (AG.online && e.kind === "user_entered" ? ` <button type="button" class="icon-btn" data-open="journal-del" data-arg="${esc(e.id)}" aria-label="Delete entry">${icon("x")}</button>` : "") }); });
    const missingHabits = J.habits.filter(h => !entries.some(e => e.habit_id === h.id)).map(h => srow({ icon: "check", color: "var(--text-3)", title: esc(h.name), right: `<span class="faint">Not logged</span>` }));
    const dayCard = `${sectionTitle(sel === end ? "Today" : fmt.date(sel, { weekday: "long", day: "numeric", month: "long" }), `<span class="small muted">${entries.length} ${entries.length === 1 ? "entry" : "entries"}</span>`)}<div class="card list-card">${rows.concat(missingHabits).join("") || `<p class="small muted" style="margin:14px 0">Nothing logged this day</p>`}</div>`;
    const st = J.status;
    const status = `${sectionTitle("Activity status", `<span class="row">${editBtn("status-set", undefined, "Set")}${st && st.id && !st.end && st.status !== "normal" ? editBtn("status-end", st.id, "End today") : ""}${info("Activity status", "Set only by you or by source data. Sick, travel and injured days change how your plan adapts.")}</span>`)}<div class="card list-card">
      ${srow({ icon: "today", color: st && st.status !== "normal" ? "var(--warn)" : "var(--ok)", title: st ? esc(fmt.sport(st.status)) : "Normal", sub: st ? `Since ${fmt.date(st.start)}${st.end ? " until " + fmt.date(st.end) : ""} · set by ${esc(st.source || "you")}` : "Nothing unusual right now" })}
      ${J.status_history.slice(0, 6).map(x => srow({ title: esc(fmt.sport(x.status)), sub: x.note ? esc(x.note) : "", right: `<span class="muted">${fmt.date(x.start)}${x.end ? "–" + fmt.date(x.end) : ""}</span>` })).join("")}</div>`;
    const form = AG.online ? `${sectionTitle("New entry", editBtn("habit-add", undefined, "New habit"))}<div class="card"><form class="form" id="journal-form"><div class="grid g2"><label>Date <input name="date" type="date" value="${sel}" required></label><label>Habit <select name="habit"><option value="">—</option>${J.habits.map(h => `<option value="${esc(h.id)}">${esc(h.name)}</option>`).join("")}</select></label><label>Type <select name="type">${["mood", "hydration", "sunlight", "screen_time", "caffeine", "alcohol", "symptom", "travel", "sickness", "supplement", "note", "habit"].map(t => `<option value="${t}">${esc(fmt.sport(t))}</option>`).join("")}</select></label><label>Value <input name="value" inputmode="decimal"></label></div><label>Note <input name="text"></label><div class="actions" style="margin-top:0"><button class="btn">Add</button></div></form></div>` : "";
    const cycle = J.cycle.enabled ? `${sectionTitle("Cycle tracking", info("Cycle tracking", "From your logs or HealthKit only. Predictions are never shown as fact."))}<div class="card">${J.cycle.latest ? `<p class="small" style="margin:0">Latest log ${fmt.date(J.cycle.latest.date)}${J.cycle.latest.phase ? " · " + esc(J.cycle.latest.phase) : ""}</p>` : `<p class="small muted" style="margin:0">No logs yet</p>`}</div>` : "";
    return `${strip}<div class="flow2"><div class="flow-a"><div class="o" style="order:0">${dayCard}</div></div><div class="flow-b"><div class="o" style="order:1">${status}</div>${form ? `<div class="o" style="order:2">${form}</div>` : ""}${cycle ? `<div class="o" style="order:3">${cycle}</div>` : ""}</div></div>`;
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
