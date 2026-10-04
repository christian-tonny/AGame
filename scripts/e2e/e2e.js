/* AGame browser tests (Playwright). Builds synthetic + empty dashboards, checks every destination on
 * iPhone (390x797) dark and light and desktop (1440x900), sheets, tooltips, empty states, overflow, then
 * runs the PWA offline check through the dev server. Writes screenshots to docs/screenshots/.
 *
 *   NODE_PATH=$(npm root -g) node scripts/e2e/e2e.js            # run checks + screenshots
 *   NODE_PATH=$(npm root -g) node scripts/e2e/e2e.js --no-shots # checks only
 *
 * Exit code 0 when every check passes, 1 otherwise.
 */
"use strict";
const { chromium } = require("playwright");
const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const net = require("net");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPTS = path.join(ROOT, "scripts");
const SHOTS = path.join(ROOT, "docs", "screenshots");
const DATE = "2026-10-04";
const PHONE = { width: 390, height: 797 };
const DESKTOP = { width: 1440, height: 900 };
const NO_SHOTS = process.argv.includes("--no-shots");
const EXEC = fs.existsSync("/opt/pw-browsers/chromium") ? undefined : undefined;

const DESTS = ["today", "training", "activities", "recovery", "sleep", "strength", "nutrition", "body", "routes", "goals", "coach", "profile",
  "strain", "timeline", "journal", "widgets"];
const TRAINING_TABS = ["fitness", "log", "progress", "plan", "zones", "records", "recaps", "review"];

const failures = [];
let passed = 0;
function check(ok, msg) { if (ok) passed++; else { failures.push(msg); console.log("  FAIL " + msg); } }

function py(args, opts = {}) {
  return execFileSync("python3", args, { cwd: SCRIPTS, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"], ...opts });
}
function buildDashboard(dataDir, outDir) {
  try { py(["build_dashboard.py", "--date", DATE, "--data-dir", dataDir, "--out", outDir, "--quiet"]); }
  catch (e) { if (e.status !== 2) throw e; } // 2 = degraded (expected for empty fixtures)
  return path.join(outDir, "fitness_dashboard.html");
}
function freePort() {
  return new Promise(res => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });
}

async function watchErrors(page) {
  const errs = [];
  page.on("pageerror", e => errs.push("pageerror: " + e.message));
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource|api\/ping/.test(m.text())) errs.push("console: " + m.text()); });
  return errs;
}
async function go(page, hash) {
  await page.evaluate(h => { location.hash = h; }, hash);
  await page.waitForTimeout(220);
}
async function overflow(page) {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}
async function mainText(page) { return page.$eval("#main", el => el.innerText); }
async function shot(page, name) {
  if (NO_SHOTS) return;
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(120);
  await page.screenshot({ path: path.join(SHOTS, name + ".png") });
}

async function destinations(browser, file, label, opts) {
  console.log(`\n${label}`);
  const ctx = await browser.newContext({ viewport: opts.viewport, colorScheme: opts.scheme, deviceScaleFactor: opts.dpr || 2 });
  const page = await ctx.newPage();
  const errs = await watchErrors(page);
  await page.goto("file://" + file + "#/today");
  await page.waitForSelector("html[data-ready='1']");
  for (const r of opts.routes) {
    await go(page, "#/" + r);
    const txt = await mainText(page);
    check(txt.trim().length > 20, `${label} ${r}: screen is blank`);
    check(!/could not render/i.test(txt), `${label} ${r}: render error`);
    check(!/\bNaN\b|\bundefined\b|\[object Object\]/.test(txt), `${label} ${r}: shows NaN/undefined`);
    const ow = await overflow(page);
    check(ow <= 0, `${label} ${r}: horizontal overflow ${ow}px`);
    if (opts.shots) await shot(page, `${opts.prefix}-${r}`);
  }
  if (opts.extra) await opts.extra(page, label);
  check(errs.length === 0, `${label}: JS errors: ${errs.slice(0, 5).join(" | ")}`);
  await ctx.close();
}

