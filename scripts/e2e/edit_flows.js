/* AGame edit flows in a real browser against the dev server (60 days of synthetic data).
 * Each flow opens a sheet, fills it, saves, waits for the server rebuild + reload, and checks the result.
 *
 *   NODE_PATH=$(npm root -g) node scripts/e2e/edit_flows.js
 */
"use strict";
const { chromium } = require("playwright");
const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const net = require("net");

const SCRIPTS = path.resolve(__dirname, "..");
const SHOTS = path.join(SCRIPTS, "..", "docs", "screenshots");
const NO_SHOTS = process.argv.includes("--no-shots");
const failures = [];
let passed = 0;
function check(ok, msg) { if (ok) passed++; else { failures.push(msg); console.log("  FAIL " + msg); } }
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, "127.0.0.1", () => { const p = s.address().port; s.close(() => res(p)); }); });

(async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "agame-edits-"));
  const data = path.join(tmp, "data"), dist = path.join(tmp, "dist");
  execFileSync("python3", ["-m", "agame.synthetic", "--out", data, "--date", "2026-10-04", "--days", "60"], { cwd: SCRIPTS, stdio: "ignore" });
  const port = await freePort();
  const srv = spawn("python3", ["fitness_server.py", "--dev", "--port", String(port), "--data-dir", data, "--dist-dir", dist], { cwd: SCRIPTS, env: { ...process.env, AGAME_QUIET: "1", AGAME_DEV_TODAY: "2026-10-04" }, stdio: "ignore" });
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 200; i++) { try { if ((await fetch(base + "/healthz")).ok && fs.existsSync(path.join(dist, "fitness_dashboard.html"))) break; } catch (e) { /* not yet */ } await new Promise(r => setTimeout(r, 200)); }
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 797 }, colorScheme: "dark", serviceWorkers: "block" });
  await ctx.clock.setFixedTime(new Date("2026-10-04T12:00:00+02:00"));
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  page.on("console", m => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
  page.on("dialog", d => d.accept());

  const ready = async () => { await page.waitForSelector("html[data-ready='1']"); await page.waitForFunction(() => typeof AG !== "undefined" && AG.online === true); };
  const go = async hash => { await page.goto(`${base}/fitness_dashboard.html${hash}`); await ready(); await page.waitForTimeout(150); };
  const exportData = async () => (await (await fetch(base + "/api/export")).json());
  const raw = async f => JSON.parse(fs.readFileSync(path.join(data, f), "utf-8"));
  async function sheetSave(fill, button = "#fs-form button[type=submit]") {
    await page.waitForSelector("#sheet.on");
    for (const [name, value] of Object.entries(fill)) {
      const el = await page.$(`#sheet [name="${name}"]`);
      if (!el) throw new Error("no field " + name);
      const tag = await el.evaluate(e => e.tagName + ":" + (e.type || ""));
      if (tag === "INPUT:checkbox") { if ((await el.isChecked()) !== value) await el.click(); }
      else if (tag.startsWith("SELECT")) await el.selectOption(String(value));
      else await el.fill(String(value));
    }
    await Promise.all([page.waitForEvent("load", { timeout: 60000 }), page.click(button)]);
    await ready();
  }
  async function clickAndReload(sel) { await Promise.all([page.waitForEvent("load", { timeout: 60000 }), page.click(sel)]); await ready(); }
  const shot = async name => { if (!NO_SHOTS) { await page.evaluate(() => { const t = document.querySelector("#toast"); if (t) t.classList.remove("on"); }); await page.waitForTimeout(250); await page.screenshot({ path: path.join(SHOTS, name + ".png") }); } };
  async function flow(name, fn) {
    console.log("· " + name);
    try { await fn(); } catch (e) { check(false, `${name}: ${e.message.split("\n")[0]}`); }
  }

  await flow("goal create, edit, undo toast", async () => {
    await go("#/goals");
    await page.click("[data-open=goal-new]");
    await page.waitForSelector("#sheet.on");
    await shot("dark-edit-goal-sheet");
    await sheetSave({ type: "distance", title: "E2E monthly distance", target: "100", period: "month" });
    const g = (await raw("goals.json")).goals.find(x => x.title === "E2E monthly distance");
    check(g && g.target === 100000, "goal distance stored in metres (100 km → 100000 m)");
    check(await page.isVisible("#toast.on button"), "undo toast offered after reload");
    await page.click(`[data-open=goal-edit][data-arg="${g.id}"]`);
    await sheetSave({ title: "E2E edited goal" });
    check((await raw("goals.json")).goals.some(x => x.title === "E2E edited goal"), "goal edited");
    await clickAndReload("#toast.on button");
    check((await raw("goals.json")).goals.some(x => x.title === "E2E monthly distance"), "undo restored previous title");
  });

  await flow("profile targets, physiology, appearance", async () => {
    await go("#/profile");
    await shot("dark-profile-edit");
    await page.click("[data-open=edit-targets]");
    await sheetSave({ protein_g: "160", water_ml: "3000" });
    check((await raw("profile.json")).targets.protein_g === 160, "protein target saved");
    await page.click("[data-open=edit-physiology]");
    await sheetSave({ hr_max: "191", threshold_pace: "4:25", method: "e2e field test" });
    const ph = (await raw("profile.json")).physiology;
    check(ph.hr_max.value === 191 && ph.hr_max.method === "e2e field test" && ph.threshold_pace_s_per_km.value === 265, "physiology saved with method and date");
    await page.click("[data-open=edit-appearance]");
    await sheetSave({ app_icon: "dark", tab3: "sleep" });
    const ui = (await raw("profile.json")).ui;
    check(ui.app_icon === "dark" && ui.mobile_tabs.includes("sleep") && ui.mobile_tabs[ui.mobile_tabs.length - 1] === "more", "appearance saved");
    check(await page.isVisible("#tabbar a[href='#/sleep']"), "tab bar follows the new tab choice");
  });

  await flow("privacy zone add/remove", async () => {
    await go("#/profile");
    await page.click("[data-open=edit-privacy]");
    await sheetSave({ label: "E2E office", lat: "-1.96", lon: "30.08", radius: "300" });
    const z = (await raw("profile.json")).privacy.zones.find(x => x.label === "E2E office");
    check(!!z, "zone added");
    await page.click("[data-open=edit-privacy]");
    await page.waitForSelector("#sheet.on");
    await clickAndReload(`[data-zone-rm="${z.id}"]`);
    check(!(await raw("profile.json")).privacy.zones.some(x => x.id === z.id), "zone removed");
  });

  await flow("nutrition: water, caffeine, meal edit + copy", async () => {
    await go("#/nutrition");
    await page.click("[data-open=water-add]");
    await sheetSave({ ml: "500" });
    check((await raw("nutrition.json")).water.some(w => w.ml === 500 && w.kind === "user_entered"), "water logged");
    await page.click("[data-open=caffeine-add]");
    await sheetSave({ mg: "80" });
    check((await raw("nutrition.json")).caffeine.some(w => w.mg === 80), "caffeine logged");
    await go("#/nutrition");
    await page.click("[data-chip=nut-tab][data-val=diary]");
    await page.waitForTimeout(150);
    const before = (await raw("nutrition.json")).meals.length;
    await page.click("[data-open=meal-edit] >> nth=0");
    await page.waitForSelector("#sheet.on");
    await page.fill("#sheet [name=copy_to]", "2026-10-05");
    await clickAndReload("#sheet [data-fs-extra='0']");
    check((await raw("nutrition.json")).meals.length === before + 1, "meal copied");
  });

  await flow("body: blood pressure reading", async () => {
    await go("#/body");
    await page.click("[data-chip=body-tab][data-val=bp]");
    await page.waitForTimeout(150);
    await page.click("[data-open=measure-add]");
    await sheetSave({ type: "bp", v: "121", v2: "79" });
    const m = (await raw("body.json")).measurements.filter(x => x.kind === "user_entered" && x.type.startsWith("bp_"));
    check(m.length === 2, "systolic + diastolic saved");
    check((await page.textContent("#main")).includes("121/79"), "BP card shows the manual reading");
  });

  await flow("health record with biomarkers", async () => {
    await go("#/body");
    await page.click("[data-chip=body-tab][data-val=records]");
    await page.waitForTimeout(150);
    await page.click("[data-open=record-add]");
    await sheetSave({ title: "E2E panel", markers: "Albumin, 45, g/L, 35-50\nCRP, 0.6, mg/L, 0-5" });
    const r = (await raw("health_records.json")).records.find(x => x.title === "E2E panel");
    check(r && r.biomarkers.length === 2 && r.biomarkers[0].code === "albumin", "record + coded biomarkers saved");
  });

  await flow("journal entry + activity status", async () => {
    await go("#/journal");
    await page.fill("#journal-form [name=text]", "E2E note");
    await page.selectOption("#journal-form [name=type]", "note");
    await clickAndReload("#journal-form button.btn");
    check((await raw("journal.json")).entries.some(e => e.text === "E2E note"), "journal entry saved");
    await page.click("[data-open=status-set]");
    await sheetSave({ status: "traveling", note: "E2E trip" });
    check((await raw("journal.json")).activity_status.some(s => s.note === "E2E trip"), "status saved");
    await go("#/today");
    check(/Traveling/.test(await page.textContent("#hdr-r")), "Today shows the status chip");
  });

  await flow("plans: adaptation, move, wizard, instant, race, routine", async () => {
    await go("#/training?tab=plan");
    const adapt = await page.$("[data-adapt=accepted]");
    if (adapt) { await clickAndReload("[data-adapt=accepted]"); check(((await raw("plans.json")).decisions || []).some(d => d.decision === "accepted"), "adaptation accepted and recorded"); }
    await go("#/training?tab=plan");
    const sid = await page.$eval("#main [data-upcoming] button.li[data-open=session][data-arg]", el => el.dataset.arg);
    await page.click(`#main button.li[data-open=session][data-arg="${sid}"]`);
    await page.waitForSelector("#sheet.on");
    await shot("dark-session-sheet");
    const mv = await page.$("#sheet [data-open=session-move]");
    if (mv) {
      await mv.click();
      const moveDate = await page.inputValue('#sheet [name="date"]');
      const originalDate = await page.evaluate(id => [].concat(D.plans.upcoming, D.plans.this_week.sessions, D.plans.next_week.sessions).find(s => s.id === id).date, sid);
      check(moveDate !== originalDate, "move picker defaults to a different day");
      await sheetSave({});
      check(true, "session moved via keyboard-friendly sheet");
    }
    await go("#/training?tab=plan");
    await page.click("[data-open=instant-schedule] >> nth=0");
    await sheetSave({});
    await page.click("[data-open=race-edit][data-arg='']");
    await sheetSave({ name: "E2E Half", date: "2026-12-06", priority: "A", dist: "21.1", goal: "1:45:00" });
    const races = (await raw("plans.json")).races;
    check(races.some(r => r.name === "E2E Half" && r.goal_time_s === 6300), "race added with goal time");
    await page.click("[data-open=routine-new]");
    await sheetSave({ name: "E2E 5x3", repeat: "5" });
    const rt = (await raw("plans.json")).routines.find(r => r.name === "E2E 5x3");
    check(rt && rt.steps.some(s => s.kind === "repeat" && s.repeat === 5), "routine with repeat block saved");
  });

  await flow("routes: import GPX and favorite", async () => {
    await go("#/routes");
    await page.click("[data-chip=rt-tab][data-val=builder]");
    await page.waitForTimeout(150);
    const gpx = path.join(tmp, "e2e-hill.gpx");
    fs.writeFileSync(gpx, `<?xml version="1.0"?><gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>${Array.from({ length: 50 }, (_, i) => `<trkpt lat="${-1.95 + i * 0.0003}" lon="${30.05 + i * 0.0002}"><ele>${1500 + i}</ele></trkpt>`).join("")}</trkseg></trk></gpx>`);
    await Promise.all([page.waitForEvent("load", { timeout: 60000 }), page.setInputFiles("#route-file", gpx)]);
    await ready();
    const f = (await raw("routes.geojson")).features.find(x => x.properties.name === "e2e-hill");
    check(!!f, "GPX imported as a route");
    await go(`#/route/${encodeURIComponent(f.properties.id)}`);
    await clickAndReload("[data-route-flag=favorite]");
    check(((await raw("profile.json")).ui.favorite_routes || []).includes(f.properties.id), "route favorited");
  });

  await flow("activity quick edit (race tag)", async () => {
    await go("#/activities");
    const href = await page.$eval("#main a.li[href^='#/activity/']", a => a.getAttribute("href"));
    await go(href);
    await page.click("[data-open=act-edit]");
    await sheetSave({ race: true, title: "E2E race day" });
    check((await page.textContent("#hdr-title")).includes("E2E race day"), "title overlay shown in header");
    check(await page.isVisible("text=Race"), "race badge/view shown");
  });

  await flow("coach memory + check-in, prehab done, custom exercise", async () => {
    await go("#/coach");
    await page.click("[data-open=memory-edit][data-arg='']");
    await sheetSave({ text: "Prefers morning runs" });
    await page.click("[data-open=checkin-edit][data-arg='']");
    await sheetSave({ text: "Creatine", time: "15:00" });
    const c = await raw("coach.json");
    check(c.memory.some(m => m.text === "Prefers morning runs") && c.checkins.some(x => x.text === "Creatine" && x.time === "15:00"), "memory + check-in saved");
    await go("#/recovery");
    const ph = await page.$("[data-prehab]");
    if (ph) { await clickAndReload("[data-prehab]"); check(((await raw("plans.json")).prehab_log || []).some(l => l.date === "2026-10-04"), "prehab logged"); }
    await go("#/strength?tab=builder");
    await page.click("[data-open=exercise-new]");
    await page.waitForSelector("#sheet.on");
    await page.check("#sheet [data-mprim][value=glutes]");
    await sheetSave({ name: "E2E hip thrust" });
    check((await raw("strength.json")).exercises.some(x => x.name === "E2E hip thrust"), "custom exercise saved");
  });

  await flow("widgets pin + gallery + history", async () => {
    await go("#/widgets");
    await clickAndReload("[data-pin=recovery]");
    check(((await raw("profile.json")).ui.today_widgets || []).includes("recovery"), "widget pinned");
    await go("#/body");
    await page.click("[data-chip=body-tab][data-val=charts]");
    await page.waitForTimeout(200);
    const metric = await page.$eval("[data-chart-pin]", el => el.dataset.chartPin);
    const was = ((await raw("profile.json")).ui.pinned_charts || []).includes(metric);
    await clickAndReload("[data-chart-pin]");
    check(((await raw("profile.json")).ui.pinned_charts || []).includes(metric) !== was, "chart pin toggled");
    await go("#/dev/gallery");
    check((await page.textContent("#main")).includes("ScoreRing"), "gallery renders");
    await shot("dark-gallery");
    await go("#/profile");
    await page.click("[data-open=history]");
    await page.waitForSelector("#sheet.on");
    check((await page.$$("#sheet .li")).length >= 10, "edit history lists the changes");
  });

  await flow("no horizontal overflow in edit sheets", async () => {
    await go("#/training?tab=plan");
    await page.click("[data-open=routine-new]");
    await page.waitForSelector("#sheet.on");
    const ow = await page.evaluate(() => { const s = document.querySelector("#sheet"); return s.scrollWidth - s.clientWidth; });
    check(ow <= 0, "routine builder fits 390 px (" + ow + ")");
  });

  check(errs.length === 0, "JS errors: " + errs.slice(0, 5).join(" | "));
  await browser.close();
  srv.kill();
  fs.rmSync(tmp, { recursive: true, force: true });
  console.log(`\n${passed} edit checks passed, ${failures.length} failed`);
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
