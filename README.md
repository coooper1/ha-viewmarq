# ViewMarq for Home Assistant

Control AutomationDirect ViewMarq LED signs over local Modbus TCP. Each display has independent settings and a live acknowledged-content view. Version 0.3.0 adds a persistent visual page builder, configurable live-game layouts and read-only Now Playing pages.

## Everyday use

Open **ViewMarq** in the HA sidebar and choose a sign. Add pages, edit their fields, arrange their order, select alert sensors and sports teams, then **Save to display**. Settings apply through an integration reload; they do not restart HA.

- Add, delete, duplicate, reorder or disable pages independently per display. Templates cover text, clock/date, weather, live sports, HA entities, Now Playing, external status, active alerts and custom layouts. There is no fixed preset page count; collections are bounded to 1,000 pages / 512 KiB for runtime safety.
- Each page supports its own font/size, color, duration, motion, field alignment and visibility condition. Position fields by row/column with explicit width/height; overlapping fields are rejected. Logical rows and long text continue across frames. Optional labels and HA scalar attributes allow custom layouts without code.
- Now Playing reads a chosen HA media player’s actual title, artist, album, source, app, station and playback state. Idle/off and paused visibility are configurable; unavailable players are hidden. It never controls playback or fabricates missing metadata.
- Sports pages select all or particular saved teams and expose team/opponent/home/away names and scores, game clock/status, football down/position/yardage and available basketball game statistics. Missing fields remain blank. Game summaries are fetched only when requested by configured stat fields, with a shared bounded cache; season averages are never substituted for game totals.
- Choose interleaving, sports-only during games, or hiding clock pages during games. Urgent alerts still override; ordinary pages resume afterward.
- Existing settings migrate once into saved pages without losing teams, alert selections or entry identity. An intentionally empty page list stays empty. The quick-message entity continues to manage its own page.
- Stationary pages default to five seconds. Long messages wrap into additional pages instead of silently losing text.
- Choose 12-hour AM/PM or 24-hour time and date presets with the year. Dates use HA's timezone.
- Weather pairs temperature and condition. The degree symbol maps to the manufacturer's documented ASCII back-apostrophe glyph.
- Select binary sensors for automatic alerts. Names and device classes determine wording and active state: door/window/opening `on` means open; battery `on` means low; connectivity `off` means disconnected. Unknown/unavailable never triggers an alert.
- Routine alerts use the bottom row while normal information continues above. With one available text row, routine alerts join normal page rotation. Smoke, gas, CO, unsafe and wet sensors default to full-page priority until cleared. Optional integration settings override each sensor's wording/presentation. No hazardous sensor is selected automatically.
- Sports come directly from ESPN. Choose Oklahoma Sooners, Dallas Cowboys, or teams from supported leagues. Only in-progress games with valid scores appear. No-game and stale data are hidden. Polling is shared across signs, bounded and backed off on failure; upstream availability and latency apply.
- Information is green, alerts are red and sports are amber by default, independently configurable.
- Configure supported font sizes, alignment, colors, duration and optional left scrolling. Mixed normal/alert rows remain stationary.

The draft preview uses the production text formatter, geometry, wrapping and colors. Its browser typeface is approximate, not a pixel-perfect copy of the device font. The separate live view shows the last command acknowledged by the real sign, not a camera image. Drafts never write to the sign until saved. The **Preview content** selector separates current rotation, actual live games for saved teams, and sample layouts. The **Sample of selected page** mode uses marked editor-only example data to design inactive sports/media layouts; those samples never enter the hardware queue.

## HACS and installation

