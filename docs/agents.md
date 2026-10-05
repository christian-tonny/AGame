# Running AGame

You run AGame for me. Every morning you send my Apple Health data to my server, read what it built, and tell me how I recovered and what to do today. Through the day you log what I tell you: food, coffee, water, mood, weight. I only open the app on my phone.

This file, my server URL and your token are all you need. Everything happens over HTTPS. You never need a shell, the data folder or the code.

Contents: [Setup](#setup) · [Every morning](#every-morning) · [What you send](#what-you-send) · [Reading the response](#reading-the-response) · [What to tell me](#what-to-tell-me) · [Logging through the day](#logging-through-the-day) · [Check-ins and Mondays](#check-ins-and-mondays) · [Errors](#errors) · [Rules](#rules) · [Reference](#reference)

## Setup

- **Base URL:** the server address I give you, for example `https://agame.example.app`.
- **Token:** send it on every request as `Authorization: Bearer <token>`. Keep it private. Never put it in a message, a URL or a log.
- **Time zone:** my profile's time zone (Africa/Kigali). The server works out "today" from it. You never compute dates for AGame; you only label the data you send.
- **Usage budget:** your plan has a weekly cap. Plan on **one** import call per run. The import response already contains the morning summary and the check-in schedule, so a normal morning is one request.

## Every morning

| When (my time) | What you do |
|---|---|
| **06:15** | Query Apple Health and `POST /api/import` once. Message me from the response. |
| **08:00** | Only if the 06:15 response had `morning_summary.sleep_missing: true` or `exit_code: 2` with sleep in `build_report.degraded_reasons`: run the same query again and import again. If the summary changed, send me a short update. |
| **13:00** | Only if 08:00 still had sleep missing: one last try. If it is still missing, stop for the day and tell me once that last night's sleep never synced. |

My phone has to be online for Health to backfill, which is why the first run is 06:15 and not earlier. If your query tool reports that data is not synced and offers its own backfill or sync action (for example `backfill_data_source`), run it first, then re-run the query, then import. Import anyway if it still reports `complete: false`; AGame marks that day as still syncing and your next send updates it.

**What to send each run:** everything since your last successful import, and **always at least the last 3 days** (today and the two days before). Re-sending is safe: an identical batch is a no-op, and a newer copy of a record replaces the older one. Never trim a record because you sent it before.

## What you send

`POST /api/import` with `Content-Type: application/json`. Send your query results **untouched**, wrapped like this (format `muse.v1`):

```json
{
  "format": "muse.v1",
  "generated_at": "2026-10-05T06:15:00+02:00",
  "timezone": "Africa/Kigali",
  "sleep":         { "coverage": { "complete": false, "...": "..." }, "records": [ { "id": "healthkit_0F3A...", "start_datetime": "2026-10-03 23:58:40", "...": "..." } ] },
  "workouts":      { "coverage": { "complete": true }, "records": [ { "id": "healthkit_7C2D...", "workout_type": "walking", "segments": [ ... ], "...": "..." } ] },
  "daily_metrics": { "coverage": { "complete": false }, "records": [ { "date": "2026-10-04", "heart_rate_variability_ms": 34.52, "...": "..." } ] }
}
```

A full, real example is [examples/muse-v1-batch.json](examples/muse-v1-batch.json).

- **`generated_at`:** when you ran the query, with a UTC offset. A newer `generated_at` wins when the same record arrives twice with different values.
- **`timezone`:** an IANA name. Record times like `2026-10-04 05:18:52` are wall-clock times in the record's own `timezone` field, or in this one if a record has none. AGame converts them. A wall time that falls in a daylight-saving change is refused for that record, not guessed.
- **`coverage`:** pass each domain's coverage block through as you received it. `complete: false` tells AGame the day is still syncing: sleep shows "Sleep not synced yet" and that day's values are marked partial until your next send replaces them.
- **IDs:** keep every record's own `id` (`healthkit_<UUID>`). Daily metric rows carry no id; AGame identifies them by `date`.
- **Daily rows:** the date goes in `date` as `YYYY-MM-DD`. `record_count` is ignored.
- **Types:** send numbers as numbers or numeric strings and booleans as `true`/`false` or `"true"`/`"false"`. Leave out what you don't have. **Absent means missing, never 0.**
- **Workout segments:** put Apple's workout segments in the workout's `segments` list (the subfields as you receive them, with epoch seconds). 1 km segments become splits; any other segment becomes a lap.
- **Weather:** `weather_temperature_celsius` and `weather_humidity_percent` on a workout become the workout's weather.

Every value is checked against the [unit table](#unit-table). A value outside its range is rejected with a reason and never converted on a guess. If you see that happen, the unit you sent is not the one the table expects; tell me rather than rescaling it yourself.

## Reading the response

A normal morning returns `200`:

```json
{
  "status": "applied",
  "exit_code": 2,
  "rejected": [],
  "ignored_fields": ["heart_rate_min", "hr_average_bpm", "..."],
  "import": { "status": "applied", "added": { "sleep": 1, "metrics.hrv_sdnn_ms": 1, "...": 1 }, "updated": {}, "duplicates": [], "conflicts": [], "stale": [] },
  "build_report": { "status": "degraded", "exit_code": 2, "degraded_reasons": ["last night's sleep not synced yet"], "errors": [],
                    "next": "Built with partial data. Re-import when the phone has synced: last night's sleep not synced yet" },
  "morning_summary": {
    "contract": "agame.morning_summary.v2",
    "sleep_missing": true,
    "message": [
      "Last night's sleep hasn't synced from your phone yet, so there is no recovery score this morning.",
      "Keep the easy run gentle and conversational."
    ],
    "coach_line": "Keep the easy run gentle and conversational.",
    "suggestion": null,
    "plan": [ { "title": "Easy run", "type": "AER", "duration": "45m", "duration_s": 2700 } ],
    "...": "..."
  },
  "checkins": { "now": "...", "due": [], "schedule": [ { "type": "morning_report", "next_at": "2026-10-06T05:55:00+02:00", "...": "..." } ] }
}
```

| You see | It means | You do |
|---|---|---|
| `200`, `exit_code: 0` | Imported and built | Message me. Done until the next check-in |
| `200`, `exit_code: 2`, `sleep_missing: true` | Imported, last night's sleep not on the phone yet | Message me (the summary already says so). Retry at 08:00, then 13:00 |
| `200`, `exit_code: 2`, `rejected` not empty | The rest was imported; these records were left out | Read each `reason`. If you can fix it from your own data (a missing field, a wrong unit), re-send once. Otherwise tell me which records and why |
| `200` with `stale` entries | AGame already has a newer copy of those records | Nothing |
| `200` with `duplicates` | The same night or workout already exists from my Apple Health export | Nothing |
| `200` with `ignored_fields` | Fields AGame doesn't use | Nothing. Keep sending them untouched |
| `422` | Every record was rejected; nothing was written | Read `rejected` and `next`. Fix and re-send once |
| `400` | The envelope itself is wrong (no `timezone`, bad `generated_at`, unknown `format`) | Fix the envelope and re-send once |
| `500` | Imported, but the build failed; the app still shows the previous day | Tell me `build_report.next` word for word. Don't retry |

## What to tell me

Send me `morning_summary.message`: two or three short lines, as they are. They come from the same sentences the app shows, so you and the app never disagree.

- Don't add numbers, rankings or medical claims. Don't reword the advice into something stronger.
- If `suggestion` is set, the third line already tells me a change is waiting in the app. Don't accept it for me.
- If `sleep_missing` is true, the first line says so. After the 08:00 or 13:00 retry, send a one-line update only if the message changed.

## Logging through the day

When I tell you something, log it with one request. Every request needs:

- `Authorization: Bearer <token>`
- `Content-Type: application/json`
- `Idempotency-Key: <unique string>`, one per thing I told you (for example `coffee-2026-10-05T08:30`). If a request times out, send it again **with the same key**; AGame logs it once.

Times carry an offset. Use the time I mention, or now if I don't.

| I say | Request |
|---|---|
| "two coffees" | Two requests (two keys): `POST /api/entries/nutrition.caffeine` `{"t": "2026-10-05T08:30:00+02:00", "mg": 95}` |
| "500 ml of water" | `POST /api/entries/nutrition.water` `{"t": "...", "ml": 500}` |
| "chicken and rice for lunch" | `POST /api/entries/nutrition.meals` `{"t": "...", "meal": "lunch", "name": "Chicken and rice", "items": [{"name": "Chicken and rice", "qty": 1, "unit": "serving", "kcal": null, "protein_g": null, "carbs_g": null, "fat_g": null}]}` |
| "feeling flat, mood 2" | `POST /api/entries/journal.entries` `{"date": "2026-10-05", "type": "mood", "value": 2, "text": "feeling flat"}` (mood is 1 to 5) |
| "83.1 kg" | `POST /api/entries/body.measurements` `{"t": "...", "type": "weight_kg", "v": 83.1}` |
| "120 over 80" | Two requests: `type: "bp_systolic_mmhg", v: 120` and `type: "bp_diastolic_mmhg", v: 80`, same `t` |
| "slept badly, note it" | `POST /api/entries/journal.entries` `{"date": "...", "type": "note", "text": "slept badly"}` |
| "I'm sick" | `POST /api/entries/journal.activity_status` `{"status": "sick", "start": "2026-10-05", "end": null, "source": "user"}` |

When I don't say how much caffeine, use my usual: 95 mg for a coffee, 65 mg for an espresso. For food, only fill in calories or macros I give you or that a label states; otherwise leave them `null`. Don't estimate a meal.

A successful log returns `200` with the saved record: `{"ok": true, "record": {...}, "build": "ok"}`. A retry with a key AGame has already seen returns `{"ok": true, "duplicate": true, ...}` and changes nothing.

If I ask you to change something you logged, `PATCH /api/entries/<collection>/<id>` with only the changed fields. The id is in the record you got back: `id` for meals and journal entries, `source_id` for water, caffeine and body measurements.

Plan changes go through actions, only when I ask: `POST /api/actions/plan.adaptation` `{"session_id": "...", "rule": "...", "decision": "accepted"}` (both come from `morning_summary.suggestion`), `plan.skip` `{"session_id": "..."}`, `plan.move` `{"session_id": "...", "date": "YYYY-MM-DD"}`.

Every change you make is marked `source: agent` in my edit history, so I can see and undo it in the app.

## Check-ins and Mondays

- The import response includes `checkins.schedule`: each check-in's `type`, `message` and `next_at`. Plan your wake-ups from it; don't poll.
- When one is due, `GET /api/agent/checkins` returns it under `due` with the facts to include. Deliver its `message` plus the facts in plain words. With no `now` parameter it uses the current time and a 15 minute window (`?window_min=30` to widen it).
- **Mondays:** after the morning import, `GET /api/agent/weekly-review` and send me a short weekly review from it: the week's distance and time, sleep and recovery averages, goals that moved, and next week's plan. No raw number dumps; pick what matters.
- `GET /api/agent/morning-summary` and `GET /api/agent/build-report` return the latest files again if you lost the import response. You shouldn't normally need them.

## Errors

| Status | Meaning | You do |
|---|---|---|
| `401` | Token missing or wrong | Stop and tell me. Never try another token |
| `403` | Not something the agent may do (any delete, undo, settings) | Don't retry. Tell me what I asked for, so I can do it in the app |
| `400` | Bad request body; `error` says what | Fix it once. If it fails again, tell me |
| `404` | Unknown path or record | Check the path. Don't guess ids |
| `409` | An Apple Health export import is already running | Wait for it; try your import again in 10 minutes |
| `413` | Body too large | Send fewer days (the last 3 are enough) |
| `422` | Import: every record rejected | See [Reading the response](#reading-the-response) |
| `5xx` or timeout | Server problem | Retry once after a minute. The same batch or the same `Idempotency-Key` is safe to resend |

If anything fails twice, stop and tell me what failed and what you tried.

## Rules

1. **Never invent data.** Send only what Apple Health returned and log only what I told you. No estimates, no averages you computed, no filled gaps.
2. **Missing stays missing.** Leave a field out rather than sending 0.
3. **Never delete.** The token can't, and you shouldn't ask anyone to. Corrections are a `PATCH` or a note.
4. **Never send `kind: "user_entered"`** in an import. Those are things I log, and they go through `/api/entries`.
5. **Don't rescale units.** If a value is rejected for its range, tell me.
6. **No medical claims.** AGame shows fitness information only.
7. **Keep my data private.** Don't share it with any person or service, and don't paste the token anywhere.
8. **Don't use `POST /api/snapshot`.** That old whole-folder push overwrites edits I made in the app. It stays only for manual restores with a separate token.

## Reference

### Endpoints for the agent token

| Method | Path | Does |
|---|---|---|
| `POST` | `/api/import` | One batch (`muse.v1` or the AGame batch below), import, rebuild. Returns import result, build report, morning summary, check-ins |
| `GET` | `/api/agent/morning-summary` | Latest morning summary (`agame.morning_summary.v2`) |
| `GET` | `/api/agent/build-report` | Latest build report |
| `GET` | `/api/agent/weekly-review` | Last completed week |
| `GET` | `/api/agent/checkins?now=<ISO>&window_min=15` | Due check-ins with facts, plus the schedule |
| `POST` | `/api/entries/<collection>` | Log something I told you |
| `PATCH` | `/api/entries/<collection>/<id>` | Change something you logged |
| `POST` | `/api/actions/<name>` | Plan changes I asked for |
| `POST` | `/api/import/apple-health-export` | My full Apple Health export (`export.zip` as the raw body). Returns `202` with a job id |
| `GET` | `/api/agent/job?id=<job>` | Progress of that export import |

Collections you log into: `nutrition.meals`, `nutrition.water`, `nutrition.caffeine`, `journal.entries`, `journal.activity_status`, `body.measurements`, `load.annotations` (RPE and notes on a workout).

### Unit table

What `muse.v1` daily rows may contain, the unit AGame expects, the accepted range of the raw value, and how it is stored. Fields not listed are ignored and reported in `ignored_fields`. Rows marked *not observed yet* are mapped already, so they turn on as soon as you start sending them.

| Muse field | Unit Muse sends | Accepted range | Stored as |
|---|---|---|---|
| `heart_rate_variability_ms` | ms, daily average SDNN | 5 to 300 | `hrv_sdnn_ms`, shown as "HRV (daily average)" and used for the recovery baseline |
| `resting_hr_average_bpm` | bpm | 25 to 150 | `resting_hr_bpm` |
| `respiratory_rate_average` | breaths/min | 4 to 60 | `respiratory_rate_brpm` |
| `oxygen_saturation_average` | fraction 0 to 1 | 0.5 to 1 | `spo2_pct` (%, ×100) |
| `apple_sleeping_wrist_temperature_average` | °C, absolute | 30 to 42 | `wrist_temp_c`; the Temp tile compares it with my own recent nights |
| `vo2_max` | ml/kg/min | 10 to 95 | `vo2max_ml_kg_min` |
| `heart_rate_recovery_one_minute_average` | bpm | 1 to 120 | `hr_recovery_bpm` |
| `walking_heart_rate_average_average` | bpm | 40 to 200 | `walking_hr_bpm` |
| `step_count` | count | 0 to 150000 | `steps` |
| `active_energy_burned_kcal` | kcal | 0 to 15000 | `active_energy_kcal` |
| `basal_energy_burned_kcal` | kcal | 300 to 6000 | `resting_energy_kcal` |
| `distance_walking_running_meters` | m | 0 to 300000 | `distance_walk_run_m` |
| `apple_stand_time_sum` | min | 0 to 1440 | `stand_min` |
| `apple_exercise_time_sum` | min | 0 to 1440 | `exercise_min` |
| `running_ground_contact_time_average` | ms | 100 to 600 | `ground_contact_ms` |
| `running_stride_length_average` | m | 0.3 to 3 | `stride_length_m` |
| `running_vertical_oscillation_average` | m | 0.02 to 0.3 | `vertical_oscillation_cm` (cm, ×100) |
| `running_power_average` | W | 20 to 1000 | `running_power_w` |
| `walking_speed_average` | m/s | 0.1 to 3 | `walking_speed_mps` |
| `walking_asymmetry_percentage_average` | fraction 0 to 1 | 0 to 1 | `walking_asymmetry_pct` (%, ×100) |
| `walking_double_support_percentage_average` | fraction 0 to 1 | 0 to 1 | `walking_double_support_pct` (%, ×100) |
| `body_mass_average` | kg | 30 to 300 | weight (`weight_kg`) |
| `blood_pressure_systolic_average` *(not observed yet)* | mmHg | 60 to 260 | `bp_systolic_mmhg` |
| `blood_pressure_diastolic_average` *(not observed yet)* | mmHg | 30 to 160 | `bp_diastolic_mmhg` |
| `blood_glucose_average` *(not observed yet)* | mg/dL | 30 to 600 | `glucose_mg_dl` |
| `body_fat_percentage` *(not observed yet)* | fraction 0 to 1 | 0.03 to 0.7 | `body_fat_pct` (%, ×100) |
| `lean_body_mass_average` *(not observed yet)* | kg | 20 to 150 | `lean_mass_kg` |
| `waist_circumference_average` *(not observed yet)* | m | 0.4 to 2 | `waist_cm` (cm, ×100) |
| `bmi` *(not observed yet)* | kg/m² | 10 to 70 | `bmi` |
| `dietary_energy_sum` | kcal | 0 to 15000 | day total `kcal` |
| `dietary_protein_sum`, `dietary_carbs_sum`, `dietary_fat_sum`, `dietary_fiber_sum`, `dietary_sugar_sum` | g | 0 to 600, 1500, 600, 200, 1000 | day totals in g |
| `dietary_sodium_sum` | g | 0 to 30 | `sodium_mg` (mg, ×1000) |
| `dietary_water_sum` | mL | 0 to 20000 | `water_ml` |
| Other `dietary_*_sum` minerals and vitamins | g | small, per nutrient | stored in mg or µg |

Sleep sessions: `sleep_*_duration_sec` (seconds, 0 to 86400) become stage minutes; `sleep_efficiency` is a percent (1 to 100); `number_of_awakenings` 0 to 200. Workouts: `hr_average_bpm`/`hr_max_bpm` 25 to 250, `distance_meters`, `energy_burned_kcal`, `average_speed_mps`, `max_speed_mps`, `elevation_gain_meters`, `elevation_descended_meters`, `active_duration_sec`, `average_mets`, `step_count`, `flights_climbed`, `is_indoor`, and the two weather fields. A workout without heart-rate samples gets an estimated load from its average heart rate; zones, the heart-rate chart, best efforts and the map stay empty until my Apple Health export brings the samples in.

### The AGame batch (for other agents)

An agent that can produce AGame's own format can send it to the same endpoint instead of `muse.v1`. Schema: [schemas/healthkit_batch.schema.json](../schemas/healthkit_batch.schema.json). Example: [examples/healthkit-batch.json](examples/healthkit-batch.json). It takes sleep with either a stage timeline (`segments`) or stage totals (`stage_minutes`), workouts with or without `samples` (with source `splits`), daily metric points, body measurements and nutrition day totals.

### My Apple Health export

The first time, I import my full history from the Health app's export (Profile in AGame, "Import Apple Health export"). It brings in heart-rate samples, sleep stages and routes. Your daily summaries and the export never duplicate each other. If I ask you to upload it for me: `POST /api/import/apple-health-export` with the zip as the raw body (`Content-Type: application/zip`), then check `GET /api/agent/job?id=<job>` every few minutes until `status` is `done`, `rejected` or `failed`.
