# AGame design rules

These are the rules I've settled on for how AGame looks and behaves. They come from iterating on the dashboard screen by screen. It is not pixel perfect yet and I'm still iterating, so treat this as the floor: never go backwards on anything here. If a change you're about to make breaks one of these rules, stop and ask me first.

## What AGame should feel like

AGame is an app, not a report. It shows the state of my body and my training, and it tells me what to do today. It doesn't narrate.

Bevel is the reference for layout, spacing, cards and tone. Strava is the reference for activity analysis, maps, the training log and records. Before you design or redesign a screen, look at the matching Bevel or Strava screens on Mobbin (the Mobbin MCP) and build it that way. Don't invent a layout from memory.

## Things I don't want, ever

- **Pills everywhere.** A status is coloured text with a small dot, not a filled capsule. Hide a status that says nothing ("In progress", "Active").
- **Eyebrow text.** No small uppercase labels above titles ("LONG RUN" above "Long run", "EVENING BEFORE").
- **Explanation sentences on the screen.** How a number is calculated, what a band means, "Edits need connection", "Built only from your data": none of it goes on the page. If it's worth keeping, it goes behind the (i) button on that card, and it opens in a sheet.
- **The same idea twice.** Today once showed "go easier" four times: a badge, a brief, an action card and a suggestion. Say it once, in the place it belongs.
- **Floating or misaligned buttons.** Buttons sit inside their card, in an aligned row, never hanging between cards.
- **Dense, crammed layouts.** If a phone screen feels crowded, it is. Give things room, and cut before you shrink.
- **Hand-drawn SVG icons, emoji or text glyphs as icons.** No ★ ☆ ↑ ↓ × ‹ › ▲ ▼ ● standing in for icons. They render badly and look cheap.
- **Placeholder branding.** No orange square for a logo. The share image uses the real logo.
- **A sample-data banner** or any other banner that isn't telling me something I need right now.
- **Text where an icon will do.** The freshness indicator is one icon, not "Updated 05:42" in a pill. The time lives in the sheet behind it.
- **Dead ends.** Every page you can reach by a link and not by the main navigation (Weekly review, Year in Sport, Timeline, an activity, a route) has a back button.
- **Em dashes** in any copy.
- **Fake or invented data on screen.** Missing is "—" with a reason, never zero. Estimates say so.

## Layout

- **Section titles go outside the cards.** On Today: "Today's plan", "Stress & energy", "Cardio load", "Health monitor", "Goals", "Timeline", "Yesterday". Each title is 20px semibold, with one link on the right at most ("Week", "All").
- **One header pattern for every card:** title on the left, at most one control on the right (a segmented range, an Add button, a status), then the (i) button if there's an explanation. Use `cardHead()`; don't hand-roll headers.
- **Small metric cards follow Bevel's tile:** small icon and grey label at the top, one big value with its unit, a coloured status line under it, and a sparkline at the bottom. The whole tile links to its detail page.
- **One number per idea.** Each card leads with one big number. Don't show the same number twice on a screen.
- **Desktop uses a clear two-column grid**, a main column and a side column. Balance the columns; don't leave one twice as long as the other.
- **The phone is first.** Check every change at 390×797 before you call it done. Nothing may scroll sideways except a row of chips or tabs.

## Navigation

- **Sub-pages within a screen** (Training's Fitness, Plan, Log, and so on) are scrollable pills. The selected pill is filled white, so it's always obvious where I am. Keep the count low; Training has six.
- **Anything that isn't a peer of the other tabs is its own page** with a back button. Weekly review and Year in Sport are pages, not tabs.
- **Ranges** (1M, 3M, W, M…) are a compact segmented control in the card header, not a row of loose chips.

## Today

- **The hero card** is the three rings (Strain, Recovery, Sleep) with a coaching note under them in the same card. The note says what to do and why, in one or two plain sentences built from the real factors, for example "Short sleep and sleep debt are holding your recovery back. Keep the long run easy and conversational." Tapping it opens the full factors.
- **Suggestions sit inside today's plan,** next to the session they change, with Accept and Keep original in the same row.
- **Stress** shows highest, lowest and average in colour, separated by thin dividers. The energy bank is a bar on its own.
- **The timeline preview** shows three events with icons and a View timeline button. The full timeline is a real timeline: a vertical line, times on the left, a coloured dot per event, and a card per event.

## Training on the phone

- **The plan week** on a phone is a week strip (day pills with a status icon) and a list of the week's sessions, not a seven-column grid of tiny tiles. The desktop can keep the grid.
- **Week totals** are plain progress rows ("5 of 6", "4h 31m of 6h 20m"), not a table of coloured numbers.

## Icons and brand

- **Icons:** only Tabler Icons, inlined in `ICONS` in `core.js` and drawn with `icon()`. To add one, take it from the Tabler set; never draw your own. Sports use the real figures (run, bike, swimming, walk, barbell).
- **The logo** is the A: a peak with a heartbeat line through it, on an orange tile. The word next to it is "Game", so the whole thing reads "A Game". The same geometry is used in the sidebar (`logo()` in `app.js`), the favicon, the PWA icons (`pwa.py`) and the share card. Change it in all of them or none.
- **The muscle map** uses the anatomical polygons from react-body-highlighter (MIT). Don't go back to hand-drawn body shapes.

## Copy

- **Plain, short, sentence case.** "As planned", not "As Planned".
- **No jargon on the surface.** "Ease off" or "Room to build", not "TSB below threshold".
- **Coaching lines** say what to do and why. Never paste raw metrics into a sentence.
- **Units on every number,** including deltas ("+22m vs yesterday", not "+22").

## Colour and type

- **Dark mode is the main theme.** The surfaces are Bevel-like grey-blue (`--bg`, `--surface`, `--surface-2` in `app.css`), the cards have 20px corners and soft borders, and orange is the accent.
- **Status colours:** green good, amber watch, red bad, blue informational. Always pair colour with text or an icon.
- **Light mode has to work too.** `scripts/tests/test_scripts.py` checks text and status contrast in both themes, so keep it passing.

## Phone details I've already been burned by

- Keep the iPhone status bar style `black`, never `black-translucent`. Translucent makes iOS 26 home-screen apps 47px short.
- No focus outline around the whole page when it renders.
- Hidden screen-reader tables can't widen the page.
- Card headers wrap on narrow screens instead of squeezing the title to nothing.
- Chart axis labels use "10k", not clipped "0,000".

## Before you say a design change is done

1. Build and look at every screen you touched at 390×797 and on desktop, in dark and light. Look at the screenshots yourself.
2. Run the browser tests (`scripts/e2e/e2e.js` and `scripts/e2e/edit_flows.js`) and the unit tests (`scripts/run_tests.py`).
3. Check nothing in this file got worse.