Repository: [coooper1/ha-viewmarq](https://github.com/coooper1/ha-viewmarq). The package contains one integration, its frontend and local brand icon.

Add its URL in **HACS → Custom repositories**, category **Integration**, download ViewMarq and restart HA once. Then **Settings → Devices & services → Add integration → ViewMarq**. Name the sign and enter its address. Setup reads its identity and register settings before enabling it. Repeat for each display.

Manual installation: copy the complete `custom_components/viewmarq` directory into HA's `config/custom_components/`, restart once, and add the integration. HACS can later manage the same domain without recreating existing display entries. Back up the directory before code updates. Do not use the old shell-command example and the native integration as competing writers.

HA 2026.10 is the verified runtime. Local brand images require HA 2026.3+. Python code updates may require a core restart; routine control changes do not.

## Hardware and transport

Physically verified on an MD4-0224: 144 × 16 pixels, two rows. Documented MD4 1/2/4-row and 12/24-character profiles are recognized; the other profiles have not all been physically tested. Unsupported identities are rejected instead of guessed. Fonts are constrained by pixel height. Adding a supported sign needs configuration, not programming.

TCP port 502 is the default. The transport validates Modbus framing, reads model identity and byte order, waits for command-buffer clearance, uses carriage-return termination and at least 100 ms handoff intervals, and requires the exact `OK` reply. Per-sign writes are serialized; global I/O is capped at four operations. Startup jitter and individual backoff isolate unreachable signs. Twenty physical signs have not been load-tested.

## Optional external status pages

The authenticated HA action **ViewMarq: Publish a temporary status page** (`viewmarq.publish_status`) accepts a display config-entry ID, source name, message and expiry of 10–900 seconds. Refresh a source to replace its page; use an empty message to clear it. Expired pages disappear automatically. Feeds are in memory and clear on restart.

This accepts measured Codex allowance/reset information and actual task state from a separately authenticated host bridge. It does not scrape credentials, fetch every ChatGPT quota, invent completion percentages or estimate a finish time. The host bridge is not connected by this package. One-time snapshots must expire rather than masquerade as live feeds.

## Verification and references

The real sign accepted clock/weather and front-door alert commands; normal pages resumed when the actual door closed. Protocol checks cover frames, byte order and error handling. Layout checks cover the single-write payload limit across supported profiles. Browser typefaces and untested physical models remain limitations.

- [Ethernet manual](https://cdn.automationdirect.com/static/manuals/mduserm/ch6.pdf)
- [Modbus handoff](https://cdn.automationdirect.com/static/manuals/mduserm/ch7.pdf)
- [ASCII commands](https://cdn.automationdirect.com/static/manuals/mduserm/appxa.pdf)
- [Registers and identity](https://cdn.automationdirect.com/static/manuals/mduserm/appxb.pdf)
- [Configuration software and degree glyph](https://cdn.automationdirect.com/static/manuals/mduserm/ch5.pdf)
- [HA binary sensor meanings](https://www.home-assistant.io/integrations/binary_sensor/)
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/)
- [Local brand images](https://developers.home-assistant.io/docs/core/integration/brand_images/)
- [Codex app-server](https://learn.chatgpt.com/docs/app-server)

The icon is the vendor application's supplied ViewMarq icon, used to identify the associated hardware. This is an independent integration, not an AutomationDirect product. ViewMarq and ESPN names belong to their owners. Reusable source contains no personal sign address, selected entities or credentials.


## Weather and autosave

Valid editor changes save after a one-second pause; wait for **All changes saved** before closing. Invalid layouts remain drafts. Use **Weather and weather alerts** for the detailed layout and NWS source, and **Door and sensor alerts** to customize selected sensors. NWS tests/cancellations/expired records do not generate live warnings. No synthetic warnings are sent for testing.

Rain chance is the next hourly forecast probability, never inferred from rainfall amount. Missing readings remain unavailable. Heat index and feels-like prefer provider values or sensor overrides; fallback estimates are marked `est.` and use the NWS heat-index/wind-chill formulas within their supported conditions. They are supplemental display information. Source coverage and availability depend on the selected HA integrations.

References: [HA forecast response fields](https://www.home-assistant.io/actions/weather.get_forecasts/), [NWS heat index](https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml), [NWS wind chill](https://www.weather.gov/safety/cold-wind-chill-chart), [NWS Alerts integration](https://github.com/finity69x2/nws_alerts).


## Compact weather, alert layouts and football

Use the compact weather preset for one screen containing time and all weather readings. R is rain chance, H is heat index, F is feels-like, and an asterisk marks an estimate; temperature values are Fahrenheit. Weather warnings can alternate with the same weather screen. Edit weather/sensor alert layouts through the page builder; their fields, colors, fonts and durations apply when an actual alert is active. Routine alerts use their selected placement; incompatible fonts use full-page rotation. Disabled or missing custom alert layouts use the built-in layout.

Preview buttons show editor-only samples. Test-on-sign buttons show explicitly labeled TEST frames for 20 seconds without changing NWS/sensor states. Tests yield to actual priority alerts and can be stopped immediately.

The football possession preset uses actual live feed possession, down-and-distance and yard line. Green means the selected team has possession, even when it is the visiting team; red means its opponent; amber means possession is not supplied. Automatic possession color is available per field.
