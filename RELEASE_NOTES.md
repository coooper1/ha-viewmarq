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
