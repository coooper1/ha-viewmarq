"""Authenticated display editor and previews using the production formatter."""
from pathlib import Path
import asyncio
try:
    import probatio as vol
except ImportError:
    import voluptuous as vol
from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN
from .builder import effective_pages, validate_pages, new_page, sample_frames, live_game_preview, PAGE_TYPES, FIELDS
from .espn import FAVORITES, LEAGUES, team_choices
from .protocol import FONTS, layout


def validated(changes, model, current, preview=False):
    enums = {"font": list(FONTS), "alignment": ["left", "center", "right"],
             "color": ["green", "red", "amber"], "alert_color": ["green", "red", "amber"], "sports_color": ["amber", "green", "red"],
             "scroll": ["static", "left"], "speed": ["slow", "medium", "fast"],
             "time_format": ["12-hour", "24-hour"], "sports_mode": ["interleave", "only", "hide_clock"],
             "date_style": ["weekday-year", "full-date", "date-only", "iso-date", "weekday-date", "time-only"]}
    output = {}
    for key, value in changes.items():
        if key == "pages":
            value = validate_pages(value, {**current, **changes}, model, allow_overlap=preview)
        elif key in enums:
            if value not in enums[key]:
                raise ValueError(f"Invalid {key}")
        elif key in ("enabled", "show_clock"):
            if type(value) is not bool:
                raise ValueError(f"Invalid {key}")
        elif key in ("quick_message", "messages", "weather_entity"):
            if not isinstance(value, str) or len(value) > (10000 if key == "messages" else 190):
                raise ValueError(f"Invalid {key}")
            if key == "weather_entity" and value and not value.startswith("weather."):
                raise ValueError("Choose a weather entity")
        elif key in ("dwell", "sports_max_age"):
            if type(value) is not int or not 1 <= value <= (300 if key == "dwell" else 15):
                raise ValueError(f"Invalid {key}")
            if key == "dwell" and value < 3:
                raise ValueError("Page duration must be at least 3 seconds")
        elif key == "binary_sensors":
            if not isinstance(value, list) or len(value) > 200 or any(not isinstance(x, str) or not x.startswith("binary_sensor.") for x in value):
                raise ValueError("Choose binary sensors")
            value = list(dict.fromkeys(value))
        elif key == "teams":
            if not isinstance(value, list) or len(value) > 100:
                raise ValueError("Too many teams")
            for team in value:
                if not isinstance(team, dict) or team.get("league") not in LEAGUES or not str(team.get("id", "")).isdigit() or not isinstance(team.get("name"), str):
                    raise ValueError("Invalid team")
            value = [{"league": t["league"], "id": str(t["id"]), "name": t["name"][:100]} for t in value]
        else:
            raise ValueError(f"Unsupported setting: {key}")
        output[key] = value
    if "font" in output:
        layout(model, output["font"])
    merged = {**current, **output}
    validate_pages(effective_pages(merged), merged, model, allow_overlap=preview)
    return output


def describe(hub):
    colors = hub.last.color if hub.last else hub.settings["color"]
    return {"id": hub.entry.entry_id, "name": hub.entry.title, "model": hub.entry.data["model"],
            "host": hub.entry.data["host"], "settings": {k: v for k, v in hub.settings.items() if k in DEFAULTS},
            "geometry": layout(hub.entry.data["model"], hub.last.font) if hub.last else hub.geometry, "displayed_text": hub.displayed, "colors": colors, "alignment": hub.last.alignment if hub.last else "left", "pages": effective_pages(hub.settings),
            "templates": {kind: new_page(kind, "new", hub.settings) for kind in PAGE_TYPES},
            "status": hub.status, "failures": hub.failures, "sports": hub.sports_status}


@websocket_api.websocket_command({"type": "viewmarq/panel", vol.Required("action"): vol.In(["read", "preview", "save", "teams"]), vol.Optional("entry_id"): str, vol.Optional("settings", default={}): dict, vol.Optional("league"): str, vol.Optional("sample_page"): str, vol.Optional("preview_mode"): vol.In(["rotation", "games", "sample"])})
@websocket_api.require_admin
@websocket_api.async_response
async def handle(hass, connection, msg):
    try:
        hubs = hass.data.get(DOMAIN, {})
        if msg["action"] == "read":
            result = {"displays": [describe(h) for h in hubs.values()], "favorites": FAVORITES,
                      "leagues": [{"value": k, "label": v[0]} for k, v in LEAGUES.items()], "page_types": PAGE_TYPES, "fields": FIELDS}
        elif msg["action"] == "teams":
            if msg.get("league") not in LEAGUES:
                raise ValueError("Choose a league")
            result = await team_choices(hass, msg["league"])
        else:
            hub = hubs.get(msg.get("entry_id"))
            if hub is None:
                raise ValueError("Display is reloading or no longer configured. Try again.")
            changes = validated(msg["settings"], hub.entry.data["model"], hub.settings, preview=msg["action"] == "preview")
            settings = {**hub.settings, **changes}
            geometry = layout(hub.entry.data["model"], settings["font"])
            settings.update({k: geometry[k] for k in ("rows", "columns")})
            warning = ""
            if msg["action"] == "preview":
                try:
                    validate_pages(effective_pages(settings), settings, hub.entry.data["model"])
                except ValueError as error:
                    warning = str(error)
            frames, status = hub.frames(settings)
            if msg["action"] == "preview" and msg.get("preview_mode") == "games":
                games, status = hub.espn.games(settings)
                frames = live_game_preview(settings, hub.entry.data["model"], hass.states.get, dt_util.now(), games)
            elif msg["action"] == "preview" and msg.get("sample_page"):
                page = next((p for p in effective_pages(settings) if p["id"] == msg["sample_page"]), None)
                if page:
                    frames = sample_frames(page, settings, hub.entry.data["model"], hass.states.get, dt_util.now())
            previews = [frame.as_dict(hub.entry.data["model"]) for frame in frames]
            if msg["action"] == "save":
                hass.config_entries.async_update_entry(hub.entry, options={**hub.entry.options, **changes})
            result = {"pages": previews, "geometry": geometry, "sports": status, "saved": msg["action"] == "save", "warning": warning, "empty_message": "No live game data for saved teams" if msg.get("preview_mode") == "games" else "Blank"}
        connection.send_result(msg["id"], result)
    except Exception as error:
        connection.send_error(msg["id"], "viewmarq_error", str(error))


async def register(hass):
    lock = hass.data.setdefault(f"{DOMAIN}_panel_lock", asyncio.Lock())
    async with lock:
        await _register(hass)


async def _register(hass):
    if hass.data.get(f"{DOMAIN}_panel"):
        return
    await hass.http.async_register_static_paths([StaticPathConfig("/viewmarq-assets", str(Path(__file__).parent / "frontend"), False)])
    websocket_api.async_register_command(hass, handle)
    await panel_custom.async_register_panel(hass, "viewmarq", "viewmarq-panel", sidebar_title="ViewMarq", sidebar_icon="mdi:sign-text", module_url="/viewmarq-assets/panel.js?v=0.3.6", require_admin=True)
    hass.data[f"{DOMAIN}_panel"] = True
