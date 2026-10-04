# AGame

A private fitness dashboard for one person. It combines the paid features of Strava and Bevel Intelligence (plus ideas from Athletica.ai), and runs on your own Apple HealthKit data. Your agent **Steve** imports that data every morning before 06:00 CAT.

AGame shows fitness information. It is **not** medical advice and never diagnoses anything.

- **On iPhone:** an installable web app (PWA) with tabs for Today · Training · Activities · Coach · More.
- **On desktop:** the same app with a sidebar.
- **Behind it:** a small Python server that handles sign-in, edits, and rebuilds.

Everything runs on the Python 3.11+ standard library. The only optional extra is the `anthropic` package, for Coach chat.

> This repository is **public**. It holds code, schemas and **empty** example files only. Your real health data lives in a separate private folder (or private repo) that you point AGame at with `AGAME_DATA_DIR`.

![Today on iPhone, dark](docs/screenshots/dark-today.png)

---

## Contents

1. [Quick start](#1-quick-start)
2. [How it works](#2-how-it-works-architecture)
3. [Commands](#3-commands)
4. [Steve's runbook](#4-steves-runbook)
5. [Data contract](#5-data-contract)
6. [Calculations](#6-calculations)
7. [Deployment (Railway)](#7-deployment-railway)
8. [Features and screens](#8-features-and-screens)
9. [Features waiting on data or services](#9-features-waiting-on-data-or-services)
10. [Tests](#10-tests)
11. [Known limitations](#11-known-limitations)

---

## 1. Quick start

```bash
# Look at the app with made-up data (nothing personal):
cd scripts
python3 -m agame.synthetic --out /tmp/agame-demo --date 2026-10-04
python3 build_dashboard.py --date 2026-10-04 --data-dir /tmp/agame-demo --out /tmp/agame-dist
open /tmp/agame-dist/fitness_dashboard.html      # or double-click it

# Or run the local server (no sign-in, bound to 127.0.0.1 only):
python3 fitness_server.py --dev --data-dir /tmp/agame-demo --dist-dir /tmp/agame-dist
# → http://127.0.0.1:8080
```

The built HTML file is self-contained. You can open it straight from disk, and it works offline. Edits (logging meals, RPE, goals and so on) need the server.

---

## 2. How it works (architecture)

```
iPhone HealthKit ──► Steve ──► batch.json ──► update_from_healthkit.py ──► AGAME_DATA_DIR/*.json
                                                                                    │
                    owner edits in the app ──► fitness_server.py (/api/entries) ────┤
                                                                                    ▼
                                                 build_dashboard.py  (validate → compute → render)
                                                                                    │
                                    dist/fitness_dashboard.html  (+ build_report.json, morning_summary.json,
                                                                   weekly_review.json, widgets.json, PWA files)
```

Think of it like a kitchen. The data folder is the pantry. Python is the cook. The HTML page is the plate: it only serves what the cook made.

- **One source of truth for numbers.** Every score is calculated once, in Python (`scripts/agame/compute/`). The browser only draws the results. A test fails if JavaScript contains formula patterns.
- **Every number carries its context.** Each value is an object: `{v, unit, kind, as_of, status}`.
  - `kind` is one of: observed, configured, computed, estimated, user_entered.
  - `status` is one of: ok, partial, stale, missing, calibrating.
  - Missing data shows as "—" with a reason. It is never shown as 0.
- **No hard-coded people or targets.** Names, dates, zones, thresholds and targets come from data files or `config/defaults.json`. Even Steve's name comes from config (`sync.agent_name`).
- **Imports are immutable.** HealthKit records keep their `source_id` and are never edited in place. Your own entries are `kind: user_entered` and can be edited, undone, exported and deleted. Every change is logged with before/after values.
- **Nothing sensitive before sign-in.** The server shows only a sign-in page and `/healthz` until the owner signs in with Google (OpenID Connect).
- **Map privacy.** Privacy zones and start/end trimming are applied in Python, so raw coordinates never reach the HTML.
- **Edits are named actions, not browser logic.** Simple edits go to `/api/entries/<collection>`. Anything that needs a decision goes to `/api/actions/<name>` (`scripts/agame/actions.py`), for example turning a template session into a real one, applying a Workout Wizard pick, copying a day of meals, or accepting a threshold. One action is one undo step.

| Folder | What's in it |
|---|---|
| `scripts/agame/` | The Python package: loading, validation, importer, build, server, auth, entries |
| `scripts/agame/compute/` | All calculations, one module per area (load, recovery, sleep, strain, body, activity, goals, muscles, nutrition, plans, routes, insights, extras) |
| `scripts/agame/web/` | CSS, the JS screens and the HTML template, inlined into one file at build time |
| `config/defaults.json` | Every algorithm parameter (no personal data). `profile.json` → `overrides` can change any of them |
| `config/exercises.json` | Exercise library with primary/secondary muscles |
| `schemas/` | JSON Schemas, generated by `python3 -m agame.schema_defs --write` (run from `scripts/`) |
| `data/` | Empty, schema-valid fixtures only. Safe for a public repo |
| `scripts/tests/`, `scripts/e2e/` | Unit/integration tests, browser tests, Steve dry run |
| `docs/build-plan.md` | Research, the 57-issue plan and the full feature matrix |
| `docs/design.md` | Design rules for every screen. Read before changing the UI |
| `docs/screenshots/` | Screenshots from synthetic data |

---

## 3. Commands

Run these from the repo root. Each one prints `--help`.

| Command | What it does | Exit codes |
|---|---|---|
| `python3 scripts/update_from_healthkit.py --date YYYY-MM-DD --input batch.json [--data-dir DIR] [--dry-run]` | Merges Steve's batch. Safe to repeat (idempotent). All-or-nothing | 0 applied or already imported · 2 applied but some records conflicted · 1 rejected, nothing written · 3 data dir not found |
| `python3 scripts/validate_data.py DIR [--date YYYY-MM-DD] [--json]` | Checks schemas and impossible values | 0 valid · 1 invalid · 3 usage |
| `python3 scripts/build_dashboard.py --date YYYY-MM-DD [--data-dir DIR] [--out DIR] [--quiet]` | The one build command. Writes `dist/` and `dist/build_report.json` | 0 ok · 2 degraded (built, but data is partial or stale) · 1 failed (previous build kept) · 3 usage |
| `python3 scripts/fitness_server.py [--dev] [--port N] [--data-dir DIR] [--dist-dir DIR]` | Server: sign-in, edits, rebuilds, snapshot upload | Refuses to start without its env vars unless `--dev` |
| `AGAME_UPLOAD_TOKEN=… python3 scripts/push_snapshot.py --url https://your-app` | Sends the data files to the deployed server, which validates them and rebuilds | 0 ok/degraded · 1 rejected |
| `python3 scripts/fitness_pwa.py --out dist/` | Regenerates only the PWA files (the build already does this) | |
| `python3 -m agame.synthetic --out DIR --date YYYY-MM-DD [--missing-last-sleep]` (from `scripts/`) | Makes 200 days of fake data for demos and tests | |
| `python3 scripts/run_tests.py [--out dist/]` | Unit and integration tests, modules in parallel (~35 s). Writes `dist/test_report.json` | 0 pass · 1 fail |
| `python3 -m unittest discover scripts/tests -p 'test_*.py'` | Same tests, one process (~90 s) | |
| `python3 scripts/import_strength_csv.py export.csv [--map names.json] [--unit lb] [--dry-run]` | Imports a Strong, Hevy or generic sets CSV into `strength.json`. Safe to repeat. Unknown exercise names are skipped and listed (muscles are never guessed) | 0 imported · 2 imported, some exercises skipped · 1 rejected · 3 usage |
| `python3 scripts/coach_maintenance.py [--dry-run]` | Nightly: removes duplicate Coach memories (one undo step) and trims old chat threads | 0 · 1 data unreadable |
| `python3 scripts/due_checkins.py [--now ISO] [--window-min 15]` | Lists check-ins due now, with the computed facts to include | 0 |
| `NODE_PATH=$(npm root -g) node scripts/e2e/edit_flows.js [--no-shots]` | Browser tests of every edit flow against the dev server | 0 pass · 1 fail |
| `NODE_PATH=$(npm root -g) node scripts/e2e/e2e.js [--no-shots]` | Browser tests and screenshots (needs Node Playwright + Chromium) | 0 pass · 1 fail |
| `python3 scripts/e2e/steve_dry_run.py` | Rehearses four mornings of Steve's routine | 0 pass · 1 fail |

`AGAME_DATA_DIR` and `AGAME_DIST_DIR` work as defaults for `--data-dir`, `--out` and `--dist-dir`.

---

## 4. Steve's runbook

Steve only touches data files and runs commands. **Steve never edits UI code to change a number.** If a number looks wrong, the fix belongs in the data or in `config/defaults.json`, made by the owner.

### Every morning (before 06:00 CAT)

```bash
export AGAME_DATA_DIR=~/agame-data          # the private data folder or repo
D=$(TZ=Africa/Kigali date +%F)

python3 scripts/update_from_healthkit.py --date "$D" --input ~/healthkit/batch-$D.json
python3 scripts/validate_data.py "$AGAME_DATA_DIR" --date "$D"
python3 scripts/build_dashboard.py --date "$D" --quiet
cat dist/build_report.json                     # read status, degraded_reasons, errors
cat dist/morning_summary.json                  # recovery, sleep, today's call, one action

# If deployed: send the data to the server (it validates and rebuilds there too)
python3 scripts/push_snapshot.py --url "$AGAME_BASE_URL"
# Then commit the private data folder:
git -C "$AGAME_DATA_DIR" add -A && git -C "$AGAME_DATA_DIR" commit -qm "HealthKit $D" && git -C "$AGAME_DATA_DIR" push -q
```

### What to do with each result

| Step | Result | What Steve does |
|---|---|---|
| Import | `0` + `applied` | Continue |
| Import | `0` + `already_imported` | Nothing changed (a re-send is harmless). Continue |
| Import | `2` (conflicts) | New records went in. Records whose `source_id` already existed with different content were **not** changed. Report the `conflicts` list to the owner. Continue |
| Import | `1` (rejected) | Nothing was written. Read `error`/`errors`, fix the batch (e.g. missing `source_id`, impossible heart rate, naive timestamp), and re-run. Do not hand-edit data files |
| Validate | `1` | Stop. Report the errors. Do not build |
| Build | `0` ok | Done. Send the morning summary |
| Build | `2` degraded | The dashboard was still built. Read `degraded_reasons` (e.g. "last night's sleep not synced yet"). Re-run import + build once more data arrives. The app shows honest "stale"/"not synced" states meanwhile |
| Build | `1` failed | The previous dashboard is kept. Read `errors` in `build_report.json`, report them, and fix the data, not the code |

### Through the day

```bash
python3 scripts/due_checkins.py          # every 15 minutes: deliver what it prints (message + facts)
```

### Every night

```bash
python3 scripts/coach_maintenance.py     # de-duplicate Coach memory, trim old threads
python3 scripts/run_tests.py             # optional: proves the code before any deploy (dist/test_report.json)
```

When the owner exports workouts from a lifting app, import them with `import_strength_csv.py` (it never guesses muscles; add a `--map` file for names it doesn't know).

### Every Monday

Read `dist/weekly_review.json` (the last completed week: load, sleep, recovery, goals, highlights). Send it to the owner as the weekly review. Check-ins and nudges listed in `coach.json → checkins` are Steve's to deliver on their schedule.

### Backup and rollback

- The private data folder is the backup. Commit it after every morning, and keep it in a **private** repository.
- `dist/snapshots/` keeps the last 7 built dashboards. To roll back the view, pin one: `echo 2026-10-03 > dist/pin.txt` (or set `AGAME_PIN_SNAPSHOT=2026-10-03` on the server). The server then serves that snapshot until the pin is removed. `/api/build-report` shows the active pin.
- To roll back data, run `git -C "$AGAME_DATA_DIR" revert <commit>` and rebuild.
- Edits made in the app are in `edit_history.jsonl` (in the data folder). Undo them from the app or with `POST /api/undo`.

### Dry run (verified)

`scripts/e2e/steve_dry_run.py` runs exactly this routine on synthetic data:

| Morning | Import | Build |
|---|---|---|
| 2 Oct: first install, full backfill | 0 · applied | 0 · ok |
| 3 Oct: normal batch | 0 · applied | 0 · ok |
| 3 Oct: same batch re-sent | 0 · already_imported, data folder byte-identical | 0 · ok |
| 4 Oct: sleep not synced yet | 0 · applied | 2 · degraded, "last night's sleep not synced yet" |

---

## 5. Data contract

### Files

All files live in `AGAME_DATA_DIR`. Every file has the same envelope:

```json
{ "schema_version": "1.0.0", "domain": "sleep", "generated_at": "2026-10-04T05:40:00+02:00",
  "as_of": "2026-10-04T05:49:36+02:00", "source": "healthkit", "fixture": false, "status": "ok", "coverage": null, … }
```

`fixture` is `false` for real data, `"empty"` for the repo's empty files, and `"synthetic"` for test data. Every timestamp **must** include a timezone offset; timestamps without one are rejected.

| File | Written by | Holds |
|---|---|---|
| `profile.json` | Owner (app) | Athlete basics, locale/timezone, physiology (HR max, LTHR, threshold pace, FTP, sleep need — each with `value`, `date`, `method`, `kind`), zones model, targets, privacy zones, modules, UI, integrations, coach settings, `overrides` for config |
| `current.json` | Importer | Sync manifest per domain (`last_sync`, `last_sample`, `expected_for`, `received`, `status`, `note`) and the import log |
| `metrics.json` | Importer | `series.<id>`: points `{t or date, v, source_id, source}` (ids in `config/defaults.json → metrics_catalog`). Unknown series need `series_meta.<id>.unit` |
| `sleep.json` | Importer | `nights`: `{source_id, date, start, end, is_nap, segments:[{stage, start, end}]}`. Stages: in_bed, awake, core, deep, rem, asleep_unspecified |
| `workouts.json` | Importer | `workouts`: `{source_id, sport, start, end, distance_m, avg_hr, max_hr, kcal, route_id, samples:{t, hr, dist_m, elev_m, speed_mps, power_w, cadence, lat, lon, …}, laps, segments, weather, tags}` |
| `routes.geojson` | Importer | GeoJSON LineStrings `[lon, lat, ele]` with `properties.id`. Workouts point to them with `route_id` |
| `body.json` | Importer + owner | `measurements`: `{source_id, t, type: weight_kg/body_fat_pct/lean_mass_kg/waist_cm/bmi, v, kind}` |
| `nutrition.json` | Importer + owner | `meals` (with `items` and macros), `water`, `caffeine`, `recipes`, `planned_meals`, `connected` |
| `load.json` | Owner | `annotations`: per-workout RPE, feel, comment (one per workout) |
| `strength.json` | Owner | `exercises` (custom), `sessions` (sets × reps × kg, RPE), `routines`, `live_state` (companion contract) |
| `goals.json` | Owner | Goals: `type`, `target`, `period`, `direction`, `start_value`, `status` |
| `plans.json` | Owner | `sessions`, `templates`, `races`, `calendar`, `routines` (structured steps), `prehab`, `prehab_log` |
| `journal.json` | Owner | `entries` (mood, symptoms, notes…), `habits`, `activity_status` (sick, travel, injured…), `cycle` |
| `health_records.json` | Owner | Lab results, notes, documents; `biomarkers: [{name, code, value, unit, ref_low, ref_high}]` |
| `social.json` | Contract | athletes, follows, clubs, posts, kudos, comments, challenges, segment efforts |
| `coach.json` | Server + owner | Threads, memory, check-ins |

**Owner additions in this version:**
- `body.json` accepts manual blood pressure as `bp_systolic_mmhg` / `bp_diastolic_mmhg` measurements (`kind: user_entered`). These join the HealthKit series.
- `profile.ui` has `favorite_routes`, `offline_routes`, `today_widgets` and `pinned_charts`.
- `plans.json → decisions` records which suggested plan changes you accepted or declined.
- Imported GPX/GeoJSON routes are features with `properties.source: "import"`.

The exact rules for every field are in `schemas/*.schema.json`. The validator also checks things a schema can't:
- impossible values (e.g. HR over 250, sleep longer than 24 h, speed impossible for the sport)
- duplicate IDs
- timestamps in the future
- unknown timezones, unknown exercises or muscles
- broken route links
- sample arrays of different lengths

**Versions.** Older `schema_version`s with the same major version are migrated in memory, with a warning. A **newer** version than the code knows is a hard failure (AGame never guesses).

### HealthKit batch (what Steve sends)

```json
{
  "batch_version": 1,
  "date": "2026-10-04",
  "generated_at": "2026-10-04T05:40:00+02:00",
  "source": "healthkit",
  "samples": {
    "metrics":   { "resting_hr_bpm": [ {"date": "2026-10-04", "v": 50.7, "source_id": "HK-…"} ],
                   "hrv_sdnn_ms":    [ {"t": "2026-10-04T05:30:00+02:00", "v": 48.4, "source_id": "HK-…"} ] },
    "sleep":     [ { "source_id": "HK-…", "date": "2026-10-04", "start": "…", "end": "…", "segments": [ … ] } ],
    "workouts":  [ { "source_id": "HK-…", "sport": "run", "start": "…", "end": "…", "samples": { … } } ],
    "body":      [ { "source_id": "HK-…", "t": "…", "type": "weight_kg", "v": 83.0 } ],
    "nutrition": { "meals": [ { "id": "…", "source_id": "HK-…", … } ], "water": [ … ], "caffeine": [ … ] },
    "routes":    [ { "type": "Feature", "properties": { "id": "route-…" }, "geometry": { … } } ]
  },
  "series_meta": { }
}
```

Rules:
- Every record needs a `source_id` (meals also need an `id`).
- A batch may not contain `kind: user_entered` records. Those are made in the app.
- The idempotency key is the date plus a hash of all source IDs. Sending the same batch twice is a no-op.
- A record whose `source_id` already exists is skipped if identical. If its content differs, it is reported as a conflict and **not** applied.
- The merged result is validated **before** anything is written. If it fails, nothing is written.
- Workouts, weigh-ins and meals are event-based: no new ones is normal. A missing night of sleep, though, is flagged as "Sleep not synced yet".

### Outputs (in `dist/`)

| File | For |
|---|---|
| `fitness_dashboard.html` | The app (data embedded) |
| `build_report.json` | Steve: `status`, `exit_code`, `errors`, `warnings`, `degraded_reasons`, per-domain `freshness`, input and output hashes |
| `morning_summary.json` | Steve: recovery, sleep, today's call, one action, data status |
| `weekly_review.json` | Steve, Mondays |
| `widgets.json` | Home-screen widget contract |
| `manifest.webmanifest`, `fitness_sw.js`, `icons/` | PWA |
| `snapshots/YYYY-MM-DD.html` | The last 7 builds |

The same inputs always give byte-identical outputs. This is tested.

---

## 6. Calculations

All parameters are in `config/defaults.json`. Each metric is registered once (`@metric` in `scripts/agame/compute/`), with its method name and inputs. The list is embedded as `meta.metrics_registry`.

| Metric | How it's calculated |
|---|---|
| **HR zones** | 5 zones as % of HR max (default), or 7 zones as % of LTHR, or your own bounds. HR max must be observed or configured. **There is no age-based guess**: without HR max, zones stay empty |
| **Session load (TRIMP)** | Banister TRIMP from the heart-rate stream (gaps capped). Fallback 1: average HR (marked estimate). Fallback 2: RPE × minutes × a factor learned from your own sessions (default until ≥ 10 paired sessions). Sex-specific constants when sex is set |
| **Fitness / Fatigue / Form** | Fitness = 42-day exponential average of daily load. Fatigue = 7-day average. Form (day d) = Fitness(d−1) − Fatigue(d−1). "Calibrating" for the first 42 days |
| **Cardio status** | From Form and the 7-day change in Fitness: overreaching, fatigued, productive, maintaining, detraining, calibrating. Plus a 14-day form forecast from planned sessions |
| **Recovery** | HRV (log scale) and resting HR, each scored against your own 60-day baseline (z-score), plus sleep debt, respiratory rate and yesterday's strain. Needs ≥ 14 days of baseline. Confidence is high, medium or low. Missing inputs lower coverage; they are never filled in |
| **Sleep** | Score from duration vs need, efficiency, consistency, stages and disruptions. Need = your base + extra after high strain + part of the debt. Debt = last 7 nights, older nights count less. Regularity = midpoint spread and SRI |
| **Strain** | Daily load mapped onto 0–100% with a saturating curve. The scale is your own 90th percentile once there is enough history |
| **Stress** | Daytime heart rate above resting, as % of HR reserve. Always labelled an estimate |
| **Energy Bank** | Starts from recovery, drains with strain and stress, refills with sleep. Stops at the last sample (no projection) |
| **Weight** | 7-day median "current", 28-day linear trend, required vs actual rate for a goal date, projected date, status ahead / on track / behind |
| **VO2 max** | Shown only from Apple Watch samples (smoothed). Never estimated from pace |
| **Activity** | Splits, GAP (Minetti energy-cost model), best efforts (exact interpolated window search), HR and power curves, efficiency factor, % of threshold, aerobic decoupling, interval detection, matched runs (route shape), Riegel race predictions |
| **Muscles** | Only from logged exercises (sets × RPE → primary/secondary muscles). Load status from acute vs chronic ratio, freshness from decayed fatigue. Generic "strength workout" entries add nothing per muscle. Running and other cardio can add an approximate leg load (configurable, labelled) |
| **Nutrition score** | Protein, energy balance, fibre, vegetables, hydration, caffeine timing. Today's score is marked partial until the day ends |
| **Biological age** | Levine PhenoAge from the nine blood markers when all are present. Otherwise a labelled heuristic from VO2 max, resting HR, HRV and sleep. Hidden without inputs |
| **Insights** | Rule-based, each with its evidence. Correlations below the minimum strength say "no clear effect". Medical words are banned (tested) |

---

## 7. Deployment (Railway)

The Docker image holds code only, with no data and no secrets. Data lives on a volume.

1. **Google sign-in.** In Google Cloud Console → APIs & Services → Credentials, create an OAuth client (type Web application). Set the redirect URI to `https://<your-app>/auth/callback`.
2. **Railway.** Create a service from this repo (it uses the `Dockerfile` and `railway.toml`). Then:
   - attach a **volume mounted at `/data`**
   - set these variables (names are also in `.env.example`):

| Variable | Value |
|---|---|
| `AGAME_OIDC_ISSUER` | `https://accounts.google.com` |
| `AGAME_OIDC_CLIENT_ID` / `AGAME_OIDC_CLIENT_SECRET` | From step 1 |
| `AGAME_OWNER_EMAIL` | The only Google account allowed in |
| `AGAME_SESSION_SECRET` | 32+ random characters (`python3 -c "import secrets;print(secrets.token_urlsafe(48))"`) |
| `AGAME_BASE_URL` | `https://<your-app>` (HTTPS turns on Secure cookies and HSTS) |
| `AGAME_UPLOAD_TOKEN` | Random token Steve uses for `push_snapshot.py` |
| `AGAME_LLM_PROVIDER`, `ANTHROPIC_API_KEY` | Optional Coach chat: set the provider to `anthropic`, and build with `INSTALL_COACH=1` (Railway: add it as a build variable). Model defaults to `claude-opus-5-5`; override with `AGAME_LLM_MODEL` |

3. On first boot, the container fills the empty volume with the empty fixtures. It then drops to the unprivileged user `agame` and starts the server. The health check is `/healthz`.
4. Steve sends data with `push_snapshot.py --url https://<your-app>`. The server validates the whole upload first: a bad upload changes nothing.
5. **Rollback.** Redeploy an earlier image in Railway. Data is on the volume and in Steve's private repo, so a code rollback never loses data.

Locally with Docker: `docker build -t agame . && docker run -p 8080:8080 -v agame-data:/data --env-file .env agame`.

**Security headers:**
- strict CSP (no external scripts or images), `frame-ancestors 'none'`, `nosniff`, `no-referrer`
- `no-store` on API responses
- HttpOnly + SameSite=Lax session cookies
- edits need JSON and a same-origin request
- sessions are signed with HMAC and rotate daily

---

## 8. Features and screens

Destinations: **Today** (with Strain, Timeline), **Training** (Fitness, Log, Progress, Plan, Zones, Records, Recaps, Review), **Activities** (list, social, detail: Summary / Analysis / Chat / Planned), **Recovery**, **Sleep**, **Strength** (Overview, History, Exercises, Builder, Records), **Nutrition**, **Body**, **Routes** (library, route detail, heatmap, segments), **Goals**, **Coach**, **Profile**, **Journal**, **Widgets**.

"Built" means it works from HealthKit data and your own entries now. "Contract" means the screen and schema exist, and the screen shows an honest empty state until the named data or service is connected (see §9).

| Feature | From | Screen | Status |
|---|---|---|---|
| Relative effort (TRIMP), weekly vs 12-week range | Strava | Activities, Training, Today | Built (HR) · RPE fallback |
| Fitness / Fatigue / Form, cardio status, form forecast, overtraining warning | Strava, Bevel, Athletica | Training, Today | Built |
| Training log, totals, progress comparison | Strava | Training | Built |
| HR / pace zones, 7-zone option, threshold candidates, zone distribution | Strava, Athletica | Training, Activity | Built |
| Splits, GAP, laps, intervals, HR curve, EF, decoupling, intensity | Strava, Bevel, Athletica | Activity | Built |
| Power curve | Strava | Activity | Built when power samples exist, empty otherwise |
| Matched runs, best efforts, PRs, top-10, race predictions | Strava | Activity, Training › Records | Built |
| Flyover replay, RPE / feel / notes, Quick Edit (title, race, private, tags), race view (goal and prediction vs finish) | Strava, Athletica | Activity | Built |
| Weather on activity | Strava | Activity | Contract |
| Goals, streaks | Strava | Goals, Today | Built |
| Calendar, Plan Your Week (drag or "Move to…"), compliance, templates, races A/B/C, events, plans with phases | Bevel, Athletica | Training › Plan | Built |
| Adaptive suggestions (accept / keep original), Workout Wizard, instant workouts (schedule) | Strava/Runna, Athletica | Training, Today | Built (rule-based) |
| Big Day Brief, pre-workout guidance | Athletica | Today | Built |
| Routines with structured steps · Apple Watch export | Bevel, Athletica | Training | Built · export is a contract |
| Year / month in sport with share card (PNG), weekly review | Strava, owner | Training › Recaps / Review | Built |
| Recovery with factors and confidence | Bevel | Today, Recovery | Built |
| Sleep score, need, debt, stages, regularity, bedtime | Bevel | Sleep, Today | Built |
| Strain, Stress (estimate), Energy Bank | Bevel | Today › Strain, Recovery | Built |
| Muscle load, freshness, muscle map | Bevel, Strava | Strength | Built from exercise logs |
| Strength builder, rest timer, plate calculator, history, custom exercises, routines | Bevel | Strength | Built |
| Strength-app import (Strong, Hevy, generic CSV) | Strava | `import_strength_csv.py` | Built |
| Weight trajectory, VO2 max, HRV, RHR, blood pressure, custom charts | Bevel, owner | Body | Built |
| Nutrition diary, macros, net energy, score, recipes | Bevel | Nutrition | Built once meals are logged or imported |
| Barcode / photo food logging, CGM | Bevel | Nutrition | Contract |
| Timeline, journal, activity status (sick / travel) | Bevel | Timeline, Journal | Built |
| Health records | Bevel | Body | Built (manual) |
| Biological age | Bevel | Body | Built when biomarkers or VO2 max data exist |
| Route library, privacy zones, heatmap (incl. night), own segments, GPX/GeoJSON import, favourites, offline | Strava | Routes | Built |
| Drawing routes on a map, leaderboards, live segments, feed, clubs, kudos | Strava | Routes, Activities › Social | Contract |
| Coach: today's call, helping / hurting, suggestions, memory, personalities, modes, Ghost mode | Bevel | Coach | Built |
| Coach: free-form Q&A and generated charts | Bevel, Strava | Coach, Activity › Chat | Contract (needs LLM key) |
| Widgets, pinned to a custom row on Today (desktop) | Bevel | Widgets, `widgets.json` | Built + export contract |
| Beacon, smart alarm | Strava, Bevel | Profile | Contract |
| Offline use, install to home screen | — | All | Built |
| Data freshness, provenance ("i" buttons), edit history with before/after, undo (toast and sheet), export, delete my entries | Brief | All, Profile | Built |
| Editing everything you own: profile, physiology, zones, targets, weekly template, appearance (theme, icon, tabs), privacy zones, modules, coach, goals, meals, water, caffeine, recipes, weigh-ins, blood pressure, health records with files, journal, status, habits, memory, check-ins, prehab | Brief | Each screen | Built |
| Component gallery (`#/dev/gallery`), WCAG AA contrast check | Plan | Dev | Built |

The original research matrix with issue numbers is in `docs/build-plan.md` §9.

### Screenshots

Taken from synthetic data at 390×797 (iPhone) in dark mode, plus Today in light mode and on desktop. They are in `docs/screenshots/` and regenerated by `scripts/e2e/e2e.js`.

| | | |
|---|---|---|
| ![](docs/screenshots/dark-today.png) | ![](docs/screenshots/dark-training.png) | ![](docs/screenshots/dark-activities.png) |
| ![](docs/screenshots/dark-activity-detail.png) | ![](docs/screenshots/dark-recovery.png) | ![](docs/screenshots/dark-sleep.png) |
| ![](docs/screenshots/dark-strength.png) | ![](docs/screenshots/dark-nutrition.png) | ![](docs/screenshots/dark-body.png) |
| ![](docs/screenshots/dark-routes.png) | ![](docs/screenshots/dark-goals.png) | ![](docs/screenshots/dark-coach.png) |
| ![](docs/screenshots/dark-profile.png) | ![](docs/screenshots/dark-strain.png) | ![](docs/screenshots/dark-timeline.png) |
| ![](docs/screenshots/dark-journal.png) | ![](docs/screenshots/dark-widgets.png) | ![](docs/screenshots/dark-more-sheet.png) |
| ![](docs/screenshots/light-today.png) | ![](docs/screenshots/dark-offline.png) | ![](docs/screenshots/dark-provenance-sheet.png) |
| ![](docs/screenshots/dark-profile-edit.png) | ![](docs/screenshots/dark-edit-goal-sheet.png) | ![](docs/screenshots/dark-session-sheet.png) |
| ![](docs/screenshots/dark-gallery.png) | ![](docs/screenshots/dark-training-plan.png) | ![](docs/screenshots/dark-route-detail.png) |

![Desktop](docs/screenshots/desktop-today.png)

---

## 9. Features waiting on data or services

Each of these already has a schema field and a screen. Supply the input below and the feature turns on at the next build, with no code change.

| Feature | Needs | Input contract |
|---|---|---|
| Power curve, power zones | A power source (running power from Apple Watch, or a cycling power meter) | `workouts[].samples.power_w` (array aligned with `samples.t`), and optionally `profile.physiology.ftp_w` `{value, date, method, kind}` |
| Weather on activities, heat-adjusted pace | A weather source | `workouts[].weather = {temp_c, humidity_pct, wind_kph, conditions, source}`. For plans: `plans.sessions[].forecast_temp_c` |
| Drawing routes on a map, base map under traces | A tile server you trust (private, no tracking) | `profile.integrations.map_tiles_url` (e.g. `https://tiles.example/{z}/{x}/{y}.png`) and `map_attribution`. Routes are drawn without a base map today; drawing tiles also needs that origin added to the CSP `img-src` (the hook is `Config.tiles_origin` in `server.py`) |
| Leaderboards, live segments, feed, clubs, kudos, friend challenges | Other people's consented data | `social.json`: `athletes`, `follows`, `clubs`, `posts`, `kudos`, `comments`, `challenges`, `segment_efforts`. No Strava API data may be used |
| Coach free-form Q&A and generated charts | An Anthropic API key | Server env: `AGAME_LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY`, image built with `INSTALL_COACH=1`. The model receives computed summaries from the snapshot only. Health records are sent only if `profile.coach.include_health_records` is true |
| Barcode and food database | A food database service | `profile.integrations.food_database` (service id). Meals still go in through `POST /api/entries/nutrition.meals` with `items[]` macros |
| Photo meal logging | A vision service | `profile.integrations.vision_service` |
| CGM / glucose | A glucose source in HealthKit | `metrics.series.glucose_mg_dl` points `{t, v, source_id}` |
| Biological age (PhenoAge) | A blood test | `health_records.records[].biomarkers` with codes `albumin`, `creatinine`, `glucose`, `crp`, `lymphocyte_pct`, `mcv`, `rdw`, `alp`, `wbc` (common units are converted), and `profile.athlete.birth_year` |
| Apple Watch workout install | A companion iOS app | Routines export as `agame.watch_workout.v1` (WorkoutKit-shaped: `displayName`, `activity`, `warmup`, `blocks[].steps[].goal/alert`, `cooldown`) |
| Live strength session on phone/watch | A companion app | `strength.live_state = {session_id, routine_id, started_at, exercise_index, set_index, rest_started_at, device}` |
| Calendar conflicts for planning | A calendar source | `plans.calendar[] = {id, start, end, title, busy, source}` and `profile.integrations.calendar_source` |
| Beacon (live location sharing), smart alarm | A companion app on the phone | `profile.beacon = {enabled, contacts[]}`, `profile.smart_alarm = {enabled, window_min, target_wake}` |
| Home-screen widgets on iOS | A widget app | Reads `dist/widgets.json` |

---

## 10. Tests

```bash
python3 scripts/run_tests.py                                   # 135 tests, ~35 s, writes dist/test_report.json
NODE_PATH=$(npm root -g) node scripts/e2e/e2e.js               # 252 browser checks + screenshots
NODE_PATH=$(npm root -g) node scripts/e2e/edit_flows.js        # 36 edit-flow checks against the dev server
python3 scripts/e2e/steve_dry_run.py                          # 4 mornings
```

What they cover:

- **Contract.** Schemas match their source; the repo only contains empty fixtures; no secrets; `.env.example` has names only; migrations; naive or future timestamps, duplicate IDs and impossible values are rejected.
- **Calculations.** TRIMP, Fitness/Fatigue/Form against an independent re-calculation, zones (and no age-based HR max), recovery with missing inputs, weight trajectory, best efforts, splits, matched runs, map privacy (no point inside a privacy zone ever reaches the page), timezone day boundaries, PhenoAge sanity.
- **Importer.** Idempotent re-runs, overlapping batches, conflicts left unapplied, duplicate IDs in a batch, all-or-nothing rejection, dry run, missing sleep, CLI exit codes.
- **Build.** Byte-identical output, degraded vs failed, the previous build kept on failure, snapshot retention.
- **Honesty.** Missing values are null (never 0), every number has an `as_of`, empty data invents nothing, stale sleep is marked, no medical phrases, no power curve without power, no muscles from generic strength workouts.
- **Frontend.** No formula patterns in JS, no raw input access, no hard-coded people, dates or targets, no Strava or Bevel API.
- **Entries.** Create, update, delete, before/after history, undo (including profile and deletes), export, delete-all with confirmation, imported records read-only (409).
- **Actions.** Moving template and plan sessions (one undo step), Workout Wizard, accepting/declining suggestions, scheduling instant workouts, templates and routines, accepting only real threshold candidates, copying meals and days, recipes, prehab, privacy zones, route import (GPX/GeoJSON, rejects XML entity tricks), route flags, record uploads (type and size limits), manual blood pressure.
- **Scripts and rules.** Strength CSV import (Strong, Hevy, re-runs, unknown names skipped), Coach memory maintenance, due check-ins, WCAG AA contrast for both themes, each metric defined once, snapshot pin.
- **Server and auth.** Unauthenticated requests get 302 or 401; tampered, expired, foreign-key and wrong-email sessions are rejected; the full OIDC flow runs against a fake provider (state, nonce, audience, unverified email); JSON-only and same-origin edits; upload token; invalid uploads change nothing.
- **Edit flows (browser).** Goal create/edit/undo toast, profile and physiology, appearance and tabs, privacy zones, water/caffeine, meal copy, blood pressure, health records, journal and status, plan suggestion/move/instant/race/routine, GPX import and favourite, quick edit, memory and check-ins, prehab, custom exercise, widget and chart pins, gallery, history; no overflow in sheets.
- **Browser.** Every destination at 390×797 in dark and light, plus desktop: no JS errors, no horizontal overflow, no NaN/undefined. Also checks the More sheet (focus, Escape), the provenance sheet, the factors sheet, chart tooltips (keyboard and pointer), all training tabs, activity and route detail, empty-state wording, and PWA offline mode through the service worker.

---

## 11. Known limitations

- **Synthetic data only so far.** Thresholds are tuned on generated data. Expect to adjust `config/defaults.json` (via `profile.json → overrides`) after a few weeks of real data.
- **Recovery and Form need history.** Recovery needs 14 days of HRV / resting HR before it shows a score. Form says "calibrating" for the first 42 days.
- **Rule-based plan adaptations.** Plans adapt by fixed rules, not by a learned model. Suggestions are never applied without your OK.
- **Coach chat needs a key.** Without an LLM key, Coach shows the deterministic call, factors and suggestions only.
- **Sign-in trusts the TLS channel.** The ID token's signature is not checked locally. Identity is taken from Google's token endpoint over TLS and cross-checked with userinfo (allowed by OIDC Core 3.1.3.7).
- **Large HTML file.** About 3 MB with 200 days of data, because detail is embedded for the latest 160 activities. Older activities show summary rows only.
- **Undo is per change, newest first.** Undo always reverts the latest change (or the latest action's group). It can't pick an older change out of order.
- **No base map.** Routes, heatmap and flyover draw your own lines on a plain background until a tile server is configured and wired in (§9).
- **No push notifications.** Check-ins and nudges are delivered by Steve, not by the PWA.
- **Not clinically validated.** Stress, Energy Bank, strain scale and biological age are estimates and are labelled as such.
