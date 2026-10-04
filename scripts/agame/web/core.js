/* AGame core: data access, formatting, router, sheets, tooltips, API. No metric formulas live here;
   every number comes from computed.json (window.AG_DATA). */
"use strict";
const AG = { screens: {}, charts: {}, ui: {}, online: false };
const D = JSON.parse(document.getElementById("agame-data").textContent);
const P = D.profile || {};
const TZ = D.meta.timezone || "UTC";
const AGENT = D.meta.sync_agent || "your sync agent";
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
/* Icons: Tabler Icons (MIT, tabler.io/icons), inlined so the dashboard works offline. */
const ICONS = {
  today: '<path d="M5 12l-2 0l9 -9l9 9l-2 0"/> <path d="M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-7"/> <path d="M9 21v-6a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2v6"/>',
  training: '<path d="M4 19l16 0"/> <path d="M4 15l4 -6l4 2l4 -5l4 4"/>',
  activities: '<path d="M3 12h4l3 8l4 -16l3 8h4"/>',
  recovery: '<path d="M19.5 12.572l-7.5 7.428l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.5 6.572"/>',
  sleep: '<path d="M12 3c.132 0 .263 0 .393 0a7.5 7.5 0 0 0 7.92 12.446a9 9 0 1 1 -8.313 -12.454l0 .008"/>',
  strength: '<path d="M2 12h1"/> <path d="M6 8h-2a1 1 0 0 0 -1 1v6a1 1 0 0 0 1 1h2"/> <path d="M6 7v10a1 1 0 0 0 1 1h1a1 1 0 0 0 1 -1v-10a1 1 0 0 0 -1 -1h-1a1 1 0 0 0 -1 1"/> <path d="M9 12h6"/> <path d="M15 7v10a1 1 0 0 0 1 1h1a1 1 0 0 0 1 -1v-10a1 1 0 0 0 -1 -1h-1a1 1 0 0 0 -1 1"/> <path d="M18 8h2a1 1 0 0 1 1 1v6a1 1 0 0 1 -1 1h-2"/> <path d="M22 12h-1"/>',
  nutrition: '<path d="M4 11.319c0 3.102 .444 5.319 2.222 7.978c1.351 1.797 3.156 2.247 5.08 .988c.426 -.268 .97 -.268 1.397 0c1.923 1.26 3.728 .809 5.079 -.988c1.778 -2.66 2.222 -4.876 2.222 -7.977c0 -2.661 -1.99 -5.32 -4.444 -5.32c-1.267 0 -2.41 .693 -3.22 1.44a.5 .5 0 0 1 -.672 0c-.809 -.746 -1.953 -1.44 -3.22 -1.44c-2.454 0 -4.444 2.66 -4.444 5.319"/> <path d="M7 12c0 -1.47 .454 -2.34 1.5 -3"/> <path d="M12 7c0 -1.2 .867 -4 3 -4"/>',
  body: '<path d="M15 5a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M5 20l5 -.5l1 -2"/> <path d="M18 20v-5h-5.5l2.5 -6.5l-5.5 1l1.5 2"/>',
  routes: '<path d="M3 7l6 -3l6 3l6 -3v13l-6 3l-6 -3l-6 3v-13"/> <path d="M9 4v13"/> <path d="M15 7v13"/>',
  goals: '<path d="M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M7 12a5 5 0 1 0 10 0a5 5 0 1 0 -10 0"/> <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/>',
  coach: '<path d="M16 18a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2m0 -12a2 2 0 0 1 2 2a2 2 0 0 1 2 -2a2 2 0 0 1 -2 -2a2 2 0 0 1 -2 2m-7 12a6 6 0 0 1 6 -6a6 6 0 0 1 -6 -6a6 6 0 0 1 -6 6a6 6 0 0 1 6 6"/>',
  profile: '<path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0 -8 0"/> <path d="M6 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/>',
  more: '<path d="M4 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M11 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M18 12a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>',
  back: '<path d="M15 6l-6 6l6 6"/>',
  run: '<path d="M11.007 5a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/> <path d="M4 17l5 1l.75 -1.5"/> <path d="M15 21v-4l-4 -3l1 -6"/> <path d="M7 12v-3l5 -1l3 3l3 1"/>',
  ride: '<path d="M2 18a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/> <path d="M16 18a3 3 0 1 0 6 0a3 3 0 0 0 -6 0"/> <path d="M12 19v-4l-3 -3l5 -4l2 3h3"/> <path d="M13.007 5a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/>',
  swim: '<path d="M15 9a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M6 11l4 -2l3.5 3l-1.5 2"/> <path d="M3 16.75a2.4 2.4 0 0 0 1 .25a2.4 2.4 0 0 0 2 -1a2.4 2.4 0 0 1 2 -1a2.4 2.4 0 0 1 2 1a2.4 2.4 0 0 0 2 1a2.4 2.4 0 0 0 2 -1a2.4 2.4 0 0 1 2 -1a2.4 2.4 0 0 1 2 1a2.4 2.4 0 0 0 2 1a2.4 2.4 0 0 0 1 -.25"/>',
  walk: '<path d="M12 4a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M7 21l3 -4"/> <path d="M16 21l-2 -4l-3 -3l1 -6"/> <path d="M6 12l2 -3l4 -1l3 3l3 1"/>',
  other: '<path d="M3 12h4.5l1.5 -6l4 12l2 -9l1.5 3h4.5"/>',
  timeline: '<path d="M4 16l6 -7l5 5l5 -6"/> <path d="M14 14a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M9 9a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M3 16a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/> <path d="M19 8a1 1 0 1 0 2 0a1 1 0 1 0 -2 0"/>',
  calendar: '<path d="M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2v-12"/> <path d="M16 3v4"/> <path d="M8 3v4"/> <path d="M4 11h16"/> <path d="M11 15h1"/> <path d="M12 15v3"/>',
  heart: '<path d="M19.5 12.572l-7.5 7.428l-7.5 -7.428a5 5 0 1 1 7.5 -6.566a5 5 0 1 1 7.5 6.572"/>',
  flame: '<path d="M12 10.941c2.333 -3.308 .167 -7.823 -1 -8.941c0 3.395 -2.235 5.299 -3.667 6.706c-1.43 1.408 -2.333 3.294 -2.333 5.588c0 3.704 3.134 6.706 7 6.706c3.866 0 7 -3.002 7 -6.706c0 -1.712 -1.232 -4.403 -2.333 -5.588c-2.084 3.353 -3.257 3.353 -4.667 2.235"/>',
  bolt: '<path d="M13 3l0 7l6 0l-8 11l0 -7l-6 0l8 -11"/>',
  info: '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/> <path d="M12 9h.01"/> <path d="M11 12h1v4h1"/>',
  social: '<path d="M5 7a4 4 0 1 0 8 0a4 4 0 1 0 -8 0"/> <path d="M3 21v-2a4 4 0 0 1 4 -4h4a4 4 0 0 1 4 4v2"/> <path d="M16 3.13a4 4 0 0 1 0 7.75"/> <path d="M21 21v-2a4 4 0 0 0 -3 -3.85"/>',
  records: '<path d="M8 21l8 0"/> <path d="M12 17l0 4"/> <path d="M7 4l10 0"/> <path d="M17 4v8a5 5 0 0 1 -10 0v-8"/> <path d="M3 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/> <path d="M17 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/>',
  hrec: '<path d="M9 5h-2a2 2 0 0 0 -2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-12a2 2 0 0 0 -2 -2h-2"/> <path d="M9 5a2 2 0 0 1 2 -2h2a2 2 0 0 1 2 2a2 2 0 0 1 -2 2h-2a2 2 0 0 1 -2 -2"/> <path d="M11.993 16.75l2.747 -2.815a1.9 1.9 0 0 0 0 -2.632a1.775 1.775 0 0 0 -2.56 0l-.183 .188l-.183 -.189a1.775 1.775 0 0 0 -2.56 0a1.899 1.899 0 0 0 0 2.632l2.738 2.825l.001 -.009"/>',
  up: '<path d="M12 5l0 14"/> <path d="M18 11l-6 -6"/> <path d="M6 11l6 -6"/>',
  down: '<path d="M12 5l0 14"/> <path d="M18 13l-6 6"/> <path d="M6 13l6 6"/>',
  minus: '<path d="M5 12l14 0"/>',
  x: '<path d="M18 6l-12 12"/> <path d="M6 6l12 12"/>',
  check: '<path d="M5 12l5 5l10 -10"/>',
  next: '<path d="M9 6l6 6l-6 6"/>',
  star: '<path d="M12 17.75l-6.172 3.245l1.179 -6.873l-5 -4.867l6.9 -1l3.086 -6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873l-6.158 -3.245"/>',
  alert: '<path d="M12 9v4"/> <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0"/> <path d="M12 16h.01"/>',
  scale: '<path d="M7 20l10 0"/> <path d="M6 6l6 -1l6 1"/> <path d="M12 3l0 17"/> <path d="M9 12l-3 -6l-3 6a3 3 0 0 0 6 0"/> <path d="M21 12l-3 -6l-3 6a3 3 0 0 0 6 0"/>',
  droplet: '<path d="M7.502 19.423c2.602 2.105 6.395 2.105 8.996 0c2.602 -2.105 3.262 -5.708 1.566 -8.546l-4.89 -7.26c-.42 -.625 -1.287 -.803 -1.936 -.397a1.376 1.376 0 0 0 -.41 .397l-4.893 7.26c-1.695 2.838 -1.035 6.441 1.567 8.546"/>',
  coffee: '<path d="M3 14c.83 .642 2.077 1.017 3.5 1c1.423 .017 2.67 -.358 3.5 -1c.83 -.642 2.077 -1.017 3.5 -1c1.423 -.017 2.67 .358 3.5 1"/> <path d="M8 3a2.4 2.4 0 0 0 -1 2a2.4 2.4 0 0 0 1 2"/> <path d="M12 3a2.4 2.4 0 0 0 -1 2a2.4 2.4 0 0 0 1 2"/> <path d="M3 10h14v5a6 6 0 0 1 -6 6h-2a6 6 0 0 1 -6 -6v-5"/> <path d="M16.746 16.726a3 3 0 1 0 .252 -5.555"/>',
  weight: '<path d="M9 6a3 3 0 1 0 6 0a3 3 0 1 0 -6 0"/> <path d="M6.835 9h10.33a1 1 0 0 1 .984 .821l1.637 9a1 1 0 0 1 -.984 1.179h-13.604a1 1 0 0 1 -.984 -1.179l1.637 -9a1 1 0 0 1 .984 -.821"/>',
  clock: '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0 -18 0"/> <path d="M12 7v5l3 3"/>',
  question: '<path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0 -18 0"/> <path d="M12 17l0 .01"/> <path d="M12 13.5a1.5 1.5 0 0 1 1 -1.5a2.6 2.6 0 1 0 -3 -4"/>',
  "star-filled": '<g fill="currentColor" stroke="none"><path d="M8.243 7.34l-6.38 .925l-.113 .023a1 1 0 0 0 -.44 1.684l4.622 4.499l-1.09 6.355l-.013 .11a1 1 0 0 0 1.464 .944l5.706 -3l5.693 3l.1 .046a1 1 0 0 0 1.352 -1.1l-1.091 -6.355l4.624 -4.5l.078 -.085a1 1 0 0 0 -.633 -1.62l-6.38 -.926l-2.852 -5.78a1 1 0 0 0 -1.794 0l-2.853 5.78z"/></g>',
  "caret-up": '<g fill="currentColor" stroke="none"><path d="M11.293 7.293a1 1 0 0 1 1.32 -.083l.094 .083l6 6l.083 .094l.054 .077l.054 .096l.017 .036l.027 .067l.032 .108l.01 .053l.01 .06l.004 .057l.002 .059l-.002 .059l-.005 .058l-.009 .06l-.01 .052l-.032 .108l-.027 .067l-.07 .132l-.065 .09l-.073 .081l-.094 .083l-.077 .054l-.096 .054l-.036 .017l-.067 .027l-.108 .032l-.053 .01l-.06 .01l-.057 .004l-.059 .002h-12c-.852 0 -1.297 -.986 -.783 -1.623l.076 -.084l6 -6z"/></g>',
  "caret-down": '<g fill="currentColor" stroke="none"><path d="M18 9c.852 0 1.297 .986 .783 1.623l-.076 .084l-6 6a1 1 0 0 1 -1.32 .083l-.094 -.083l-6 -6l-.083 -.094l-.054 -.077l-.054 -.096l-.017 -.036l-.027 -.067l-.032 -.108l-.01 -.053l-.01 -.06l-.004 -.057v-.118l.005 -.058l.009 -.06l.01 -.052l.032 -.108l.027 -.067l.07 -.132l.065 -.09l.073 -.081l.094 -.083l.077 -.054l.096 -.054l.036 -.017l.067 -.027l.108 -.032l.053 -.01l.06 -.01l.057 -.004l12.059 -.002z"/></g>',
  "cloud-check": '<path d="M11 18.004h-4.343c-2.572 -.004 -4.657 -2.011 -4.657 -4.487c0 -2.475 2.085 -4.482 4.657 -4.482c.393 -1.762 1.794 -3.2 3.675 -3.773c1.88 -.572 3.956 -.193 5.444 1c1.488 1.19 2.162 3.007 1.77 4.769h.99c1.388 0 2.585 .82 3.138 2.007"/> <path d="M15 19l2 2l4 -4"/>',
  arrow: '<path d="M5 12l14 0"/> <path d="M13 18l6 -6"/> <path d="M13 6l6 6"/>',
  share: '<path d="M13 4v4c-6.575 1.028 -9.02 6.788 -10 12c-.037 .206 5.384 -5.962 10 -6v4l8 -7l-8 -7"/>',
  bed: '<path d="M5 9a2 2 0 1 0 4 0a2 2 0 1 0 -4 0"/> <path d="M22 17v-3h-20"/> <path d="M2 8v9"/> <path d="M12 14h10v-2a3 3 0 0 0 -3 -3h-7v5"/>',
  meal: '<path d="M19 3v12h-5c-.023 -3.681 .184 -7.406 5 -12m0 12v6h-1v-3m-10 -14v17m-3 -17v3a3 3 0 1 0 6 0v-3"/>',
  note: '<path d="M5 5a2 2 0 0 1 2 -2h10a2 2 0 0 1 2 2v14a2 2 0 0 1 -2 2h-10a2 2 0 0 1 -2 -2l0 -14"/> <path d="M9 7l6 0"/> <path d="M9 11l6 0"/> <path d="M9 15l4 0"/>',
  event: '<path d="M4 7a2 2 0 0 1 2 -2h12a2 2 0 0 1 2 2v12a2 2 0 0 1 -2 2h-12a2 2 0 0 1 -2 -2l0 -12"/> <path d="M16 3l0 4"/> <path d="M8 3l0 4"/> <path d="M4 11l16 0"/> <path d="M8 15h2v2h-2l0 -2"/>',
  lungs: '<path d="M6.081 20c1.612 0 2.919 -1.335 2.919 -2.98v-9.763c0 -.694 -.552 -1.257 -1.232 -1.257c-.205 0 -.405 .052 -.584 .15l-.13 .083c-1.46 1.059 -2.432 2.647 -3.404 5.824c-.42 1.37 -.636 2.962 -.648 4.775c-.012 1.675 1.261 3.054 2.877 3.161l.203 .007"/> <path d="M17.92 20c-1.613 0 -2.92 -1.335 -2.92 -2.98v-9.763c0 -.694 .552 -1.257 1.233 -1.257c.204 0 .405 .052 .584 .15l.13 .083c1.46 1.059 2.432 2.647 3.405 5.824c.42 1.37 .636 2.962 .648 4.775c.012 1.675 -1.261 3.054 -2.878 3.161l-.202 .007"/> <path d="M9 12a3 3 0 0 0 3 -3a3 3 0 0 0 3 3"/> <path d="M12 4v5"/>',
  refresh: '<path d="M20 11a8.1 8.1 0 0 0 -15.5 -2m-.5 -4v4h4"/> <path d="M4 13a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4"/>',
  download: '<path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2 -2v-2"/> <path d="M7 11l5 5l5 -5"/> <path d="M12 4l0 12"/>',
};
function icon(name, cls = "") {
  return `<svg class="ic ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ICONS.other}</svg>`;
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
  sh.innerHTML = `<div class="grab"></div><div class="sh-head"><h2>${esc(title)}</h2><button class="x" aria-label="Close" data-close>${icon("x")}</button></div><div class="sh-body">${html}</div>`;
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
