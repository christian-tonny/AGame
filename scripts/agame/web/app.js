/* AGame shell: navigation, banners, theme, service worker, boot */
"use strict";

function applyTheme() {
  const t = uiGet("chip:theme", uiGet("theme", ((D.profile.ui || {}).theme) || "system"));
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}

function logo(size = 28) {
  return `<svg class="logo" width="${size}" height="${size}" viewBox="0 0 100 100" aria-hidden="true"><defs><linearGradient id="lg-tile" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff6b1a"/><stop offset="1" stop-color="#e8430a"/></linearGradient></defs>
    <rect width="100" height="100" rx="23" fill="url(#lg-tile)"/><path d="M28 78L50 22L72 78" fill="none" stroke="#fff" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M17 62H35L41 51L49 72L55 62H83" fill="none" stroke="#fff" stroke-width="6.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
}
function buildShell() {
  const tabs = mobileTabs();
  const label = id => id === "more" ? "More" : (DESTS.find(d => d.id === id) || { label: id }).label;
  const ic = id => id === "more" ? "more" : (DESTS.find(d => d.id === id) || { icon: "other" }).icon;
  $("#tabbar").innerHTML = tabs.map(id => id === "more"
    ? `<button data-nav="more" data-open="more" aria-label="More destinations">${icon("more")}<span>More</span></button>`
    : `<a href="#/${id}" data-nav="${id}">${icon(ic(id))}<span>${esc(label(id))}</span></a>`).join("");
  $("#sidebar").innerHTML = `<div class="brand" aria-label="AGame">${logo()}<span aria-hidden="true">Game</span></div>${DESTS.map(d => `<a href="#/${d.id}" data-nav="${d.id}">${icon(d.icon)}<span>${esc(d.label)}</span></a>`).join("")}
    <div class="foot">Build ${esc(D.meta.build_date)}<br>${esc(TZ)}</div>`;
  const banners = [];
  if (D.meta.fixture === "empty") banners.push(`<div class="banner sync" role="note">${icon("info")}<span><b>${STR.waiting}.</b> This build uses the empty fixtures shipped with the public repo.</span></div>`);
  const ds = D.meta.data_status;
  if (D.meta.fixture !== "empty" && ds.overall !== "ok") banners.push(`<div class="banner sync" role="status">${icon("info")}<span>${ds.sleep_missing ? STR.sleepNotSynced + " · " : ""}${ds.last_sync ? "Last successful update " + fmt.dt(ds.last_sync) : "No sync yet"}</span></div>`);
  $("#banners").innerHTML = banners.join("");
}

AG.sheets.more = function () {
  const tabs = mobileTabs();
  const rest = DESTS.filter(d => !tabs.includes(d.id));
  const extra = [{ id: "timeline", label: "Timeline", icon: "timeline" }, { id: "journal", label: "Journal", icon: "calendar" }, { id: "widgets", label: "Widgets", icon: "today" }];
  openSheet("More", `<nav aria-label="More destinations"><div class="more-grid">${rest.concat(extra).map(d => `<a href="#/${d.id}" data-close-sheet>${icon(d.icon)}<span>${esc(d.label)}</span></a>`).join("")}</div></nav>`);
};
document.addEventListener("click", e => { if (e.target.closest("[data-close-sheet]")) closeSheet(true); });

function offlineBanner() {
  const set = () => {
    let b = $("#offline-b");
    if (!navigator.onLine) {
      if (!b) $("#banners").insertAdjacentHTML("afterbegin", `<div class="banner offline" id="offline-b" role="status">${icon("info")}<span>Offline · showing the last successful snapshot (${fmt.dt(D.meta.data_status.last_sync || D.meta.build_now)})</span></div>`);
    } else if (b) b.remove();
  };
  window.addEventListener("online", set); window.addEventListener("offline", set); set();
}

async function boot() {
  applyTheme();
  buildShell();
  offlineBanner();
  window.addEventListener("hashchange", AG.render);
  if (window.matchMedia) window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", applyTheme);
  AG.render();
  try {
    if (await detectServer()) {
      try { const p = await fetch("api/ping", { credentials: "same-origin" }).then(r => r.json()); AG.llm = !!p.llm; } catch (e) { /* ignore */ }
      rerender();
      undoToastOnBoot();
    }
  } catch (e) { /* static file: read-only */ }
  if ("serviceWorker" in navigator && location.protocol !== "file:") {
    navigator.serviceWorker.register("fitness_sw.js", { scope: "./" }).catch(() => { /* optional */ });
  }
  document.documentElement.setAttribute("data-ready", "1");
}
boot();
