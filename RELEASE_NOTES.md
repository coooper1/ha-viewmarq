# 0.5.2 — Automatic pregame countdown

Editable pregame pages count down from ESPN scheduled start times during the two hours before a selected game. The countdown includes seconds and ESPN broadcaster names, joins everyday rotation two hours before kickoff, and takes over fifteen minutes before kickoff in sports-only mode. Everyday pages return after the live game. Postponed/canceled events are excluded; a scheduled game awaiting ESPN live status shows Awaiting start for at most fifteen minutes. Priority alerts continue to override.

# 0.5.1 — Faster live sports updates

Live ESPN scoreboards and requested game statistics refresh every five seconds instead of thirty. Inactive leagues retain the two-minute interval, shared caching, bounded requests and error backoff. Visible sports pages update on the next display tick; other pages keep their configured rotation. ESPN publishing delays still apply.

# 0.5.0 — Compact weather, editable alerts and football possession

Single-screen weather combines time, Fahrenheit, conditions, rain, UV, heat index and feels-like. Weather warnings can alternate with the same weather screen. Weather and sensor alerts use editable page-builder layouts, including fields, colors, fonts and timing. Editor previews remain samples; physical tests are explicitly marked TEST, expire after 20 seconds and yield to actual priority alerts. Stop-test control restores normal operation immediately. Football possession layouts show scores, possession, down-and-distance and ball position, with selected-team possession green, opponent red and unknown amber.

# 0.4.1 — Weather sources per reading

Individual weather readings can use a different weather entity as well as sensor overrides, allowing NWS rain probability alongside UV from another provider.

# 0.4.0 — Autosave, detailed weather and alert controls

Valid edits autosave after a one-second pause, preserving newer edits during in-flight saves. Invalid layouts remain drafts with a visible error. Detailed weather shows Fahrenheit, conditions, hourly rain probability when supplied, UV level, heat index and feels-like. Derived temperatures are labeled estimates. NWS actual unexpired warnings override the display in red, watches/advisories rotate in amber, and unavailable sources are reported. Door/sensor message and placement controls are available directly in the editor.

# 0.3.6 — Individual field colors

Each field can inherit the page color or use green, amber or red. Preview and physical output support different colors on the same row. Mixed-color pages remain stationary and preserve colors above routine alerts.

# 0.3.5 — Share one row

Automatic-width, single-line fields on the same row now share left, center and right sections when their alignments differ. The second row stays available; long values continue on additional frames. Explicit widths and columns remain supported. Includes numeric sports samples.

# 0.3.4 — Numeric sports samples

Sample layouts now show representative first downs, passing and rushing yards, rebounds, assists, field goal percentages, and turnovers instead of generic sample text. These values remain editor-only; live games use actual feed data.

# 0.3.3 — Preview follows each edit

Update the layout preview while typing and adjusting settings. Automatically show the continuation screen containing the field being edited. Overlapping drafts render with a warning but cannot be saved; other invalid edits clear the stale preview and explain the problem.

# 0.3.2 — Following preview and live-game previews

- Preview follows the editor while scrolling, with controls bounded to the window height and compact behavior on narrow screens.
- Preview content selector separates actual live games for saved teams, current rotation, and clearly marked sample layouts. No-game states stay empty; no fabricated scores.
- Live preview refreshes automatically from the shared ESPN cache.

# 0.3.0 — Persistent page builder

- Add, delete, duplicate, reorder and enable per-display pages with field grids, fonts, colors, durations, motion and visibility conditions.
- Clock/date, weather, text, live sports, entities, read-only Now Playing, active alerts, external status and custom templates.
- Shared renderer for preview and real sign; explicit editor-only sample previews.
- Actual ESPN game fields, on-demand bounded summary cache and configurable live-game rotation policy.
- Stable page identity prevents clock/score updates from resetting dwell. Routine alerts keep normal content rotating; hazards retain priority.
- Existing options migrate into persistent pages while preserving teams, sensors and display identities.
- Backend tests cover persistence, migration, rendering, timing, alert recovery, unavailable stats and media visibility; browser checks exercise page CRUD and preview.