async function interactions(page, label) {
  // More sheet from the tab bar
  await go(page, "#/today");
  await page.click("#tabbar [data-open='more']");
  await page.waitForSelector("#sheet.on");
  await page.waitForTimeout(120);
  const links = await page.$$eval("#sheet .more-grid a", as => as.map(a => a.getAttribute("href")));
  check(links.includes("#/recovery") && links.includes("#/profile"), `${label}: More sheet lists other destinations`);
  check(await page.evaluate(() => document.activeElement && document.activeElement.closest("#sheet") !== null), `${label}: focus moves into sheet`);
  if (!NO_SHOTS) await page.screenshot({ path: path.join(SHOTS, "dark-more-sheet.png") });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(350);
  check(!(await page.$("#sheet")), `${label}: Escape closes sheet`);
  // navigate via the sheet
  await page.click("#tabbar [data-open='more']");
  await page.waitForSelector("#sheet.on");
  await page.click("#sheet a[href='#/sleep']");
  await page.waitForTimeout(350);
  check(await page.evaluate(() => location.hash === "#/sleep"), `${label}: More sheet navigates`);
  // provenance sheet
  await go(page, "#/today");
  await page.click("[data-prov]");
  await page.waitForSelector("#sheet.on");
  const ptxt = await page.$eval("#sheet", el => el.innerText);
  check(/Value/.test(ptxt) && /(As of|Updated|as of)/i.test(ptxt), `${label}: provenance sheet shows value and timestamp`);
  if (!NO_SHOTS) await page.screenshot({ path: path.join(SHOTS, "dark-provenance-sheet.png") });
  await page.keyboard.press("Escape");
  await page.waitForTimeout(300);
  // recovery factors sheet
  const factors = await page.$("[data-open='factors']");
  if (factors) {
    await factors.click();
    await page.waitForSelector("#sheet.on");
    check((await page.$eval("#sheet", el => el.innerText)).length > 40, `${label}: factors sheet has content`);
    await page.keyboard.press("Escape");
    await page.waitForTimeout(300);
  }
  // chart tooltip by keyboard
  await go(page, "#/training?tab=fitness");
  await page.focus(".chart");
  await page.keyboard.press("ArrowRight");
  await page.waitForTimeout(120);
  check(await page.evaluate(() => !!document.querySelector(".tip.on") && document.querySelector(".tip.on").innerText.length > 0), `${label}: chart tooltip on arrow key`);
  // chart tooltip by pointer
  const box = await (await page.$(".chart svg")).boundingBox();
  await page.mouse.move(box.x + box.width * 0.6, box.y + box.height * 0.5);
  await page.waitForTimeout(120);
  check(await page.evaluate(() => !!document.querySelector(".tip.on")), `${label}: chart tooltip on hover`);
  // training tabs
  for (const t of TRAINING_TABS) {
    await go(page, "#/training?tab=" + t);
    const ow = await overflow(page);
    check(ow <= 0, `${label}: training/${t} overflow ${ow}px`);
    check(!/could not render/i.test(await mainText(page)), `${label}: training/${t} render error`);
    if (!NO_SHOTS && ["plan", "zones", "records"].includes(t)) await shot(page, "dark-training-" + t);
  }
  // activity detail + route detail
  await go(page, "#/activities");
  const href = await page.$eval("#main a.li[href^='#/activity/']", a => a.getAttribute("href"));
  await go(page, href);
  check(/Summary/.test(await mainText(page)), `${label}: activity detail opens`);
  check(await overflow(page) <= 0, `${label}: activity detail overflow`);
  await shot(page, "dark-activity-detail");
  await go(page, "#/routes");
  const rhref = await page.$eval("#main a.li[href^='#/route/']", a => a.getAttribute("href"));
  await go(page, rhref);
  check(await overflow(page) <= 0, `${label}: route detail overflow`);
  await shot(page, "dark-route-detail");
  // back button visible on detail, hidden on top-level
  check(await page.evaluate(() => { const b = document.querySelector("#back"); return !b || !b.hidden; }), `${label}: back button on detail`);
}

async function emptyStates(page, label) {
  await go(page, "#/today");
  const txt = await mainText(page);
  check(/Waiting for/i.test(txt), `${label}: Today says it is waiting for the first sync`);
  const rings = await page.$$eval(".ring", rs => rs.map(r => r.innerText));
  check(rings.every(t => !/^\s*0\s*%?\s*$/m.test(t)), `${label}: rings never show 0 for missing data (${rings.join(" | ")})`);
  await go(page, "#/nutrition");
  check(!/\b0 kcal\b|\b0 g protein\b/i.test(await mainText(page)), `${label}: nutrition shows no zeros`);
  await go(page, "#/body");
  check(!/\b0(\.0)? kg\b/.test(await mainText(page)), `${label}: body shows no 0 kg`);
}

