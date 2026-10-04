# AGame — Complete Build Plan

> **Status:** draft for owner review. No production code until approved.
> **Compiled:** 2026-10-04.
> **Sources:** owner brief, my own research, and *Strava + Bevel + Athletica.ai Complete Feature Reference* (55 pp, incl. 34 official screenshots).
> **This file is the single source of truth for the plan.** It replaces the 51 Linear issues DEV-554…DEV-604 created earlier (mapping in §11).

---

## 0. How to use this document

- Every `### AG-xx` heading below is **one issue**, ready to push to Linear or GitHub Issues.
- The line under each heading holds the issue fields: `Milestone · Priority · Depends on · Linear`.
  - Priority: P1 urgent, P2 high, P3 medium, P4 low.
- The checklist under **AC** is the acceptance criteria. An issue is done only when every box is checked.
- When pushing: title = heading text, body = everything under it, milestone + priority from the field line.
  - Issues with a `Linear: DEV-xxx` value already exist. Update those instead of creating duplicates.

---

## 1. What changed after reading the feature reference

1. **The screenshots arrived** (inside the PDF appendix): 10 Strava, 10 Bevel, 8 Athletica, plus 6 Strava subscribe-page cards. The design system now has a concrete visual direction (§4). Exact pixel measurements still need sharper captures (AG-56).
2. **Athletica.ai added as a third reference** (the PDF's Part 3). Its useful ideas are now issues:
   - plan-vs-actual compliance and a week header
   - Workout Wizard session alternatives
   - threshold calibration from test efforts
   - form forecast and overtraining warning
   - post-workout RPE + feel + comment
   - drag-and-drop week planning with a template library
   - A/B/C race priority and "train-to-maintain"
   - per-session guiding metric

   Device sync, Velocity live classes, and the coach platform are **out of scope** (§10).
3. **New detail folded in:**
   - Bevel's Muscular Load / Freshness statuses and calibration rules
   - Nutrition Score 2.0 quality contributors
   - pinned, reorderable charts and a Personal Records hub with top-10 per record
   - structured workout steps (warm-up / repeat / recovery / cool-down with HR or pace targets)
   - Strava's weekly Relative Effort vs 12-week weighted average and the maintain / increase / recover suggestion
   - Runna's "Not Feeling 100%" mode and heat-adjusted pace targets
   - Year in Sport (paywalled since Dec 2025), Live Segments, friend challenges
4. **Plan split:** the old "Plans" issue was too big. It is now four issues (AG-32…AG-35). Two new calc issues pull Muscular Load and Nutrition math out of the screens (AG-23, AG-24). One new screen-level issue covers customizable charts + Personal Records (AG-39).
5. **The repo is public.** Real data must live in a private place (AG-01, AG-00 decision 2).

---

## 2. Ground rules (every issue inherits these)

1. **Steve only touches data and runs commands.**
   - Steve writes `data/*.json` and runs scripts. He never edits UI code to change a number.
2. **One deterministic build.**
   - Same input + same `--date` gives the same bytes.
   - It succeeds on partial data, fails loudly on impossible data, and always writes `dist/build_report.json`.
3. **Missing is never zero.**
   - Every value carries `as_of`, `source`, `coverage`, `status`.
   - Every value also carries a kind: `observed | configured | computed | estimated | user_entered`.
4. **One formula per metric, in Python.**
   - The browser only renders `computed.json`.
   - Two screens showing the same metric read the same key.
5. **Nothing hard-coded in components.** Names, targets, dates, zones, and thresholds come from data or config.
6. **No invented data.**
   - No fake athletes, routes, ranks, or citations.
   - No age-based HR max. No muscles guessed from a generic workout.
   - No VO2 max estimated from pace. No power curve without power data.
7. **Allowed sources only.**
   - HealthKit (via Steve) is the source of truth.
   - No Strava API data in any AI, prompt, embedding, or RAG pipeline. No Bevel API.
8. **Fitness information, not medical advice.** No diagnosis language anywhere.
9. **A screen is done only after inspection at 390×797**, in dark and light, not just rendering.

---

## 3. Research summary

### 3.1 Strava subscription ($11.99/mo · $79.99/yr · Runna bundle $149.99/yr)

| # | Paid feature | AGame coverage |
|---|---|---|
| 1 | Relative Effort per workout, weekly chart vs 12-week weighted avg, maintain/increase/recover hint | AG-14, AG-28 |
| 2 | Fitness & Freshness (42d / 7d impulse-response, Form = Fitness − Fatigue) | AG-15, AG-28 |
| 3 | Training Log + cumulative stats, period comparisons | AG-21, AG-28 |
| 4 | Matched Runs | AG-20, AG-29 |
| 5 | Advanced workout insights: zones, custom HR zones, power/HR curves, GAP, race analysis, weather | AG-14, AG-20, AG-29 |
| 6 | Custom Goals (distance, time, calories, RE, kJ) + Best Efforts | AG-21, AG-31 |
| 7 | Training plans | AG-33 |
| 8 | Route builder + recommendations | AG-42 |
| 9 | Offline maps / saved routes | AG-42, AG-11 |
| 10 | Personal heatmap (incl. night) | AG-43 |
| 11 | Full segment leaderboards, filters, Live Segments | AG-43, AG-50 |
| 12 | Custom challenges with friends | AG-47 |
| 13 | Leaderboard Integrity (cheat detection) | AG-43 |
| 14 | Year in Sport (paywalled since Dec 2025) | AG-48 |
| 15 | Athlete Intelligence (AI summaries from last 30 days) | AG-22 |
| 16 | Strength muscle map + strength-app integrations (Sept 2026) | AG-23, AG-36, AG-41 |
| 17 | Claude integration (chat over workout data) | AG-44 (over HealthKit data, **not** Strava data) |
| 18 | Runna adaptive coaching: pace-target adjustment, "Not Feeling 100%", heat adaptation | AG-33 |
| 19 | Perks: custom app icon, Recover Athletics prehab | AG-38, AG-26 |
| 20 | Beacon (free on phone; paid from watch) | AG-50 (contract only) |
| — | Also verified in my research: Performance Predictions, Instant Workouts, Progress comparison, Flyover, Quick Edit, weekly heatmap, Month in Sport | AG-20, AG-33, AG-28, AG-29, AG-43, AG-48 |

### 3.2 Bevel (core free since Dec 2025; Bevel Pro $14.99/mo · $99.99/yr unlocks Intelligence)

**Free app, covered fully:**
- Recovery, Sleep, Strain, Stress, Energy Bank
- Nutrition Score 2.0, Biological Age, Health Records, Journal
- Cardio Load
- Muscular Load & Muscle Freshness (with Muscle Map)
- Training Calendar
- Routines (sendable to Watch)
- Customizable charts, Personal Records
- Activity details (scrub, running form, splits, multisport)
- Strength Builder (700+ exercises)
- Food logging (barcode, image, recipe, describe-meal)
- Timeline, CGM
- Cycle tracking, water & caffeine, Activity Status, widgets, smart alarm

**Bevel Intelligence (paid):**

| # | Feature | AGame coverage |
|---|---|---|
| I1 | Conversational Q&A on own data, citing research | AG-44 |
| I2 | Train vs rest; helping / hurting factors | AG-22, AG-25 |
| I3 | Proactive check-ins and nudges (e.g. daily 3 pm reminder) | AG-44, AG-55 |
| I4 | AI training plans + workouts, scheduled on the calendar, adjusted via chat | AG-33, AG-44 |
| I5 | Full workout context + long-term memory with overnight maintenance | AG-44 |
| — | From my research: coaching personalities, Files store, artifacts, Fast/Thinking modes | AG-44 |

### 3.3 Athletica.ai (single tier: $19.90/mo · $99/6 mo · $189/yr)

| # | Feature | AGame coverage |
|---|---|---|
| 1 | Adaptive multi-sport plans, A/B/C race priority, train-to-maintain | AG-33 |
| 2 | Data-grounded AI coach, tone + language complexity, daily summary, weekly HRV flags | AG-44 |
| 3 | Workout Wizard: shorter / longer / format / easier / harder / recovery alternatives | AG-33 |
| 4 | Test week + threshold-based zones (5K test, FTP, CSS), auto-update on new thresholds | AG-14 |
| 5 | Fitness / form / fatigue with RPE + feel, form forecast, overtraining warning (toggle) | AG-15 |
| 6 | Pre-workout guidance + post-workout insights (RPE, feel, comment) | AG-34, AG-29 |
| 7 | Plan Your Week drag-and-drop + template library with edit propagation | AG-32 |
| 8 | Strength from a library, RPE-anchored; strength cancelled on poor recovery | AG-41, AG-33 |
| 9 | Device sync, extended warm-up/cool-down, per-session guiding metric | AG-35 (sync itself out of scope) |
| 10 | Velocity live workouts | Out of scope |
| 11 | Coach platform | Out of scope |

---

## 4. Visual direction (from the 34 screenshots)

Screenshots are low-resolution marketing images. Proportions are approximate. AG-56 refines them with sharper captures.

**Base:** Strava's dark shell.
- Near-black background, cards one step lighter, rounded ~12–16 px.
- White primary text, grey secondary.
- **Strava orange** accent for activity and training data: routes, progress lines, selected chips, active nav.

**Scores:** Bevel's ring language.
- Three rings in a row on Today, in the order **Strain · Recovery · Sleep**. Percent inside, label below.
- Score colors: Strain = orange→yellow, Recovery = green, Sleep = blue/violet.
- Detail page pattern:
  - big number + date
  - a "Normal range 34–67%" style personal band
  - segmented chips to switch the chart metric
  - a line chart with a shaded personal-range band and an average marker
  - sub-cards with value + sparkline + "Normal range ✓"

**Sleep:** Bevel dark hypnogram.
- Stage colors: awake orange, REM light blue, core blue, deep violet.
- 2×2 stage tiles: duration + % + mini ring.
- "Sleep needed" row, "Time to fall asleep" row.

**Nutrition:** Bevel.
- Macro % as dot-matrix columns: fat blue, carbs orange, protein pink.
- Net-energy scale −500…+500.
- Quality-contributor rows with a slider bar and "+7".

**Recovery:** ring + HRV and RHR tiles with ▲/▼ deltas, one insight card, a "Recovery timeline".

**Biological Age:** Bevel gauge.
- Big age with "x years younger/older" and "−0.2 from last week".
- "Next update in N days" and "85% confidence".
- Category rows (Sleep / Activity / Fitness) with years ±.

**Training analysis:**
- Strava Progress chart: sport chip + metric chips, current period orange vs prior period teal, total + % delta, "Prior 3 months" pill.
- Athletica week header: Actual vs Planned (sessions, duration, load). Week grid of session tiles with type code, load (planned in brackets), duration, and a compliance border (green = as planned, amber = partial).

**Activity detail:**
- Strava stat grid: Distance / Time / Elevation / Achievements; strength: Elapsed / Volume / Sets / Avg HR.
- Athletica tabs **Summary · Analysis · Chat · Planned**. Analysis has a multi-metric overlay chart with zone bands and a Session chart ↔ Time in Zone toggle. Summary has a plan-vs-actual table and a compliance banner.

**Routes:**
- Strava cards: thumbnail trace, "distance · elevation · time".
- Filter chips: Length / Elevation / Surface / Difficulty.
- A surface breakdown bar (paved / unpaved / unknown).

**Structured workout:** Bevel step list.
- Warm-up 10 m HR 130–145 → Repeat ×3 (Tempo 6 m pace X / Recovery 2 m HR < 150) → Cool-down.
- Device row.

**Coach:** Bevel Intelligence.
- Greeting, suggestion chips ("Create a training plan", "Log food").
- "Ask anything" input with a **Fast** mode chip.

**Rules:**
- Gradients only where the references use them, as subtle backgrounds behind score heroes. Never decorative.
- No stock photos. AGame has no user photos.
- Route thumbnails are SVG traces.

---

## 5. Architecture and privacy

```text
AGame/
  README.md  AGENTS.md  .env.example  Dockerfile  railway.toml  pyproject.toml
  docs/        product.md  data-contract.md  calculations.md  deployment.md  build-plan.md
  schemas/     one JSON Schema per data file
  data/        EMPTY fixtures only (public repo)
  scripts/
    agame/     stdlib package: io, validate, migrate, compute/*, insights, render
    build_dashboard.py  validate_data.py  update_from_healthkit.py
    fitness_server.py   fitness_pwa.py    fitness_sw.js
    tests/     unit + integration + fixtures (synthetic, marked fixture:true)
    e2e/       Playwright (dev only)
  dist/        git-ignored: fitness_dashboard.html, manifest, sw, icons, build_report.json,
               weekly_review.json, widgets.json
```

**Stack:**
- Python 3.11+ standard library at runtime. Playwright is a dev-only dependency.
- One self-contained HTML file: vanilla JS + inline SVG charts. No framework.

**Data path:**
- `AGAME_DATA_DIR` points at the real data. Recommended: a separate **private** repo `agame-data`.
- Steve commits data + dist there, never to this public repo.

**Data files:**
- `profile.json`, `current.json` (sync manifest), `metrics.json`, `sleep.json`, `workouts.json`
- `load.json` (user-entered RPE / feel / comments only; computed load lives in `computed.json`)
- `body.json`, `nutrition.json`, `strength.json`, `goals.json`, `plans.json`, `routes.geojson`
- `social.json`, `journal.json`, `health_records.json`, `coach.json`, `edit_history.jsonl`

**Commands:**

```bash
python3 scripts/update_from_healthkit.py --date YYYY-MM-DD --input batch.json   # or --input -
python3 scripts/validate_data.py data/
python3 scripts/build_dashboard.py --date YYYY-MM-DD
python3 scripts/fitness_server.py            # --dev for localhost without auth
python3 -m unittest discover scripts/tests -p 'test_*.py'
```

---

## 6. Open decisions (defaults apply if you just approve)

| # | Decision | Default |
|---|---|---|
| 1 | Visual reference | Use the PDF screenshots now. Add sharper real-device captures to `docs/reference/` later (AG-56). |
| 2 | Where real data lives (repo is public) | Private repo `irachrist1/agame-data` via `AGAME_DATA_DIR`. Railway volume synced from it. |
| 3 | Sign-in | Google OIDC, one owner email (`AGAME_OWNER_EMAIL`), signed session cookie. Any OIDC issuer supported. |
| 4 | Coach chat LLM | Optional, server-side, key in env. Sees only computed AGame data + coach memory. Without it: deterministic insights + "Coach chat not connected". |
| 5 | Map tiles | None. SVG traces on a neutral grid (offline, zero third-party calls). Optional tile URL in config. |
| 6 | Mobile tabs (new) | **Today · Training · Activities · Coach · More**. Recovery / Sleep / Strain open from the Today rings (Bevel pattern). Tab list is config, so you can swap Coach for Recovery. |
| 7 | Zone model (new) | 5 HR zones + 5 pace zones by default. Optional 7-zone threshold model (Athletica style) via config. |

---

## 7. Issues

### M0 — Foundations

### AG-00 Open decisions — owner answers
`M0 · P1 · — · Linear: DEV-554`

Answer §6 in a comment, or reply "use defaults".

**AC**
- [ ] Every decision in §6 has an answer or "default".
- [ ] Answers recorded in `docs/deployment.md` (2–5) and `docs/product.md` (1, 6, 7).

### AG-01 Repo skeleton, tooling, private-data boundary
`M0 · P1 · — · Linear: DEV-555`

**AC**
- [ ] Layout from §5. `pyproject.toml` (Python ≥ 3.11, no runtime deps). `.gitignore` covers `dist/`, `.env`, `private/`, `*.local.json`.
- [ ] `.env.example` lists names only, no values.
- [ ] `data/` holds schema-valid **empty** fixtures. `scripts/tests/fixtures/` holds synthetic fixtures with `"fixture": true` in every header.
- [ ] `AGAME_DATA_DIR` (default `./data`) is the only place real data is read from.
- [ ] Guard test: the suite fails if any committed `data/` file holds records.
- [ ] Clean clone → unittest passes with zero installs.

### AG-02 Data contract v1 — `docs/data-contract.md`
`M0 · P1 · AG-01 · Linear: DEV-556`

The contract Steve builds against. Freeze file names after approval.

**AC**
- [ ] Shared envelope on every file: `schema_version, generated_at, as_of, source, coverage{expected,received,ratio}, status(ok|partial|stale|missing)`.
- [ ] Per-value fields: `kind`, `unit`, `source_id(s)` for imports.
- [ ] Every field documented with type, unit, source, null behaviour, and example. Each file has a full example **and** an empty payload.
- [ ] Rules:
  - ISO-8601 with offset.
  - Local dates in `profile.timezone` (default `Africa/Kigali`).
  - `null` = unknown, never 0.
  - Sleep is attributed to the wake date.
- [ ] Imported records are immutable with `source_id`. User changes are separate `user_entered` records that reference them.
- [ ] Post-workout subjective fields: `rpe (1–10)`, `feel (1–5)`, `comment`, linked by workout `source_id`.
- [ ] Plans schema covers:
  - planned session: type code, steps, targets, guiding metric, priority, linked workout id
  - templates, races (A/B/C)
  - calendar events
- [ ] Weekly aggregates provably computable from daily data, with a worked example.
- [ ] Versioning + migration policy.

### AG-03 JSON Schemas + `validate_data.py` + migrations
`M0 · P1 · AG-02 · Linear: DEV-557`

**AC**
- [ ] One schema per file in `schemas/`, plus a stdlib validator (draft 2020-12 subset).
- [ ] `validate_data.py data/` exits 0 when valid, 1 when invalid. `--json` gives machine output (file, JSON pointer, reason).
- [ ] Semantic checks:
  - HR 0 or > 250
  - sleep > 24 h, end < start, negative distance
  - future timestamps beyond build date + tz slack
  - duplicate `source_id`, unknown units, broken references
- [ ] Old `schema_version` migrates in memory with a warning. Unknown future version fails hard.
- [ ] Tests for every rule.

### AG-04 `update_from_healthkit.py` — idempotent importer
`M0 · P1 · AG-03 · Linear: DEV-558`

**AC**
- [ ] Reads a batch from `--input file` or stdin.
  - Documented batch format per HealthKit type: sleep stages, HRV, RHR, VO2 max, respiratory rate, workouts + routes + HR/pace/power/cadence/running-form series, body mass/fat, steps, energy, BP, glucose, nutrition, water, caffeine.
- [ ] Idempotency key = date + sorted sample IDs. Rerun = byte-identical files. A known `source_id` is never duplicated.
- [ ] Atomic: temp + rename, all-or-nothing across files.
- [ ] Changed upstream sample with the same ID → reported as conflict and not applied.
- [ ] JSON summary on stdout: added / skipped / conflicts / domains. Exit codes documented.
- [ ] Updates the `current.json` sync manifest.
- [ ] Tests: rerun, partial batch, in-batch duplicates, malformed input, midnight-crossing sleep.

### AG-05 Compute core — periods, timezone, partial windows, metric registry
`M0 · P1 · AG-02 · Linear: DEV-559`

**AC**
- [ ] Day / week (Mon start, configurable) / month / quarter / year / all, tz-aware via `zoneinfo`.
- [ ] Window helper returns `{values, partial, coverage}`.
- [ ] Metric registry: id, unit, inputs, min observations, function. Declared once. A test asserts no duplicate formulas.
- [ ] Every computed value carries `as_of` = max of its inputs, `kind`, and `status`. Missing input → `null` + `missing`.

### AG-06 `build_dashboard.py` — deterministic build + build report
`M0 · P1 · AG-03, AG-05 · Linear: DEV-560`

**AC**
- [ ] Pipeline: validate → migrate → compute once → `computed.json` → embed into `dist/fitness_dashboard.html` → manifest, SW, icons.
- [ ] No network, no prompts, no wall-clock. Same input + date → same bytes (tested).
- [ ] Partial data builds with `partial` / `stale` markers. Impossible data → exit 1, previous `dist/` untouched (build in temp, then swap).
- [ ] `dist/build_report.json`: status (`ok|degraded|failed`), date, input hashes, per-domain freshness, warnings, errors, output hash, schema versions.
- [ ] Exit codes: 0 ok, 2 degraded (published), 1 failed.

### AG-07 Design system — tokens + core components
`M0 · P2 · AG-01 · Linear: DEV-561`

Follows §4.

**AC**
- [ ] CSS tokens for dark (primary) and light (system default): surfaces, text, accent orange, score colors (strain / recovery / sleep), sleep-stage colors, macro colors, status colors, spacing, radius, type scale, chart axes, motion.
- [ ] Every status pairs color with icon or text. AA contrast checked by a script.
- [ ] Components:
  - ScoreRing, StatTile (value · unit · Δ · as_of), MetricDetailHeader (big value + normal-range band label), ChipTabs, TrendCard with sparkline, FactorRow, InsightCard (≤ 2 lines + evidence)
  - Sheet (bottom on mobile, side panel on desktop), EmptyState, StaleBadge, ProvenanceChip
  - WeekGrid tile (type code · load (planned) · duration · compliance border), StepList (structured workout), DotMatrix macro bar, RangeScale (net energy), Gauge (bio age)
  - MuscleMap (front / back SVG), RouteThumb (SVG trace), SurfaceBar, LeaderRow, Widget card
- [ ] Dev-only gallery `#/dev/gallery` shows every component in ok / partial / stale / missing / estimate.
- [ ] Reduced motion disables ring and chart animation.

### AG-08 App shell — navigation, routing, More sheet, desktop rail
`M0 · P2 · AG-07 · Linear: DEV-562`

**AC**
- [ ] Mobile ≤ 768 px: 5-tab bottom bar from config (default §6 decision 6). More sheet lists the remaining destinations.
- [ ] Desktop: compact left sidebar with all 12 destinations. Multi-column content. Details open in a side panel.
- [ ] Hash routes (`#/today`, `#/activities/:id`, …). Deep links work offline. Back closes sheets.
- [ ] Keyboard: focus trap in sheets, Esc closes, visible focus, landmarks.
- [ ] Header: date + global freshness chip ("Updated 05:42 · partial") that opens the data-status sheet.
- [ ] No horizontal page scroll at 390×797.

### AG-09 Chart library — vanilla SVG
`M0 · P2 · AG-07 · Linear: DEV-563`

**AC**
- [ ] Types:
  - line / area (multi-series, dual y-axis), personal-range band + avg marker
  - bar / stacked, two-period comparison (current vs prior, Strava Progress)
  - hypnogram, zone bands behind a series, time-in-zone bars
  - calendar heat grid, scatter + smoothed trend, duration curve (log-x)
  - elevation profile, map trace, ring, gauge, sparkline
- [ ] `null` breaks lines. Partial periods are hatched and labelled.
- [ ] Tap (mobile), hover (desktop), and arrow keys inspect: value · unit · date · kind. Multi-metric scrub line on activity charts.
- [ ] `aria-label` summary + hidden data table per chart.
- [ ] Range switcher D / W / M / Q / Y / All, plus 1 / 3 / 6 / 12 / 24 mo where relevant. Visible range labelled.
- [ ] Units from config (metric default). Readable at 390 px.

### AG-10 Freshness, provenance, empty states
`M0 · P2 · AG-07 · Linear: DEV-564`

**AC**
- [ ] Every card's detail sheet shows source, coverage %, status, kind, method, and input count.
- [ ] Stale shows the last value dimmed + "Last updated {when}". Partial shows a badge + what's missing. Estimates show an "Estimate" label.
- [ ] One strings file holds the exact empty copy:
  - "Route data unavailable", "No cardio-fitness samples yet", "Nutrition not connected"
  - "No leaderboard data connected", "Power meter not connected" (and the chart is omitted)
  - "No exercise details — muscles not inferred", "Sleep not synced yet · last {date}"
- [ ] Sync banner when today's morning sync is missing.
- [ ] Test: an empty-fixture build renders no numeric 0 for missing metrics.

### AG-11 PWA — manifest, icons, service worker, offline snapshot
`M0 · P2 · AG-06 · Linear: DEV-565`

**AC**
- [ ] Installable on iOS Safari and Chrome. Standalone display, theme colors for both modes.
- [ ] SW caches the last successful snapshot, versioned by output hash. Offline launch shows it with as_of + an "Offline" chip.
- [ ] A failed build never replaces the cache.
- [ ] Icons generated deterministically (stdlib PNG). Alternate app icons selectable (Strava perk parity).
- [ ] Never caches edit APIs or health records.

### AG-12 `fitness_server.py` — owner sign-in and auth boundary
`M0 · P2 · AG-06 · Linear: DEV-566`

**AC**
- [ ] Env:
  - `AGAME_OIDC_ISSUER`, `AGAME_OIDC_CLIENT_ID`, `AGAME_OIDC_CLIENT_SECRET`
  - `AGAME_OWNER_EMAIL`, `AGAME_SESSION_SECRET`, `AGAME_BASE_URL`, `AGAME_DATA_DIR`
- [ ] Refuses to start in production mode if any is missing.
- [ ] Auth-code flow + state + nonce + PKCE. Identity via userinfo over TLS. Only the verified owner email is allowed.
- [ ] Before auth only the sign-in page is served: no snapshot, no data, no manifest details.
- [ ] Session cookie: HMAC-signed, HttpOnly, Secure, SameSite=Lax. Logout endpoint.
- [ ] CSP, HSTS, `frame-ancestors none`, `no-store` on the API. `/healthz` returns no data.
- [ ] `--dev` binds 127.0.0.1 only, with a banner.
- [ ] Tests: every route unauthenticated → redirect / 401; wrong email and tampered cookie rejected.

### AG-13 Manual entries API — edit history, undo, export, delete
`M0 · P2 · AG-12 · Linear: DEV-567`

**AC**
- [ ] `POST/PATCH/DELETE /api/entries/{domain}` for:
  - goals, meals, recipes, plans, templates, journal, strength logs
  - RPE / feel / comments, manual measurements (BP, weight), coach memory, settings
- [ ] Schema-validated, atomic, triggers a rebuild.
- [ ] Append-only `edit_history.jsonl` (ts, domain, id, before, after). Undo applies the inverse and is itself logged.
- [ ] Imported records → 409. Annotations go in linked `user_entered` records.
- [ ] Export all user-entered data + history. Delete per record or "all user-entered data" with a confirm token.
- [ ] Offline: edit controls disabled with "Edits need connection".
- [ ] Tests: create → edit → undo, delete, export round-trip, refusal on imported records.

---

### M1 — Calculations

### AG-14 Zones, thresholds, session load (TRIMP / Relative Effort)
`M1 · P1 · AG-05 · Linear: DEV-568`

**AC**
- [ ] HR zones from configured or observed HR max / LTHR, with method + date. **No age formula anywhere.** Missing → "HR max not configured".
- [ ] Pace zones from threshold pace. 5-zone default. Optional 7-zone threshold model (zones 6–7 for short sprints) via config.
- [ ] **Threshold calibration** (Athletica test-week idea):
  - Detect candidate thresholds from tagged test efforts or races: 5K test, 30-min TT, race best efforts.
  - Propose them as `observed` with method + date.
  - Applied only if the user confirms or `auto_accept_thresholds: true`.
- [ ] Per workout: time in zone, Banister TRIMP (constants from profile, documented), zone-weighted Relative Effort.
- [ ] No HR → labelled session-RPE fallback (RPE × minutes, `estimated`), else `missing`.
- [ ] Weekly RE vs **12-week weighted average** band → maintain / increase / recover hint (thresholds in config).
- [ ] Zone distribution per activity and per week / month.
- [ ] Hand-computed fixture tests.

### AG-15 Fitness / Fatigue / Form, Cardio Status, form forecast, overtraining warning
`M1 · P1 · AG-14 · Linear: DEV-569`

**AC**
- [ ] Daily load = sum of session loads. Rest day = 0 only when the day is covered by a sync, else unknown.
- [ ] CTL = 42-day EWMA, ATL = 7-day EWMA, TSB = CTL − ATL (convention documented). `calibrating` until 42 days of coverage.
- [ ] Cardio Status: calibrating / detraining / maintaining / productive / fatigued / overreaching. Thresholds in config.
- [ ] Ramp rate with a configurable warning.
- [ ] **Form forecast:** project CTL / ATL / TSB forward over planned sessions (planned load from plans.json). Clearly labelled "projection".
- [ ] **Overtraining warning:** fires when HRV trend down + TSB below threshold + execution below plan for N days. All thresholds in config. User toggle to disable.
- [ ] Optional subjective modifier (RPE / feel). Off by default, documented.
- [ ] Series for 1 / 3 / 6 / 12 / 24 mo. Tests against reference sequences, gaps, partial windows.

### AG-16 Recovery / readiness
`M1 · P1 · AG-05 · Linear: DEV-570`

**AC**
- [ ] Components:
  - HRV vs personal baseline (7-day vs 60-day)
  - RHR vs baseline
  - sleep debt
  - optional respiratory-rate deviation and prior-day strain
- [ ] Weights in config. Score 0–100 with each component's value, baseline, Δ, and contribution.
- [ ] Personal normal range (e.g. 34–67%) from the user's own distribution.
- [ ] Confidence high / medium / low from baseline length + today's coverage. Missing components excluded, re-weighted, and listed.
- [ ] No score when both HRV and RHR baselines are absent.
- [ ] Before the morning sync: yesterday's score shown as stale, never a new number.
- [ ] Tests: each component missing, short baseline, extremes, stale.

### AG-17 Sleep metrics
`M1 · P1 · AG-05 · Linear: DEV-571`

**AC**
- [ ] From stages (in bed, awake, core, deep, REM):
  - asleep, in bed, efficiency, time to fall asleep
  - stage minutes and %, disruptions (configurable threshold), bed / wake times
- [ ] Sleep need = base (config) + strain adjustment + debt repayment. Debt = rolling shortfall with decay. Documented.
- [ ] Regularity: SD of midpoints (7 / 14 d) and Sleep Regularity Index when ≥ 7 nights.
- [ ] Sleep score with components shown. In-bed-only nights → partial. Naps separate.
- [ ] Sleep ↔ recovery correlation only past min nights, else "Not enough nights (n/N)".
- [ ] Tests incl. tz boundaries.

### AG-18 Strain, Stress, Energy Bank
`M1 · P1 · AG-16, AG-17 · Linear: DEV-572`

**AC**
- [ ] Strain % (day and workout):
  - inputs: workout load + time above a configured HR floor outside workouts, exercise duration, daytime HR
  - shown against a personal normal range
- [ ] Stress (**Estimate**): daytime HR vs resting baseline + HRV samples, hourly + daily. Today's highest / lowest / average. Hidden when samples are insufficient.
- [ ] Energy Bank: morning charge from recovery + sleep, drained by strain + stress, using real samples only. Stops at the last sample time and never extrapolates.
- [ ] Documented formulas, min-data rules, tests.

### AG-19 Body weight trajectory + VO2 max trend
`M1 · P1 · AG-05 · Linear: DEV-573`

**AC**
- [ ] Weight:
  - weekly median, 4-week trend (kg/week)
  - projected date to the goal target
  - required vs actual rate to hit the goal date → on track / behind / ahead
  - target + date only from `goals.json`
  - fewer than 2 weeks of data → "Not enough weigh-ins (n/N)"
- [ ] VO2 max:
  - raw HealthKit points, smoothed trend (method documented)
  - current, Δ30 d, Δ90 d, confidence by sample density, gaps
  - **never estimated from pace**
  - empty → "No cardio-fitness samples yet"
- [ ] A generic trend helper reused for HRV, RHR, respiratory rate, steps, energy, BP, glucose, running form, HR recovery.
- [ ] Tests.

### AG-20 Activity analysis
`M1 · P1 · AG-14 · Linear: DEV-574`

**AC**
- [ ] Splits per km / mi, laps, intervals, multisport segments + transitions. Negative / even / positive split verdict.
- [ ] GAP only with elevation samples, labelled **approximate**.
- [ ] Efficiency factor (speed / avg HR, Friel). Intensity vs threshold % (GAP speed / threshold speed; HR / LTHR fallback). Both documented as AGame definitions.
- [ ] Best efforts:
  - distances: 400 m, 1 km, 1 mi, 5 K, 10 K, HM, M, 50 K, longest run
  - cycling and swim best efforts when present
  - top-10 per record from own history only
- [ ] HR curve (5 s…60 min) with an HR series. Power curve (5 s…20 min) only with power data, else omitted.
- [ ] HR recovery (60 s post-workout drop) only when post-workout HR samples exist.
- [ ] Matched runs: start geohash + distance bucket + shape similarity. Without GPS: "approximate match" from distance + start metadata, or none.
- [ ] Race predictions 5 K / 10 K / HM / M / 50 K from recent best efforts (Riegel, configurable exponent). Labelled **Estimate**, showing the source effort + date.
- [ ] Weather only if present in input. Never fetched.
- [ ] Tests with synthetic streams.

### AG-21 Goals engine, streaks, training-log totals, progress comparison
`M1 · P2 · AG-05 · Linear: DEV-575`

**AC**
- [ ] Goal types: distance, time, elevation, calories, kJ, Relative Effort / load, streak, record-by-date, segment, strength (e1RM / volume), body weight, nutrition (protein days hit), habit.
- [ ] Periods: week / month / year / custom.
- [ ] Each goal gets progress, expected-by-now marker, projection, and status. Partial period flagged.
- [ ] Streaks: weekly activity streak + per-goal day streaks. Schedule-aware rest days.
- [ ] Totals by sport per week / month / quarter / year, vs prior period and vs same period last year.
- [ ] Progress comparison: any period vs prior equal period (Strava Progress: total, % delta, overlay series).
- [ ] No goal → "No goal set". Never a default target.
- [ ] Tests.

### AG-22 Insight engine — evidence-backed summaries and recommendations
`M1 · P2 · AG-15…AG-21 · Linear: DEV-576`

**AC**
- [ ] Rule catalog in config (id, inputs, condition, evidence, short template). Every insight lists the exact numbers it uses.
- [ ] Daily call: train as planned / reduce / swap / rest, with factors (recovery, TSB, sleep debt, ramp, activity status, planned session, overtraining flag).
- [ ] "One action today" = highest-priority actionable rule.
- [ ] Helping / hurting over 7 / 30 / 90 d. Correlations only past min-n and an effect threshold, else "Not enough observations (n/N)".
- [ ] Activity summary (Athlete Intelligence parity): vs last 30 days and same route / distance, plus 2–3 concrete improvements.
- [ ] Recovery insight card text (≤ 2 lines, Bevel style), e.g. "HRV 31.3 ms vs usual 56.8 ms".
- [ ] Tone variants for coach personalities change wording only, never facts.
- [ ] A banned-phrases test blocks diagnosis language.

### AG-23 Muscular Load + Muscle Freshness (new)
`M1 · P2 · AG-05 · Linear: new (was inside DEV-585)`

**AC**
- [ ] Per muscle group, from exercise-level strength logs (weight × reps × sets, RPE).
- [ ] Load status (Bevel parity): productive / maintaining / overtraining / detraining.
  - Calibration: 1–2 workouts/week per muscle over 6 weeks; until then `calibrating`.
- [ ] Freshness: recovered / fatigued / depleted.
  - Calibration: 3 recent workouts for that muscle.
- [ ] Cardio contribution via a **config mapping per activity type** (e.g. run → quads, hamstrings, calves, glutes), labelled approximate, can be switched off.
- [ ] **Never inferred from a generic strength workout.** No exercise logs → `missing`.
- [ ] Tests.

### AG-24 Nutrition calculations (new)
`M1 · P2 · AG-05 · Linear: new (was inside DEV-588)`

**AC**
- [ ] Daily totals: kcal, protein, carbs, fat, fiber, micros present, water, caffeine. Macro g and %.
- [ ] Protein vs configured target (150 g lives in data): today, 7-day average, days hit / days logged, per-meal distribution.
- [ ] Net energy = consumed − (active + resting energy), with logging coverage. Incomplete days flagged partial.
- [ ] Nutrition Score (Bevel 2.0 style), documented:
  - protein adherence, energy balance vs goal, fiber, meal regularity
  - **quality contributors** (vegetables vs configured daily target, whole grains, red meat, sodium, sugar) only when food-group data exists
  - each contributor shown as +N / −N
- [ ] No nutrition data → everything `missing`.
- [ ] Tests.

---

### M1 — Core screens

### AG-25 Today
`M1 · P1 · AG-22 · Linear: DEV-577`

**AC**
- [ ] Header: date, Activity Status chip, freshness chip, weather chip only if supplied.
- [ ] Three rings **Strain · Recovery · Sleep** with Δ vs baseline. Tap opens the detail page.
- [ ] Morning brief card: ≤ 2 lines + "View insights" (from AG-22, no free prose).
- [ ] Recommendation with the top 3 helping / hurting factors.
- [ ] Today's plan:
  - planned session(s) with type, target, guiding metric
  - "Rest day" or "Nothing planned"
  - calendar conflicts listed
- [ ] Stress & Energy card: today's highest / lowest / average + Energy Bank bar.
- [ ] Load card: Form (TSB) + Cardio Status + week's Relative Effort vs range.
- [ ] Since yesterday: HRV, RHR, sleep, weight Δ. Missing → "—" + reason.
- [ ] Yesterday's training rows. Goals strip (weight, running, strength, protein). One action today.
- [ ] Big Day Brief card when applicable (AG-34).
- [ ] 390×797 dark + light inspected. Desktop 2–3 column grid.

### AG-26 Recovery
`M1 · P1 · AG-16, AG-18 · Linear: DEV-578`

**AC**
- [ ] Ring hero ("41% Recovered") + date picker + confidence + coverage.
- [ ] HRV and RHR tiles with ▲/▼ vs usual. Component rows with contribution. Missing components listed.
- [ ] Insight card + Recovery timeline (intraday).
- [ ] Trends: recovery (with normal-range band), HRV (raw + 7-day + baseline band), RHR, respiratory rate. D…All with gaps.
- [ ] Stress chart (**Estimate**) + Energy Bank curve.
- [ ] Helping / hurting with a window picker.
- [ ] Prehab module (Recover Athletics parity): user routines, completion history, no medical claims. Empty → "No prehab routines yet".
- [ ] 390×797 inspected.

### AG-27 Sleep
`M1 · P1 · AG-17 · Linear: DEV-579`

**AC**
- [ ] Score ring, asleep vs need, debt, efficiency, consistency.
- [ ] Hypnogram with Bevel stage colors + 2×2 stage tiles (duration · % · mini ring). Disruptions marked.
- [ ] "Sleep needed" and "Time to fall asleep" rows.
- [ ] Bed / wake chart with regularity band (14 / 30 / 90 d). Trends D…All.
- [ ] Sleep → recovery correlation (gated). Naps listed separately.
- [ ] Smart alarm settings (companion contract) with "Requires companion app — this page cannot wake you".
- [ ] 05:30 state: "Sleep not synced yet · last {date}".
- [ ] 390×797 inspected.

### AG-28 Training
`M1 · P1 · AG-15, AG-21 · Linear: DEV-580`

**AC**
- [ ] Fitness & Freshness chart (CTL, ATL, TSB area), 1 / 3 / 6 / 12 / 24 mo, tap shows the day's activities, calibrating marked. Form forecast dashed beyond today.
- [ ] Cardio Status + ramp rate + overtraining flag.
- [ ] Progress (Strava parity): sport chip + metric chips (distance / time / elevation / load), current vs prior period overlay, total + % delta.
- [ ] Training Log calendar (week rows, bubbles sized by load, colored by sport) + list view. Period totals with prior-period Δ.
- [ ] Weekly Relative Effort chart with 12-week band + hint.
- [ ] Zone distribution over time. Best efforts + race predictions. Links to Weekly review and Year in Sport.
- [ ] 390×797 inspected (week rows wrap, no page scroll).

### AG-29 Activities list + activity detail (post-workout report)
`M1 · P1 · AG-20, AG-22 · Linear: DEV-581`

**AC**
- [ ] List: Strava-style cards (sport, local date / time, stat row, mini SVG trace, PR badges). Filters (sport, date, GPS, PR, planned / unplanned). Search.
- [ ] Detail tabs **Summary · Analysis · Chat · Planned**:
  - **Summary:**
    - outcome headline
    - stat grid (run: distance / time / elevation / achievements; strength: elapsed / volume / sets / avg HR)
    - compliance banner + plan-vs-actual table (duration, moving time, distance, load)
    - activity summary + 2–3 improvements, best efforts set
    - Relative Effort + zone bars, matched-runs comparison
    - weather if supplied
  - **Analysis:**
    - multi-metric overlay chart (pace, HR, power, cadence, elevation, running form; each only if present) with zone bands
    - Session ↔ Time in Zone toggle
    - splits + verdict, laps / intervals, GAP (approx), HR curve, power curve (if power), EF, intensity %
  - **Chat:** Coach scoped to this activity (AG-44). "Coach chat not connected" without an LLM.
  - **Planned:** the planned session it matched, or "Unplanned".
- [ ] Map with privacy zones. Flyover-style replay (respects reduced motion). Needs GPS, else "Route data unavailable".
- [ ] Post-workout form: RPE slider (1–10 with descriptors), feel (5 faces with text labels), comment. Saved via AG-13.
- [ ] Quick Edit: title, race tag, private flag (overlay only).
- [ ] Race view when tagged race: plan vs actual pace, finish vs prediction.
- [ ] 390×797 inspected for a GPS run and a strength session.

### AG-30 Body
`M1 · P2 · AG-19 · Linear: DEV-582`

**AC**
- [ ] Weight: points + weekly median + trend + goal line, status with required vs actual kg/week.
- [ ] Body composition only if samples exist.
- [ ] VO2 max card + chart (raw, smoothed, Δ30 / Δ90, confidence, gaps).
- [ ] Blood pressure (HealthKit or manual), no diagnostic category labels. Glucose / CGM only with samples.
- [ ] Entries to Biological Age and Health Records (AG-46).
- [ ] 390×797 inspected.

### AG-31 Goals
`M1 · P2 · AG-21 · Linear: DEV-583`

**AC**
- [ ] Card per goal: ring / bar, expected-by-now marker, projection, status, as_of.
- [ ] Weight trajectory (75 kg by 2027-01-01, from data), protein adherence (150 g from data), running, and strength goals.
- [ ] Streaks. Segment goals only if segments exist.
- [ ] Create / edit / archive via AG-13 with undo. Empty → "No goals set".
- [ ] 390×797 inspected.

### AG-32 Training calendar + Plan Your Week (new split)
`M1 · P2 · AG-13, AG-15 · Linear: DEV-584 (part)`

**AC**
- [ ] One calendar holding past activities, planned sessions, and calendar events (Bevel Training Calendar). Day / Week / Month views. Filter by type.
- [ ] Week header (Athletica): **Actual vs Planned** sessions · duration · load.
- [ ] Week grid tiles: type code (AER, TMP, VO2, REC, STR, LR, RACE, NPU = unplanned), load with planned in brackets, duration, compliance border with a text label.
- [ ] Planned sessions auto-link to completed workouts (same day + type + duration tolerance, configurable). Compliance = as planned / partial / missed / unplanned.
- [ ] Drag-and-drop to move sessions (keyboard alternative: "Move to…" menu). Edits go through AG-13 with undo.
- [ ] Template library: save a session as a template. Editing a template offers to update future sessions built from it.
- [ ] Conflicts: planned session overlaps a calendar event or exceeds available time.
- [ ] 390×797 inspected.

### AG-33 Adaptive plans, Workout Wizard, instant workouts (new split)
`M1 · P2 · AG-32, AG-22 · Linear: DEV-584 (part)`

**AC**
- [ ] Plan = goal + phases + planned sessions.
  - Built from the default weekly template in data: Mon run, Tue + Wed lift, Thu run, Fri rest, weekend optional run.
  - Created by user / Steve as data, or by Coach when an LLM is connected.
- [ ] Races with **A / B / C priority** (taper only for A). **Train-to-maintain** mode when no target race.
- [ ] Adaptation rules (documented, each change shows its reason, original target kept visible):
  - missed / moved session → re-flow
  - low recovery or overtraining flag → swap to easier
  - Activity Status sick / injured / traveling → **"Not feeling 100%"** restructure
  - strength session cancelled or shortened on poor recovery
  - pace targets adjusted only after a **consistent** pattern across N tempo / interval sessions, not one session
- [ ] **Workout Wizard:** each future session offers alternatives (shorter, longer, format variation, easier, harder, recovery). Picking one only minimally changes the rest of the week.
- [ ] **Instant workouts:** Maintain / Build / Explore / Recover suggestions from recent history, explained. Routes only from the user's own library.
- [ ] Heat adjustment of pace targets: contract only, used when forecast temperature is supplied in data.
- [ ] 390×797 inspected.

### AG-34 Big Day Brief + pre-workout guidance (new split)
`M1 · P2 · AG-33 · Linear: DEV-584 (part)`

**AC**
- [ ] Pre-workout card for every planned session: objective, steps, targets, guiding metric, and what to watch.
- [ ] Big Day Brief when the session is long or hard (thresholds in config):
  - evening before: sleep target, fuel, kit checklist from config
  - morning of: readiness check, pacing targets from zones, go / adjust call with factors
- [ ] Appears on Today and on the session detail.

### AG-35 Routines — structured cardio + strength, Watch export (new split)
`M1 · P2 · AG-32 · Linear: DEV-584 (part)`

**AC**
- [ ] Routine builder with Bevel step list:
  - warm-up / work / recovery / repeat ×N / cool-down
  - each step: duration or distance + target (HR range, pace range, power, zone, open)
  - extended warm-up / cool-down options
- [ ] **Guiding metric per session** (Athletica "intelligent mode"): HR for easy / aerobic, pace or power for intervals. Rules in config.
- [ ] Routines can be scheduled onto the calendar.
- [ ] Apple Watch export **contract**: WorkoutKit-shaped JSON, documented. No claim of sync without a companion.
- [ ] 390×797 inspected.

### AG-36 Strength
`M1 · P2 · AG-23 · Linear: DEV-585`

**AC**
- [ ] Session history: HealthKit strength workouts merged with exercise logs when present.
- [ ] Per exercise: volume, heaviest weight, e1RM (Epley, labelled estimate), total reps, PRs, progressive-overload chart.
- [ ] Muscle map front / back (Strava style: trained groups highlighted on a dark body). States fresh / recovering / fatigued with text + pattern, not color alone.
- [ ] Muscular Load statuses per group (AG-23).
- [ ] Session-only workouts → "No exercise details — muscles not inferred".
- [ ] Weekly volume / sessions / time.
- [ ] 390×797 inspected for both data cases.

### AG-37 Weekly review + Steve weekly aggregates
`M1 · P2 · AG-21, AG-22 · Linear: DEV-586`

**AC**
- [ ] Build emits `dist/weekly_review.json` + a Weekly review view.
- [ ] Contents:
  - week in numbers, 4-week training log, CTL / ATL / TSB
  - recovery + sleep trends, protein adherence, weight median
  - goal trajectories, best efforts, compliance %, next week's plan intent
- [ ] Weekly totals equal the sum of the days (tested). Partial week flagged.
- [ ] Month in Sport uses the same mechanism.

### AG-38 Profile / settings
`M1 · P2 · AG-13 · Linear: DEV-587`

**AC**
- [ ] Profile:
  - timezone (default Africa/Kigali), units, week start
  - TRIMP constants, HR max + method + date, LTHR, threshold pace
  - zones (5 / 7 model), sleep base need, tab choice
- [ ] Targets: protein, kcal, macros, water, caffeine + cutoff, vegetables / day. Every edit has history + undo.
- [ ] Theme (system / dark / light). App icon choice.
- [ ] Integrations panel showing the truthful status per source: HealthKit-via-Steve last sync per domain, nutrition, map provider, LLM, calendar, companion apps.
- [ ] Privacy zones, default activity privacy. Modules: cycle tracking (off), health records, social.
- [ ] Data: export, delete user data, edit history, undo.
- [ ] Coach: personality, tone, language complexity, check-in schedule.

### AG-39 Customizable charts + Personal Records hub (new)
`M1 · P3 · AG-20, AG-09 · Linear: new`

**AC**
- [ ] Pin and reorder charts (Bevel parity), saved in config. Day / week aggregation. Year-to-date view.
  - Activity: duration, distance, energy, pace, speed, HR, power, cadence.
  - Cardio: VO2 max, HR recovery, HR zones.
  - Exercise: e1RM, heaviest, volume, sets, reps.
  - Muscle: volume, sets, load, freshness.
  - Metrics: any present series (HRV, RHR, respiratory rate, steps, energy, weight, BP, glucose, running form).
- [ ] Metrics without samples are not offered.
- [ ] PR hub:
  - strength (heaviest, e1RM, session / set volume, set reps)
  - running (longest, fastest 5 K…M, 50 K)
  - cycling (longest, elevation, fastest, best power 5 s–20 min if power)
  - swimming (longest, fastest pool / open water)
  - tap a record → top-10 efforts
- [ ] Desktop: under Body / Training. Mobile: More → Records.

---

### M2 — Extended features

### AG-40 Nutrition
`M2 · P2 · AG-24, AG-13 · Linear: DEV-588`

**AC**
- [ ] No data → "Nutrition not connected". No zeros.
- [ ] Protein hero: today vs target, 7-day adherence, per-meal distribution.
- [ ] Macro card: g / % toggle, dot-matrix columns. Remaining "g left" per macro.
- [ ] Net energy scale. Nutrition Score with contributor rows.
- [ ] Diary + meal timeline. Micros present. Water and caffeine (with cutoff).
- [ ] Entry: text / describe-meal (manual fields), barcode field (number only unless a food DB is configured), photo slot ("Photo recognition not connected" unless configured), recipes, favorites.
- [ ] Editing: copy meal / copy day / copy foods across dates, change date / time, multi-select, make recipe from items, delete with undo.
- [ ] Future-date meal planning. CGM overlay only with glucose samples. Conversational logging via Coach when connected.
- [ ] 390×797 inspected (empty and populated).

### AG-41 Strength Builder
`M2 · P2 · AG-23, AG-13 · Linear: DEV-589`

**AC**
- [ ] Exercise library as **config** (name, muscles, equipment, pattern, form cues, scaling notes). User-extendable.
- [ ] Routines / templates / planned sessions. Log live or **log past workouts**.
  - sets × reps × weight, RPE / RIR, warm-up flag, supersets, notes
- [ ] RPE-anchored targets (e.g. "8 reps @ RPE 8"). Progression hint from the last session.
- [ ] Rest timer (works offline). Plate calculator (bar + available plates from config, kg / lb).
- [ ] Live workout state **contract** for future phone / watch sync.
- [ ] Import contract for strength-app exports (Hevy / Strong / Lyfta-style CSV mapped to `strength.json`), documented.
- [ ] AI-generated sessions only when Coach is connected.
- [ ] Tap targets ≥ 44 px. 390×797 inspected.

### AG-42 Routes
`M2 · P2 · AG-20 · Linear: DEV-590`

**AC**
- [ ] Library cards: SVG trace, "distance · elevation · est. time" (own recent pace), times run, favorite.
- [ ] Filter chips: Length / Elevation / Surface / Difficulty (difficulty defined in config).
- [ ] Detail: map, elevation profile, surface breakdown bar (if tagged), matched activities + best times.
- [ ] SVG on a neutral grid by default. Tiles only if configured.
- [ ] Builder: draw / edit when tiles are configured, else "Map provider not configured". GPX / GeoJSON import always works.
- [ ] Recommendations from the own library only (target distance, surface, recency).
- [ ] Save offline (SW cache). Saved list visible offline.
- [ ] Privacy zones applied on every map and export (tested).
- [ ] 390×797 inspected.

### AG-43 Heatmap, segments, leaderboard contract
`M2 · P3 · AG-42 · Linear: DEV-591`

**AC**
- [ ] Personal heatmap with range + sport filters, **night** view (sunset–sunrise by documented solar formula), weekly view.
- [ ] User-defined segments: history, PR, trend, segment goals.
- [ ] Leaderboards only from supplied `social.json` data, with source. Filters: all / men / women / age / weight / followers / clubs / this year / today. CR crown. Empty → "No leaderboard data connected".
- [ ] Integrity flags on imported efforts (implausible speed, GPS jump, vehicle-like acceleration) + flagging contract.
- [ ] Live Segments: contract (AG-50).
- [ ] Tests: night classification, segment matching, privacy on heatmap.

### AG-44 Coach
`M2 · P2 · AG-22 · Linear: DEV-592`

**AC**
- [ ] Without an LLM: daily summary, readiness call with factors, helping / hurting, weekly summary (AG-22).
- [ ] With an LLM:
  - Q&A over the computed snapshot + memory only
  - answers cite metric keys + dates
  - refuses diagnosis
  - **never sees Strava data**
- [ ] Greeting + suggestion chips ("Create a training plan", "Log food", "Why is recovery low?"). Input with a mode chip **Fast / Thinking / Adaptive**.
- [ ] Personalities: Data Nerd / Guardian / Friend / Commander. Tone + language complexity (Athletica). Same facts.
- [ ] Generated charts: the LLM returns a chart spec, the chart lib renders computed data. No LLM numbers.
- [ ] Memory store (Files parity) in `coach.json`: preferences, goals, corrections, saved artifacts. View / edit / delete with history.
  - Overnight memory maintenance job (Steve runs it) compacts and dedupes.
- [ ] Plan actions: create / adjust plans and schedule sessions → writes via AG-13 after confirmation.
- [ ] Proactive check-ins: schedule stored as data (morning report, log reminders, e.g. "creatine 15:00", goal progress, weekly / monthly). Steve delivers them.
- [ ] Ghost Mode: nothing persisted, visible indicator, no content in logs.
- [ ] Citations only when a source is supplied. Empty → nothing rendered (tested).
- [ ] 390×797 inspected.

### AG-45 Timeline, Journal, Activity Status, cycle tracking
`M2 · P3 · AG-13 · Linear: DEV-593`

**AC**
- [ ] Day timeline: sleep, meals, workouts, scores, measurements, notes, planned events. Pinned scores / macros at the top. Day picker, filters.
- [ ] Journal: mood, hydration, sunlight, screen time, caffeine, symptoms, travel, sickness, custom habits (from config).
- [ ] Activity Status: normal / sick / traveling / injured / recovering, set by user or source, with a date range. Feeds AG-33 and shows on Today.
- [ ] Cycle tracking hidden unless enabled. Logs + phase from user / HealthKit only. No predictions shown as fact.
- [ ] Journal factors feed correlations only past min-n.

### AG-46 Health Records + Biological Age
`M2 · P3 · AG-13, AG-19 · Linear: DEV-594`

**AC**
- [ ] Records:
  - labs and biomarkers (value, unit, the lab's own reference range, date)
  - notes, PDFs in the private dir behind auth
  - trend per biomarker
- [ ] Excluded from Coach (unless toggled), SW cache, and widgets. No diagnostic verdicts.
- [ ] Manual entry. PDF extraction only if a parser / LLM is configured.
- [ ] Biological Age only when the required inputs exist:
  - inputs: sleep, steps, zone time, strength time, optional 9 PhenoAge biomarkers
  - weekly (Monday) over rolling 30 days
  - shows gauge, years ±, Δ vs last week, next-update countdown, confidence %
  - category rows (Sleep / Activity / Fitness / Blood), methodology, **Estimate** label
  - missing inputs → list of what's needed
- [ ] PhenoAge formula tested against a published worked example.

### AG-47 Social + challenges (empty by default)
`M2 · P4 · AG-13 · Linear: DEV-595`

**AC**
- [ ] `social.json`: athletes (opt-in), follows, clubs, posts, kudos, comments, challenges (monthly + private friend challenges), progress, segment efforts. Every record has source + consent.
- [ ] Views: feed (Strava card), clubs, challenges with progress, comments + kudos on my activities.
- [ ] Empty states everywhere. Test scans the built HTML for fixture names.
- [ ] Self-made challenges work from my own data now.
- [ ] Events: races / events from user data, linked to plans (A/B/C).

### AG-48 Year in Sport + Month in Sport
`M2 · P3 · AG-21 · Linear: DEV-596`

**AC**
- [ ] Contents:
  - totals by sport, longest and fastest efforts, PRs
  - consistency (active weeks, streaks), best / worst months
  - sleep + recovery averages, strength volume, goal progress, weight change
- [ ] Month version uses the same structure. Partial periods flagged.
- [ ] Share card (SVG / PNG) with privacy zones, no health records.

### AG-49 Widgets
`M2 · P4 · AG-07 · Linear: DEV-597`

**AC**
- [ ] Small / medium / large cards: three rings, Recovery, Sleep, Strain, Energy, Today's plan, Protein, Hydration gauge, Weight trajectory, Weekly load, Goal.
- [ ] Same computed keys as the full screens. as_of + stale on every card.
- [ ] Gallery in Profile. Pin to a Today custom row on desktop.
- [ ] `dist/widgets.json` contract for a future native widget. No health records.

### AG-50 Companion contracts
`M2 · P4 · AG-02 · Linear: DEV-598`

**AC**
- [ ] Schemas + docs for:
  - Beacon (session, contacts, expiring link, position stream, stop)
  - smart alarm (window, target, stage rule)
  - live workout state
  - Live Segments (segment id, elapsed, Δ vs PR)
  - Watch workout export
- [ ] UI settings show "Companion not connected". No button pretends to start live tracking.
- [ ] Schemas validated by tests.

---

### M3 — Ship

### AG-51 Unit + integration tests
`M3 · P1 · all calc issues · Linear: DEV-599`

**AC**
- [ ] Coverage:
  - schemas + migrations; recovery + missing data
  - TRIMP / RE, CTL / ATL / TSB, forecast; zones + threshold proposals
  - weight trajectory + goals; best efforts, PRs, splits, matched runs, route privacy
  - muscular load gating, nutrition score gating
  - tz + period boundaries; idempotent imports + duplicate IDs; stale / partial
  - auth; edit history + undo; plan ↔ workout linking + compliance
  - build determinism
- [ ] "No zero for missing", "no fabricated content", and public-repo guard tests.
- [ ] Suite < 60 s. Summary in `dist/test_report.json`.

### AG-52 Playwright E2E + screenshots
`M3 · P1 · all screens · Linear: DEV-600`

**AC**
- [ ] iPhone 390×797 dark + light. Desktop 1440×900.
- [ ] PWA installability. Offline reload shows the snapshot + timestamp.
- [ ] All 12 destinations via tabs, More, and sidebar. Sheets (Esc / back), tooltips (tap / hover), drag-and-drop + keyboard move, empty-state copy.
- [ ] No horizontal overflow on any page. Accessibility checks (labels, contrast, focus).
- [ ] Screenshots to `docs/screenshots/` (synthetic data, labelled): every destination dark at 390×797, Today light, Today desktop.

### AG-53 Docs
`M3 · P2 · — · Linear: DEV-601`

**AC**
- [ ] `README.md`: setup, build, run, test, Railway. Commands work from a clean clone.
- [ ] `docs/product.md`: every displayed term + feature-to-screen matrix (§9) + token table.
- [ ] `docs/calculations.md`: every formula, window, constant, confidence rule, limitation, reference.
- [ ] `docs/deployment.md`: auth setup, env vars, private data repo, backup, rollback, daily + weekly flow.
- [ ] `AGENTS.md`: ground rules (§2) + "prove with tests and build report before deploy".
- [ ] List of features needing extra data / services, each with its exact input contract.

### AG-54 Railway deploy
`M3 · P2 · AG-12 · Linear: DEV-602`

**AC**
- [ ] `Dockerfile` (python:3.12-slim, non-root, code only). `railway.toml` (start, `/healthz`, restart policy).
- [ ] Volume at `AGAME_DATA_DIR`. Data arrives via pull from the private repo (deploy key in env) or an authenticated `POST /api/snapshot`.
- [ ] Rebuild on new data. A failed build keeps the last good snapshot. Keeps 7 snapshots. A pin flag allows rollback.
- [ ] Local `docker build && docker run` smoke test passes.

### AG-55 Steve's morning + weekly automation
`M3 · P1 · AG-04, AG-06, AG-51 · Linear: DEV-603`

**AC**
- [ ] Runbook (before 06:00 CAT):
  1. pull HealthKit
  2. `update_from_healthkit.py`
  3. validate, build, unittest
  4. read `build_report.json`
  5. send `dist/fitness_dashboard.html`
  6. commit data + dist to the **private** repo
  7. optional Railway push
- [ ] Decision table for exit codes 0 / 2 / 1.
- [ ] 05:30 rule: build degraded without sleep, rebuild when sleep lands.
- [ ] Check-in delivery from the `coach.json` schedule. Overnight memory maintenance step.
- [ ] Monday: read `weekly_review.json`.
- [ ] Dry run: 3 synthetic days, rerun of day 2 (idempotent), one day missing sleep. All pass.

### AG-56 Visual fidelity pass
`M3 · P2 · AG-52 · Linear: DEV-604`

**AC**
- [ ] Compare every destination to the PDF screenshots (§4). Add sharper real-device captures to `docs/reference/` if you can provide them.
- [ ] Adjust tokens / components. Side-by-side images per destination.
- [ ] Token table in `docs/product.md`. Owner sign-off.

---

## 8. Build order

1. **Week-1 slice:**
   - Steve can run the full loop on real data: AG-01…06, AG-10, AG-51 basics, AG-55 dry run.
   - Today shows recovery / sleep / strain / load: AG-14…19, AG-25.
2. Core screens: AG-26…31, AG-36, AG-37, AG-38.
3. Planning layer: AG-32…35, AG-22, AG-39.
4. Extended: AG-40…50.
5. Ship: AG-52…54, AG-56.

---

## 9. Feature-to-screen matrix

Legend:
- **Built** = works from HealthKit data now.
- **Contract** = real UI + schema with an honest empty state until the named data or service exists.

| Feature | Source | Screen | Status | Issue |
|---|---|---|---|---|
| Relative Effort + weekly vs 12-wk avg | Strava | Activities, Training | Built (HR) / RPE fallback | AG-14 |
| Fitness / Fatigue / Form | Strava, Bevel, Athletica | Training, Today | Built | AG-15 |
| Form forecast, overtraining warning | Athletica | Training | Built | AG-15 |
| Training Log, totals, comparisons | Strava | Training | Built | AG-21, AG-28 |
| Progress comparison | Strava | Training | Built | AG-21 |
| Matched Runs | Strava | Activity | Built (GPS) | AG-20 |
| Zones, custom zones, distribution | Strava | Training, Activity | Built | AG-14 |
| Threshold calibration / 7-zone option | Athletica | Profile, Training | Built | AG-14 |
| HR curve / power curve | Strava | Activity | Built / Contract (power meter) | AG-20 |
| GAP, splits, laps, intervals, multisport, race analysis | Strava, Bevel | Activity | Built | AG-20, AG-29 |
| EF, intensity vs threshold, compliance | Athletica | Activity | Built | AG-20, AG-32 |
| Performance predictions | Strava | Training | Built, estimate | AG-20 |
| Weather on activity | Strava | Activity | Contract | AG-20 |
| Best efforts, PRs, top-10 | Strava, Bevel | Training, Records | Built | AG-20, AG-39 |
| Custom goals, streaks | Strava | Goals | Built | AG-21, AG-31 |
| Training plans, adaptive, A/B/C, maintain | Strava/Runna, Bevel, Athletica | Training | Built (rule-based) | AG-33 |
| Workout Wizard alternatives | Athletica | Session detail | Built | AG-33 |
| Instant workouts | Strava | Training, Today | Built | AG-33 |
| Not Feeling 100% / heat-adjusted pace | Runna | Training | Built / Contract (forecast) | AG-33 |
| Training calendar, Plan Your Week, templates | Bevel, Athletica | Training | Built | AG-32 |
| Routines + structured steps + Watch export | Bevel, Athletica | Training | Built + Contract | AG-35 |
| Pre-workout guidance, Big Day Brief | Athletica, owner | Today | Built | AG-34 |
| Post-workout RPE / feel / comment | Athletica | Activity | Built | AG-29 |
| Athlete Intelligence summaries | Strava | Activity | Built (deterministic) | AG-22 |
| Year / Month in Sport | Strava | Training | Built | AG-48 |
| Flyover, Quick Edit | Strava | Activity | Built (GPS) | AG-29 |
| Route library, offline, privacy | Strava | Routes | Built (GPS) | AG-42 |
| Route builder / recommendations | Strava | Routes | Contract (tiles) / Built (own routes) | AG-42 |
| Personal / night / weekly heatmap | Strava | Routes | Built (GPS) | AG-43 |
| Segments, goals | Strava | Routes | Built (own) | AG-43 |
| Leaderboards, integrity, Live Segments | Strava | Routes | Contract | AG-43, AG-50 |
| Feed, clubs, kudos, friend challenges, events | Strava | Social | Contract (own challenges built) | AG-47 |
| Beacon, smart alarm | Strava, Bevel | Profile, Sleep | Contract | AG-50 |
| Custom app icon, prehab | Strava | Profile, Recovery | Built | AG-38, AG-26 |
| Recovery + factors + confidence | Bevel | Today, Recovery | Built | AG-16 |
| Sleep score, need, debt, stages, regularity | Bevel | Sleep | Built | AG-17 |
| Strain, Stress (estimate), Energy Bank | Bevel | Today, Recovery | Built | AG-18 |
| Cardio Load / Status | Bevel | Training | Built | AG-15 |
| Muscular Load, Freshness, Muscle Map | Bevel, Strava | Strength | Built (exercise logs) | AG-23, AG-36 |
| Strength Builder, timer, plate calc, past logs | Bevel | Strength | Built | AG-41 |
| Strength-app import | Strava | Strength | Contract | AG-41 |
| Customizable charts | Bevel | Body, Training | Built | AG-39 |
| VO2 max, HRV, RHR, weight trends | Bevel, owner | Body | Built | AG-19 |
| Blood pressure | Bevel | Body | Built | AG-30 |
| Nutrition diary, macros, net energy, score, protein | Bevel | Nutrition | Contract until logged, then Built | AG-24, AG-40 |
| Barcode / photo / recipe / favorites / copy | Bevel | Nutrition | Manual Built; DB / vision Contract | AG-40 |
| CGM | Bevel | Nutrition, Body | Contract | AG-40 |
| Timeline, journal, Activity Status | Bevel | Today › Timeline | Built | AG-45 |
| Cycle tracking | Bevel | Body (opt-in) | Built, hidden | AG-45 |
| Health Records | Bevel | Body | Built (manual) | AG-46 |
| Biological Age | Bevel | Body | Contract until inputs | AG-46 |
| Widgets | Bevel | Profile, Today | Built + export | AG-49 |
| Q&A, generated charts | Bevel, Strava, Athletica | Coach | Contract (LLM key) | AG-44 |
| Train / rest call, helping / hurting | Bevel | Today, Coach | Built | AG-22 |
| Check-ins, nudges | Bevel | Coach | Built (Steve delivers) | AG-44, AG-55 |
| Memory, personalities, modes, Ghost Mode | Bevel | Coach | Built | AG-44 |
| Citations | Bevel | Coach | Contract (source only) | AG-44 |
| Weekly review, weight trajectory, annual recap | Owner | Training, Body | Built | AG-37, AG-19, AG-48 |

---

## 10. Out of scope (and why)

| Item | Why |
|---|---|
| Two-way device sync (Garmin, Coros, Wahoo, Concept2, Oura) | HealthKit via Steve is the only source. Watch export is a contract only (AG-35). |
| Strava / Bevel / Athletica APIs | Forbidden by the brief. No public Bevel API. |
| Athletica Velocity live classes | Third-party live human coaching service. |
| Athletica coach platform (multi-athlete, billing) | AGame is single-owner. |
| Pricing, credits, family / student plans, partner discounts | AGame has no subscriptions. |
| Athletica "Workout Reserve", "mWR", best-effort rating | Definitions not documented in the sources. Not invented. Revisit if a definition is supplied. |

---

## 11. Linear mapping (existing issues → this plan)

| Linear | Plan | Note |
|---|---|---|
| DEV-554…DEV-567 | AG-00…AG-13 | Update bodies from this doc |
| DEV-568…DEV-576 | AG-14…AG-22 | AG-14, 15, 18, 20, 22 gained Athletica / Bevel detail |
| — | AG-23, AG-24 | **New** issues |
| DEV-577…DEV-583 | AG-25…AG-31 | AG-25 and AG-29 gained screenshot-driven layout |
| DEV-584 | AG-32 | Retitle. Create **new** AG-33, AG-34, AG-35 |
| DEV-585, DEV-586, DEV-587 | AG-36, AG-37, AG-38 | Update |
| — | AG-39 | **New** |
| DEV-588…DEV-598 | AG-40…AG-50 | Update |
| DEV-599…DEV-604 | AG-51…AG-56 | AG-56 now partly unblocked |

**Total: 57 issues** (51 existing updated + 6 new).
