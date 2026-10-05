# AGame

A private fitness dashboard for one person. It combines the paid features of Strava and Bevel Intelligence (plus ideas from Athletica.ai), and runs on your own Apple HealthKit data. An agent (today **Muse**, set in `sync.agent_name`) sends that data in every morning over HTTP and logs what you tell it through the day.

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
4. [The agent's runbook](#4-the-agents-runbook)
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
iPhone HealthKit ──► agent (Muse) ──► POST /api/import ──► importer ──────────► AGAME_DATA_DIR/*.json
Health export.zip ──► POST /api/import/apple-health-export (one-time backfill) ──┤
                    owner edits in the app, agent logs ──► /api/entries ────────┤
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
- **No hard-coded people or targets.** Names, dates, zones, thresholds and targets come from data files or `config/defaults.json`. Even the agent's name comes from config (`sync.agent_name`).
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
| `scripts/tests/`, `scripts/e2e/` | Unit/integration tests, browser tests, agent dry run |
| `docs/build-plan.md` | Research, the 57-issue plan and the full feature matrix |
| `docs/design.md` | Design rules for every screen. Read before changing the UI |
| `docs/screenshots/` | Screenshots from synthetic data |

---

## 3. Commands

Run these from the repo root. Each one prints `--help`.

| Command | What it does | Exit codes |
|---|---|---|
| `python3 scripts/update_from_healthkit.py --date YYYY-MM-DD --input batch.json [--data-dir DIR] [--dry-run]` | Merges one HealthKit batch (AGame batch or `muse.v1`). Safe to repeat. All-or-nothing; the HTTP import is lenient instead | 0 applied or already imported · 2 applied, some records left out (stale, conflicting or rejected) · 1 rejected, nothing written · 3 data dir not found |
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
| `python3 scripts/import_apple_health_export.py export.zip [--data-dir DIR] [--dry-run]` | One-time backfill from the Health app's export: daily values, sleep stages, workouts with heart rate and routes. Safe to repeat; never duplicates the agent's records | 0 imported · 2 imported, some records left out · 1 rejected · 3 usage |
| `python3 scripts/e2e/agent_dry_run.py` | Rehearses the agent's mornings over HTTP only, exactly as `docs/agents.md` says | 0 pass · 1 fail |

`AGAME_DATA_DIR` and `AGAME_DIST_DIR` work as defaults for `--data-dir`, `--out` and `--dist-dir`.

---

## 4. The agent's runbook

**[docs/agents.md](docs/agents.md) is the only file the agent needs.** It covers auth, every endpoint with examples, the batch format, the daily routine (06:15, retries at 08:00 and 13:00), what to do for every error, and the hard rules. Muse runs AGame from it over HTTPS alone: no shell, no data folder, one import call per run.

In short:

- `POST /api/import` with the agent token takes one batch, imports it, rebuilds, and answers with the import result, `build_report`, `morning_summary` and the check-in schedule.
- Bad records go into a `rejected` list with a reason; the rest still imports. Re-sending is safe: identical batches are no-ops, and a newer copy of a record replaces the older one (logged in the edit history).
- The agent logs through `/api/entries` and `/api/actions` with the same token. Each change is marked `source: agent`. The token can't delete, undo or change settings.
- `POST /api/snapshot` (the whole-folder push with `AGAME_UPLOAD_TOKEN`) is no longer part of the daily routine: it overwrites edits made in the app. Keep it for manual restores.

### Running it by hand (laptop)

The same steps work from a shell when you want to:

```bash
export AGAME_DATA_DIR=~/agame-data
python3 scripts/update_from_healthkit.py --date 2026-10-05 --input batch.json   # AGame batch or muse.v1
python3 scripts/build_dashboard.py --date 2026-10-05 --quiet                     # date in the profile's time zone
cat dist/build_report.json dist/morning_summary.json
python3 scripts/import_apple_health_export.py ~/Downloads/export.zip           # one-time backfill
python3 scripts/due_checkins.py                                                 # check-ins due now
python3 scripts/coach_maintenance.py                                            # nightly: tidy Coach memory
```

`build_report.json → next` names the first real error and what to do ("fix the batch and re-import"), or the reason a build is degraded.

### Backup and rollback

- The private data folder (the Railway volume) is the source of truth. Download it now and then with **Export my data** in Profile, or copy the volume.
- `dist/snapshots/` keeps the last 7 built dashboards. To roll back the view, pin one: `echo 2026-10-03 > dist/pin.txt` (or set `AGAME_PIN_SNAPSHOT=2026-10-03` on the server). `/api/agent/build-report` shows the active pin.
- Edits made in the app or by the agent are in `edit_history.jsonl` (in the data folder), with before and after. Undo them from the app.

### Dry run (verified)

`scripts/e2e/agent_dry_run.py` runs the routine over HTTP on synthetic data shaped like Muse's queries:

| When | Batch | Result |
|---|---|---|
| 2 Oct 06:15 | First run: history since 24 Sept, last night still syncing | 200 · imported · summary says sleep hasn't synced |
| 2 Oct 08:00 | Retry: last 3 days, sync complete | 200 · values updated · no night or workout duplicated |
| 2 Oct 08:00 | Identical re-send | 200 · `already_imported` · data unchanged |
| 3 Oct 06:15 | One impossible night and one value in the wrong unit | 200 · exit 2 · both listed in `rejected`, the rest applied |
| 3 Oct 06:20 | The fixed batch, sent once | 200 · applied |
| 3 Oct, day | Two coffees (one request retried with the same key) and a mood | logged once each, marked `source: agent` · delete refused (403) |

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
| `sleep.json` | Importer | `nights`: `{source_id, date, start, end, is_nap, segments:[{stage, start, end}]}` or, from a summary source, `stage_minutes:{core, deep, rem, awake, in_bed, asleep_unspecified}` with `efficiency_pct` and `awakenings`. Stages: in_bed, awake, core, deep, rem, asleep_unspecified |
| `workouts.json` | Importer | `workouts`: `{source_id, sport, start, end, distance_m, avg_hr, max_hr, moving_s, avg_speed_mps, elevation_gain_m, steps, route_id, samples:{t, hr, dist_m, elev_m, speed_mps, power_w, cadence, lat, lon, …}, splits, laps, segments, weather, tags, synced_at, partial}`. `samples` is optional (summary workouts) |
| `routes.geojson` | Importer | GeoJSON LineStrings `[lon, lat, ele]` with `properties.id`. Workouts point to them with `route_id` |
| `body.json` | Importer + owner | `measurements`: `{source_id, t, type: weight_kg/body_fat_pct/lean_mass_kg/waist_cm/bmi, v, kind}` |
| `nutrition.json` | Importer + owner | `meals` (with `items` and macros), `water`, `caffeine`, `daily_totals` (whole-day totals from HealthKit, added to meals logged in AGame), `recipes`, `planned_meals`, `connected` |
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

### HealthKit batch (what the agent sends)

`POST /api/import` and `update_from_healthkit.py` accept two shapes:

- **`muse.v1`:** Muse's query results, untouched: `{"format": "muse.v1", "generated_at", "timezone", "sleep": {coverage, records}, "workouts": {coverage, records}, "daily_metrics": {coverage, records}}`. The adapter (`scripts/agame/muse.py`) maps each field through an explicit unit table with range checks. Full description and the unit table: [docs/agents.md](docs/agents.md). Example: [docs/examples/muse-v1-batch.json](docs/examples/muse-v1-batch.json).
- **AGame batch (`batch_version` 2):** the format the adapter produces. Schema: [schemas/healthkit_batch.schema.json](schemas/healthkit_batch.schema.json). Example: [docs/examples/healthkit-batch.json](docs/examples/healthkit-batch.json).

```json
{
  "batch_version": 2, "date": "2026-10-05", "generated_at": "2026-10-05T06:15:00+02:00", "timezone": "Africa/Kigali", "source": "healthkit",
  "coverage": { "sleep": { "complete": false, "note": "…" } },
  "samples": {
    "metrics":   { "hrv_sdnn_ms": [ {"date": "2026-10-04", "v": 34.5, "source_id": "healthkit_daily_hrv_sdnn_ms_2026-10-04", "partial": true} ] },
    "sleep":     [ { "source_id": "healthkit_0F3A…", "start": "2026-10-03 23:58:40", "end": "…", "stage_minutes": {"core": 200.2, "deep": 65.1, "rem": 73.5, "awake": 13.7}, "efficiency_pct": 94.1, "awakenings": 4 } ],
    "workouts":  [ { "source_id": "healthkit_7C2D…", "sport": "walk", "start": "…", "end": "…", "avg_hr": 101.2, "max_hr": 121, "splits": [ … ], "weather": { … } } ],
    "body":      [ { "source_id": "…", "t": "…", "type": "weight_kg", "v": 83.0 } ],
    "nutrition": { "daily_totals": [ { "source_id": "healthkit_daily_nutrition_2026-10-04", "date": "2026-10-04", "kcal": 1302.8, "protein_g": 62.2 } ],
                   "meals": [ … ], "water": [ … ], "caffeine": [ … ] },
    "routes":    [ … ]
  },
  "series_meta": { "wrist_temp_c": { "unit": "°C", "label": "Wrist temperature", "agg": "mean" } }
}
```

Rules:
- Every record needs a `source_id` (the HealthKit UUID as `healthkit_<UUID>`; meals also need an `id`). Daily values use `healthkit_daily_<series>_<date>`.
- Timestamps carry an offset, or are wall-clock times placed in the record's or batch's `timezone`. A wall time inside a daylight-saving change is refused.
- A batch may not contain `kind: user_entered` records. Those are made in the app or logged by the agent through `/api/entries`.
- Sleep comes either as a stage timeline (`segments`) or as stage totals (`stage_minutes`). Workouts come with `samples`, or as a summary with `avg_hr`, `max_hr` and source `splits`. Summaries never get a made-up stream: the hypnogram, heart-rate zones and chart, best efforts and the map show their missing state, and load is estimated from average heart rate.
- The idempotency key is the date plus a hash of the batch content. Sending the same batch twice is a no-op.
- A record whose `source_id` already exists is skipped if identical. If it differs, the copy with the newer `generated_at` wins and the change is written to `edit_history.jsonl` with before and after. Records you entered yourself are never touched.
- The same night or workout under another id (the agent's summary and the Apple Health export) is stored once; a detailed copy replaces a summary.
- `coverage.<domain>.complete: false` marks that domain as still syncing; for sleep the app says "Sleep not synced yet".
- The merged result is validated **before** anything is written. The CLI rejects the whole batch on one bad record; the HTTP import lists bad records in `rejected` and applies the rest.

### Outputs (in `dist/`)

| File | For |
|---|---|
| `fitness_dashboard.html` | The app (data embedded) |
| `build_report.json` | The agent: `status`, `exit_code`, `errors`, `warnings`, `degraded_reasons`, per-domain `freshness`, input and output hashes, and `next` (the first real error and how to recover) |
| `morning_summary.json` | The agent (`agame.morning_summary.v2`): `message` (the lines to send, the same sentences the app shows), recovery, sleep, today's call, the suggested change, data status |
| `weekly_review.json` | The agent, Mondays |
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
| `AGAME_AGENT_TOKEN` | Random token the agent (Muse) sends as `Authorization: Bearer …` for `/api/import`, `/api/agent/*`, `/api/entries` and `/api/actions` |
| `AGAME_UPLOAD_TOKEN` | Optional. A different random token for `push_snapshot.py` (manual restores only, never the daily routine) |
| `AGAME_LLM_PROVIDER`, `ANTHROPIC_API_KEY` | Optional Coach chat: set the provider to `anthropic`, and build with `INSTALL_COACH=1` (Railway: add it as a build variable). Model defaults to `claude-opus-5-5`; override with `AGAME_LLM_MODEL` |

3. On first boot, the container fills the empty volume with the empty fixtures. It then drops to the unprivileged user `agame` and starts the server. The health check is `/healthz`.
4. The agent sends data with `POST /api/import` ([docs/agents.md](docs/agents.md)). Every import is validated before anything is written.
5. **Rollback.** Redeploy an earlier image in Railway. Data is on the volume, so a code rollback never loses data.

### Deploy checklist

1. **Generate two tokens** on your laptop, one per line, and keep them in your password manager:
   ```bash
   python3 -c "import secrets;print('AGAME_SESSION_SECRET', secrets.token_urlsafe(48))"
   python3 -c "import secrets;print('AGAME_AGENT_TOKEN', secrets.token_urlsafe(32))"
   ```
   (`AGAME_UPLOAD_TOKEN` only if you want manual restores; make it a third, different value.)
2. **Google OAuth client** (step 1 above) with redirect `https://<your-app>/auth/callback`.
3. **Railway service** from this repo on branch `design-cleanup` (or `main` once merged). **Volume** mounted at `/data`. Leave `AGAME_DATA_DIR` and `AGAME_DIST_DIR` unset; the image points them at the volume.
4. **Variables:** `AGAME_OIDC_ISSUER=https://accounts.google.com`, `AGAME_OIDC_CLIENT_ID`, `AGAME_OIDC_CLIENT_SECRET`, `AGAME_OWNER_EMAIL`, `AGAME_SESSION_SECRET`, `AGAME_BASE_URL=https://<your-app>`, `AGAME_AGENT_TOKEN`. Optional: `AGAME_UPLOAD_TOKEN`, Coach chat variables.
5. **Deploy**, wait for `/healthz` to pass, then run the smoke test from your laptop:
   ```bash
   export AGAME_BASE_URL=https://<your-app> AGAME_AGENT_TOKEN=<token>
   curl -fsS "$AGAME_BASE_URL/healthz"                                                        # {"ok": true}
   curl -s -o /dev/null -w "%{http_code}\n" "$AGAME_BASE_URL/api/agent/morning-summary"     # 401 without the token
   curl -fsS -H "Authorization: Bearer $AGAME_AGENT_TOKEN" "$AGAME_BASE_URL/api/agent/checkins"
   curl -fsS -X POST -H "Authorization: Bearer $AGAME_AGENT_TOKEN" -H "Content-Type: application/json" \
        --data @docs/examples/muse-v1-batch.json "$AGAME_BASE_URL/api/import" | python3 -m json.tool | head -40
   ```
   The last call imports the example (an anonymised night, walk and day of metrics for 4 October) and should answer `200` with `exit_code` 2 and "Last night's sleep hasn't synced". **Run it only on an empty volume, then reset the volume** (`railway volume delete --volume <name> --yes && railway volume add --mount-path /data`): the example's night would otherwise stand in for your real night of 4 October. On a volume with real data, check the import path with `--data '{"format": "muse.v1"}'` instead, which must answer `400` and write nothing.
6. **Sign in on the phone:** open `https://<your-app>` in Safari, sign in with Google, then Share → Add to Home Screen. The session lasts 30 days and renews every time you open the app.
7. **Profile:** set time zone, HR max or LTHR, sleep need and targets (Profile → Edit). Without HR max there are no zones, by design.
8. **Backfill:** Profile → Import Apple Health export, with the `export.zip` from the Health app (Profile picture → Export All Health Data).
9. **Hand Muse** the base URL, the agent token and `docs/agents.md`.

Locally with Docker: `docker build -t agame . && docker run -p 8080:8080 -v agame-data:/data --env-file .env agame`.

**Security headers:**
- strict CSP (no external scripts or images), `frame-ancestors 'none'`, `nosniff`, `no-referrer`
- `no-store` on API responses
- HttpOnly + SameSite=Lax session cookies
- edits need JSON and a same-origin request
- sessions are signed with HMAC, last 30 days and renew on every signed-in request
- the agent token can't delete, undo or change settings

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
| Weather on activity | Strava | Activity | Built (temperature and humidity from Apple Health workouts) |
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
| Wind and conditions on activities, heat-adjusted pace for planned sessions | A weather source (temperature and humidity already come from Apple Health) | `workouts[].weather = {temp_c, humidity_pct, wind_kph, conditions, source}`. For plans: `plans.sessions[].forecast_temp_c` |
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
python3 scripts/run_tests.py                                   # 155 tests, ~90 s, writes dist/test_report.json
NODE_PATH=$(npm root -g) node scripts/e2e/e2e.js               # 257 browser checks + screenshots
NODE_PATH=$(npm root -g) node scripts/e2e/edit_flows.js        # 37 edit-flow checks against the dev server
python3 scripts/e2e/agent_dry_run.py                          # the agent's mornings over HTTP
```

What they cover:

- **Contract.** Schemas match their source; the repo only contains empty fixtures; no secrets; `.env.example` has names only; migrations; naive or future timestamps, duplicate IDs and impossible values are rejected.
- **Calculations.** TRIMP, Fitness/Fatigue/Form against an independent re-calculation, zones (and no age-based HR max), recovery with missing inputs, weight trajectory, best efforts, splits, matched runs, map privacy (no point inside a privacy zone ever reaches the page), timezone day boundaries, PhenoAge sanity.
- **Importer.** Idempotent re-runs, overlapping batches, newer copies updating records (with history), older copies never winning, user-entered records untouched, duplicate IDs in a batch, all-or-nothing CLI rejection, lenient HTTP rejection lists, dry run, missing sleep, CLI exit codes.
- **Muse and the Apple Health export.** The real Muse fixtures map without rejections; units and ranges; fraction and metre conversions; absent fields stay missing; ambiguous wall times refused; coverage marks sleep as not synced; three-day re-sends stay idempotent; the export's per-device totals, sleep stages, heart rate and routes; the export and Muse never duplicate a night or workout; XML entities refused; the doc examples match the schema.
- **Build.** Byte-identical output (including cached against uncached builds), degraded vs failed, the previous build kept on failure, snapshot retention.
- **Honesty.** Missing values are null (never 0), every number has an `as_of`, empty data invents nothing, stale sleep is marked, no medical phrases, no power curve without power, no muscles from generic strength workouts.
- **Frontend.** No formula patterns in JS, no raw input access, no hard-coded people, dates or targets, no Strava or Bevel API.
- **Entries.** Create, update, delete, before/after history, undo (including profile and deletes), export, delete-all with confirmation, imported records read-only (409).
- **Actions.** Moving template and plan sessions (one undo step), Workout Wizard, accepting/declining suggestions, scheduling instant workouts, templates and routines, accepting only real threshold candidates, copying meals and days, recipes, prehab, privacy zones, route import (GPX/GeoJSON, rejects XML entity tricks), route flags, record uploads (type and size limits), manual blood pressure.
- **Scripts and rules.** Strength CSV import (Strong, Hevy, re-runs, unknown names skipped), Coach memory maintenance, due check-ins, WCAG AA contrast for both themes, each metric defined once, snapshot pin.
- **Agent API.** A morning over HTTP, agent logs marked `source: agent`, retried requests applied once, deletes and settings refused, wrong or missing tokens, sessions renewed.
- **Server and auth.** Unauthenticated requests get 302 or 401; tampered, expired, foreign-key and wrong-email sessions are rejected; the full OIDC flow runs against a fake provider (state, nonce, audience, unverified email); JSON-only and same-origin edits; upload token; invalid uploads change nothing.
- **Edit flows (browser).** Goal create/edit/undo toast, profile and physiology, appearance and tabs, privacy zones, water/caffeine, meal copy, blood pressure, health records, journal and status, plan suggestion/move/instant/race/routine, GPX import and favourite, quick edit, memory and check-ins, prehab, custom exercise, widget and chart pins, gallery, history; no overflow in sheets.
- **Browser.** Every destination at 390×797 in dark and light, plus desktop: no JS errors, no horizontal overflow, no NaN/undefined. Also checks the More sheet (focus, Escape), the provenance sheet, the factors sheet, chart tooltips (keyboard and pointer), all training tabs, activity and route detail, empty-state wording, and PWA offline mode through the service worker.

---

## 11. Known limitations

- **HRV is a daily average.** Muse sends the day's average SDNN, which includes daytime readings. Recovery uses that same series for today and for its baseline, so they stay comparable; it is not the overnight-only HRV some apps show.
- **Summary imports have no streams.** Until the Apple Health export is imported, workouts have no heart-rate zones, chart, best efforts or map, and nights have no stage timeline. They say so on screen.
- **Synthetic data only so far.** Thresholds are tuned on generated data. Expect to adjust `config/defaults.json` (via `profile.json → overrides`) after a few weeks of real data.
- **Recovery and Form need history.** Recovery needs 14 days of HRV / resting HR before it shows a score. Form says "calibrating" for the first 42 days.
- **Rule-based plan adaptations.** Plans adapt by fixed rules, not by a learned model. Suggestions are never applied without your OK.
- **Coach chat needs a key.** Without an LLM key, Coach shows the deterministic call, factors and suggestions only.
- **Sign-in trusts the TLS channel.** The ID token's signature is not checked locally. Identity is taken from Google's token endpoint over TLS and cross-checked with userinfo (allowed by OIDC Core 3.1.3.7).
- **Large HTML file.** About 3 MB with 200 days of data, because detail is embedded for the latest 160 activities. Older activities show summary rows only.
- **Undo is per change, newest first.** Undo always reverts the latest change (or the latest action's group). It can't pick an older change out of order.
- **No base map.** Routes, heatmap and flyover draw your own lines on a plain background until a tile server is configured and wired in (§9).
- **No push notifications.** Check-ins and nudges are delivered by the agent, not by the PWA.
- **Not clinically validated.** Stress, Energy Bank, strain scale and biological age are estimates and are labelled as such.