async function pwaOffline(browser, dataDir, distDir) {
  console.log("\nPWA offline via dev server");
  const port = await freePort();
  const srv = spawn("python3", ["fitness_server.py", "--dev", "--port", String(port), "--data-dir", dataDir, "--dist-dir", distDir],
    { cwd: SCRIPTS, env: { ...process.env, AGAME_QUIET: "1" }, stdio: "ignore" });
  try {
    const base = `http://127.0.0.1:${port}`;
    for (let i = 0; i < 100; i++) { try { const r = await fetch(base + "/healthz"); if (r.ok) break; } catch (e) { /* not up */ } await new Promise(r => setTimeout(r, 150)); }
    const ctx = await browser.newContext({ viewport: PHONE, colorScheme: "dark" });
    const page = await ctx.newPage();
    const errs = await watchErrors(page);
    await page.goto(base + "/fitness_dashboard.html#/today");
    await page.waitForSelector("html[data-ready='1']");
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.reload();
    await page.waitForSelector("html[data-ready='1']");
    check(await page.evaluate(() => !!navigator.serviceWorker.controller), "service worker controls the page");
    const man = await (await fetch(base + "/manifest.webmanifest")).json();
    check(man.display === "standalone" && man.icons.length >= 2, "manifest is installable");
    // edit through the API while online
    const res = await page.evaluate(async () => (await fetch("api/entries/journal.entries", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ date: "2026-10-04", type: "note", text: "e2e" }) })).status);
    check(res === 200, "online edit accepted (" + res + ")");
    await ctx.setOffline(true);
    await page.reload();
    await page.waitForSelector("html[data-ready='1']");
    check((await mainText(page)).length > 50, "dashboard renders offline from cache");
    check(!!(await page.$("#offline-b")), "offline banner shown");
    if (!NO_SHOTS) await page.screenshot({ path: path.join(SHOTS, "dark-offline.png") });
    check(errs.length === 0, "PWA: JS errors: " + errs.slice(0, 5).join(" | "));
    await ctx.close();
  } finally { srv.kill(); }
}

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agame-e2e-"));
  const syn = path.join(tmp, "syn"), synDist = path.join(tmp, "syn-dist"), emptyDist = path.join(tmp, "empty-dist");
  py(["-m", "agame.synthetic", "--out", syn, "--date", DATE]);
  const synHtml = buildDashboard(syn, synDist);
  const emptyHtml = buildDashboard(path.join(ROOT, "data"), emptyDist);
  if (!NO_SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch(EXEC ? { executablePath: EXEC } : {});
  try {
    await destinations(browser, synHtml, "iPhone dark", { viewport: PHONE, scheme: "dark", routes: DESTS, shots: true, prefix: "dark", extra: interactions });
    await destinations(browser, synHtml, "iPhone light", { viewport: PHONE, scheme: "light", routes: DESTS, shots: false, prefix: "light",
      extra: async page => { await go(page, "#/today"); await shot(page, "light-today"); } });
    await destinations(browser, synHtml, "Desktop", { viewport: DESKTOP, scheme: "dark", dpr: 1, routes: ["today", "training", "activities", "sleep"], shots: false,
      extra: async page => {
        await go(page, "#/today");
        check(await page.$eval("#sidebar", el => getComputedStyle(el).display !== "none"), "Desktop: sidebar visible");
        check(await page.$eval("#tabbar", el => getComputedStyle(el).display === "none"), "Desktop: tab bar hidden");
        await shot(page, "desktop-today");
      } });
    await destinations(browser, emptyHtml, "Empty fixtures", { viewport: PHONE, scheme: "dark", routes: DESTS, shots: false, extra: emptyStates });
    await pwaOffline(browser, syn, path.join(tmp, "srv-dist"));
  } finally {
    await browser.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  console.log(`\n${passed} checks passed, ${failures.length} failed`);
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
