/* AGame core: data access, formatting, router, sheets, tooltips, API. No metric formulas live here;
   every number comes from computed.json (window.AG_DATA). */
"use strict";
const AG = { screens: {}, charts: {}, ui: {}, online: false };
const D = JSON.parse(document.getElementById("agame-data").textContent);
const P = D.profile || {};
const TZ = D.meta.timezone || "Africa/Kigali";
const IMPERIAL = D.meta.units === "imperial";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

/* ---------- persistence (per-viewer conveniences only) ---------- */
const store = {
  get(k, d) { try { const v = localStorage.getItem("agame:" + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("agame:" + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
};
AG.ui = store.get("ui", {});
function uiGet(k, d) { return AG.ui[k] === undefined ? d : AG.ui[k]; }
function uiSet(k, v) { AG.ui[k] = v; store.set("ui", AG.ui); }

/* ---------- escaping ---------- */
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const isNum = v => typeof v === "number" && isFinite(v);

/* ---------- formatting ---------- */
const fmt = {
  n(v, d = 0) { return isNum(v) ? v.toLocaleString("en-GB", { minimumFractionDigits: d, maximumFractionDigits: d }) : "—"; },
  signed(v, d = 0, unit = "") { if (!isNum(v)) return "—"; const s = v > 0 ? "+" : v < 0 ? "−" : "±"; return s + fmt.n(Math.abs(v), d) + unit; },
  dist(m, d) {
    if (!isNum(m)) return "—";
    if (IMPERIAL) { const mi = m / 1609.344; return fmt.n(mi, d === undefined ? (mi < 10 ? 2 : 1) : d) + " mi"; }
    const km = m / 1000; return fmt.n(km, d === undefined ? (km < 10 ? 2 : 1) : d) + " km";
  },
  distNum(m, d = 1) { return isNum(m) ? fmt.n(IMPERIAL ? m / 1609.344 : m / 1000, d) : "—"; },
  distUnit() { return IMPERIAL ? "mi" : "km"; },
  pace(sPerKm, unit = true) {
    if (!isNum(sPerKm) || sPerKm <= 0) return "—";
    let s = IMPERIAL ? sPerKm * 1.609344 : sPerKm; s = Math.round(s);
    return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0") + (unit ? (IMPERIAL ? " /mi" : " /km") : "");
  },
  paceUnit() { return IMPERIAL ? "/mi" : "/km"; },
  dur(s) {
    if (!isNum(s)) return "—"; s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h ? `${h}:${String(m).padStart(2, "0")}:${String(x).padStart(2, "0")}` : `${m}:${String(x).padStart(2, "0")}`;
  },
  hm(min) {
    if (!isNum(min)) return "—"; const m = Math.round(min);
    return m >= 60 ? `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m` : `${m}m`;
  },
  mins(s) { return isNum(s) ? fmt.hm(s / 60) : "—"; },
  elev(m) { return isNum(m) ? (IMPERIAL ? fmt.n(m * 3.28084) + " ft" : fmt.n(m) + " m") : "—"; },
  kg(v, d = 1) { return isNum(v) ? (IMPERIAL ? fmt.n(v * 2.20462, d) + " lb" : fmt.n(v, d) + " kg") : "—"; },
  kgNum(v, d = 1) { return isNum(v) ? fmt.n(IMPERIAL ? v * 2.20462 : v, d) : "—"; },
  wUnit() { return IMPERIAL ? "lb" : "kg"; },
  temp(c) { return isNum(c) ? (IMPERIAL ? fmt.n(c * 9 / 5 + 32) + "°F" : fmt.n(c) + "°C") : "—"; },
  pct(v) { return isNum(v) ? fmt.n(v) + "%" : "—"; },
  date(iso, o) {
    if (!iso) return "—";
    const d = iso.length === 10 ? new Date(iso + "T12:00:00Z") : new Date(iso);
    const opts = Object.assign({ timeZone: iso.length === 10 ? "UTC" : TZ }, o || { day: "numeric", month: "short" });
    return new Intl.DateTimeFormat("en-GB", opts).format(d);
  },
  dateLong(iso) { return fmt.date(iso, { weekday: "long", day: "numeric", month: "long" }); },
  dow(iso) { return fmt.date(iso, { weekday: "short" }); },
  time(iso) { return iso ? new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso)) : "—"; },
  dt(iso) { return iso ? fmt.date(iso, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", hour12: false }) : "—"; },
  ago(iso) {
    if (!iso) return "never";
    const ms = new Date(D.meta.build_now) - new Date(iso);
    const h = ms / 3600000;
    if (h < 0) return fmt.dt(iso);
    if (h < 1) return Math.max(1, Math.round(h * 60)) + " min before build";
    if (h < 36) return fmt.dt(iso);
    return fmt.date(iso, { day: "numeric", month: "short", year: "numeric" });
  },
  sport(s) { return (s || "").replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()); },
  distLabel(m) {
    const named = { 400: "400 m", 1000: "1 km", 1609.344: "1 mile", 5000: "5K", 10000: "10K", 21097.5: "Half marathon", 42195: "Marathon", 50000: "50K" };
    return named[m] || (m >= 1000 ? fmt.n(m / 1000, 1) + " km" : m + " m");
  },
};

/* ---------- icons ---------- */
const ICONS = {
  today: '<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  training: '<path d="M3 20h18M6 16l4-6 4 3 5-8"/><circle cx="19" cy="5" r="1.5"/>',
  activities: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  recovery: '<path d="M12 21s-7-4.5-9-9.5C1.6 7.6 4.3 4 7.8 4c1.8 0 3.2 1 4.2 2.3C13 5 14.4 4 16.2 4c3.5 0 6.2 3.6 4.8 7.5C19 16.5 12 21 12 21z"/>',
  sleep: '<path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z"/>',
  strength: '<path d="M2 12h2m16 0h2M6 7v10M18 7v10M4 9v6M20 9v6M6 12h12"/>',
  nutrition: '<path d="M12 7c-1-2.5-3-3-4-3m4 3c3-2 8-1 8 5 0 5-3 9-5 9-1.5 0-2-.8-3-.8S10.5 21 9 21c-2 0-5-4-5-9 0-6 5-7 8-5z"/>',
  body: '<circle cx="12" cy="4.5" r="2.5"/><path d="M12 7.5v7m0 0-3.5 7m3.5-7 3.5 7M5 10.5l7-1 7 1"/>',
  routes: '<path d="M9 18l-6 3V6l6-3 6 3 6-3v15l-6 3-6-3z"/><path d="M9 3v15m6-12v15"/>',
  goals: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  coach: '<path d="M12 3l1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
  profile: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
  more: '<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  run: '<circle cx="15" cy="4" r="2"/><path d="M7 21l3-6 3 2 1 5M9 11l2-4 4 2 3 1M6 10l3-3"/>',
  ride: '<circle cx="6" cy="16" r="4"/><circle cx="18" cy="16" r="4"/><path d="M6 16l4-7h5l3 7M10 9l-1-3h-2"/>',
  swim: '<path d="M2 18c2 0 2-1.5 4-1.5S8 18 10 18s2-1.5 4-1.5 2 1.5 4 1.5 2-1.5 4-1.5M8 13l4-6 4 3"/><circle cx="17" cy="6" r="1.6"/>',
  walk: '<circle cx="13" cy="4" r="2"/><path d="M10 21l2-7 3 3v4M9 12l2-5 3 2 3 2"/>',
  other: '<circle cx="12" cy="12" r="8"/>',
  timeline: '<path d="M12 3v18M6 7h6M12 12h6M6 17h6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4m8-4v4"/>',
  heart: '<path d="M12 21s-7-4.5-9-9.5C1.6 7.6 4.3 4 7.8 4c1.8 0 3.2 1 4.2 2.3C13 5 14.4 4 16.2 4c3.5 0 6.2 3.6 4.8 7.5C19 16.5 12 21 12 21z"/>',
  flame: '<path d="M12 3s5 4 5 10a5 5 0 0 1-10 0c0-2 1-4 2-5 0 2 1 3 2 3 0-3 1-6 1-8z"/>',
  bolt: '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-9.5v.5"/>',
  social: '<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2.5"/><path d="M2 20c.8-3.5 3-5 6-5s5.2 1.5 6 5M14 20c.4-2.4 1.6-3.8 3.5-3.8S21 17.6 22 20"/>',
  records: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0zM7 6H4c0 3 1 4.5 3 5M17 6h3c0 3-1 4.5-3 5"/>',
  hrec: '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M13 10v6"/>',
};
function icon(name, cls = "") {
  return `<svg class="ic ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.other}</svg>`;
}
function sportIcon(family) { return icon({ run: "run", ride: "ride", swim: "swim", walk: "walk", strength: "strength" }[family] || "other"); }
function sportColor(family) { return `var(--${["run", "ride", "swim", "walk", "strength"].includes(family) ? family : "other"})`; }

/* ---------- navigation model ---------- */
const DESTS = [
  { id: "today", label: "Today", icon: "today" },
  { id: "training", label: "Training", icon: "training" },
  { id: "activities", label: "Activities", icon: "activities" },
  { id: "recovery", label: "Recovery", icon: "recovery" },
  { id: "sleep", label: "Sleep", icon: "sleep" },
  { id: "strength", label: "Strength", icon: "strength" },
  { id: "nutrition", label: "Nutrition", icon: "nutrition" },
  { id: "body", label: "Body", icon: "body" },
  { id: "routes", label: "Routes", icon: "routes" },
  { id: "goals", label: "Goals", icon: "goals" },
  { id: "coach", label: "Coach", icon: "coach" },
  { id: "profile", label: "Profile", icon: "profile" },
];
function mobileTabs() {
  const want = ((P.ui || {}).mobile_tabs || ["today", "training", "activities", "coach", "more"]).slice(0, 5);
  if (!want.includes("more")) { want.length = Math.min(want.length, 4); want.push("more"); }
  return want;
}

/* ---------- router ---------- */
function parseHash() {
  const h = (location.hash || "#/today").replace(/^#\/?/, "");
  const [path, q] = h.split("?");
  const parts = path.split("/").filter(Boolean);
  const params = {};
  (q || "").split("&").filter(Boolean).forEach(kv => { const [k, v] = kv.split("="); params[decodeURIComponent(k)] = decodeURIComponent(v || ""); });
  return { name: parts[0] || "today", arg: parts[1] ? decodeURIComponent(parts[1]) : null, params };
}
function go(hash) { location.hash = hash; }
AG.render = function () {
  const r = parseHash();
  const scr = AG.screens[r.name] || AG.screens.today;
  closeSheet(true);
  const main = $("#main");
  let html;
  try { html = scr.render(r); }
  catch (e) { console.error(e); html = empty("This view could not render", String(e && e.message || e)); }
  main.innerHTML = html;
  const title = typeof scr.title === "function" ? scr.title(r) : scr.title;
  $("#hdr-title").textContent = title || "AGame";
  document.title = (title ? title + " · " : "") + "AGame";
  const back = $("#hdr-back");
  back.hidden = !scr.parent;
  back.onclick = () => (history.length > 1 ? history.back() : go(scr.parent));
  const active = scr.nav || r.name;
  $$("[data-nav]").forEach(a => a.setAttribute("aria-current", a.dataset.nav === active || (a.dataset.nav === "more" && !mobileTabs().includes(active)) ? "page" : "false"));
  if (scr.after) scr.after(r);
  main.focus({ preventScroll: true });
  if (!AG._keepScroll) window.scrollTo(0, 0);
  AG._keepScroll = false;
};
function rerender() { AG._keepScroll = true; AG.render(); }

/* ---------- sheets ---------- */
let sheetOpen = false;
function openSheet(title, html, opts = {}) {
  closeSheet(true);
  const scrim = document.createElement("div"); scrim.className = "scrim"; scrim.id = "scrim";
  const sh = document.createElement("div"); sh.className = "sheet"; sh.id = "sheet";
  sh.setAttribute("role", "dialog"); sh.setAttribute("aria-modal", "true"); sh.setAttribute("aria-label", title);
  sh.innerHTML = `<div class="grab"></div><div class="sh-head"><h2>${esc(title)}</h2><button class="x" aria-label="Close" data-close>×</button></div><div class="sh-body">${html}</div>`;
  document.body.append(scrim, sh);
  requestAnimationFrame(() => { scrim.classList.add("on"); sh.classList.add("on"); });
  scrim.onclick = () => closeSheet();
  sh.querySelector("[data-close]").onclick = () => closeSheet();
  sheetOpen = true;
  AG._lastFocus = document.activeElement;
  setTimeout(() => (sh.querySelector("[data-autofocus]") || sh.querySelector("[data-close]")).focus(), 30);
  history.pushState({ sheet: true }, "", location.href);
  if (opts.after) opts.after(sh);
  return sh;
}
function closeSheet(silent) {
  const sh = $("#sheet"), sc = $("#scrim");
  if (!sh) return;
  sh.remove(); sc && sc.remove();
  if (sheetOpen && !silent && history.state && history.state.sheet) { sheetOpen = false; history.back(); }
  sheetOpen = false;
  if (AG._lastFocus && AG._lastFocus.focus) AG._lastFocus.focus();
}
window.addEventListener("popstate", () => { if ($("#sheet")) { sheetOpen = false; closeSheet(true); } });
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && $("#sheet")) { e.preventDefault(); closeSheet(); }
  if (e.key === "Tab" && $("#sheet")) {
    const f = $$("#sheet button, #sheet a, #sheet input, #sheet select, #sheet textarea, #sheet [tabindex]").filter(x => !x.disabled && x.offsetParent !== null);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  }
});

/* ---------- tooltip ---------- */
const tip = { el: null };
function showTip(x, y, html) {
  if (!tip.el) { tip.el = document.createElement("div"); tip.el.className = "tip"; tip.el.setAttribute("role", "status"); document.body.appendChild(tip.el); }
  tip.el.innerHTML = html; tip.el.classList.add("on");
  const r = tip.el.getBoundingClientRect();
  let left = x + 12, top = y - r.height - 12;
  if (left + r.width > window.innerWidth - 8) left = x - r.width - 12;
  if (left < 8) left = 8;
  if (top < 8) top = y + 16;
  tip.el.style.left = left + "px"; tip.el.style.top = top + "px";
}
function hideTip() { if (tip.el) tip.el.classList.remove("on"); }

/* ---------- API (only when served by fitness_server.py) ---------- */
async function detectServer() {
  if (location.protocol === "file:") return false;
  try { const r = await fetch("api/ping", { credentials: "same-origin", cache: "no-store" }); AG.online = r.ok; } catch (e) { AG.online = false; }
  return AG.online;
}
async function api(method, path, body) {
  if (!AG.online) throw new Error("Edits need a connection to your AGame server");
  const r = await fetch("api/" + path, { method, credentials: "same-origin", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || ("HTTP " + r.status));
  return j;
}
function offlineNote() { return AG.online ? "" : `<p class="note-off">Edits need connection to your AGame server. This snapshot is read-only.</p>`; }
