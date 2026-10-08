# 0.3.1 — Preview follows scrolling

Fix the preview scroll container so layout and live previews stay visible while editing long pages. Keep preview controls within the viewport, including a compact sticky preview on narrow screens. Frontend-only behavior change; refresh the ViewMarq editor after updating.

# 0.3.0 — Persistent page builder

- Add, delete, duplicate, reorder and enable per-display pages with field grids, fonts, colors, durations, motion and visibility conditions.
- Clock/date, weather, text, live sports, entities, read-only Now Playing, active alerts, external status and custom templates.
- Shared renderer for preview and real sign; explicit editor-only sample previews.
- Actual ESPN game fields, on-demand bounded summary cache and configurable live-game rotation policy.
- Stable page identity prevents clock/score updates from resetting dwell. Routine alerts keep normal content rotating; hazards retain priority.
- Existing options migrate into persistent pages while preserving teams, sensors and display identities.
- Backend tests cover persistence, migration, rendering, timing, alert recovery, unavailable stats and media visibility; browser checks exercise page CRUD and preview.
