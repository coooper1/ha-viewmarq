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
from .content import pages, active_alerts, paginate
from .espn import FAVORITES, LEAGUES, team_choices
from .protocol import FONTS, layout, page_message
from .status_feed import status_pages


def validated(changes, model):
    enums = {"font": list(FONTS), "alignment": ["left", "center", "right"],
             "color": ["green", "red", "amber"], "alert_color": ["green", "red", "amber"], "sports_color": ["amber", "green", "red"],
             "scroll": ["static", "left"], "speed": ["slow", "medium", "fast"],
             "time_format": ["12-hour", "24-hour"],
             "date_style": ["weekday-year", "full-date", "date-only", "iso-date", "weekday-date", "time-only"]}
    output = {}
    for key, value in changes.items():
        if key in enums:
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
    return output


def describe(hub):
    colors = hub.last[1] if hub.last else hub.settings["color"]
    return {"id": hub.entry.entry_id, "name": hub.entry.title, "model": hub.entry.data["model"],
            "host": hub.entry.data["host"], "settings": {k: v for k, v in hub.settings.items() if k in DEFAULTS},
            "geometry": hub.geometry, "displayed_text": hub.displayed, "colors": colors,
            "status": hub.status, "failures": hub.failures, "sports": hub.sports_status}


@websocket_api.websocket_command({"type": "viewmarq/panel", vol.Required("action"): vol.In(["read", "preview", "save", "teams"]), vol.Optional("entry_id"): str, vol.Optional("settings", default={}): dict, vol.Optional("league"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def handle(hass, connection, msg):
    try:
        hubs = hass.data.get(DOMAIN, {})
        if msg["action"] == "read":
            result = {"displays": [describe(h) for h in hubs.values()], "favorites": FAVORITES,
                      "leagues": [{"value": k, "label": v[0]} for k, v in LEAGUES.items()]}
        elif msg["action"] == "teams":
            if msg.get("league") not in LEAGUES:
                raise ValueError("Choose a league")
            result = await team_choices(hass, msg["league"])
        else:
            hub = hubs.get(msg.get("entry_id"))
            if hub is None:
                raise ValueError("Display is reloading or no longer configured. Try again.")
            changes = validated(msg["settings"], hub.entry.data["model"])
            settings = {**hub.settings, **changes}
            geometry = layout(hub.entry.data["model"], settings["font"])
            settings.update({k: geometry[k] for k in ("rows", "columns")})
            ordinary, alerts = pages(settings, hass.states.get, dt_util.now())
            scores, status = hub.espn.pages(settings)
            ordinary.extend(scores)
            ordinary.extend(status_pages(hass, hub.entry.entry_id, settings))
            previews = [{"text": text, "color": color, "kind": "Normal page"} for text, color in ordinary]
            active_items = active_alerts(settings, hass.states.get)
            urgent = [(text, settings["alert_color"]) for text, mode, _ in active_items if mode == "full-page"]
            if urgent:
                previews = [{"text": text, "color": color, "kind": "Priority alert"} for text, color in paginate(urgent, settings["rows"], settings["columns"])]
            elif alerts and settings["rows"] >= 2:
                split = {**settings, "rows": 1}
                top, bottom = pages(split, hass.states.get, dt_util.now())
                top_scores, _ = hub.espn.pages(split)
                top.extend(top_scores)
                top.extend(status_pages(hass, hub.entry.entry_id, split))
                top = top or [(" ", settings["color"])]
                previews = []
                for index in range(max(len(top), len(bottom))):
                    a, b = top[index % len(top)], bottom[index % len(bottom)]
                    count = settings["rows"] - 2
                    previews.append({"text": a[0] + "\n" * (count + 1) + b[0], "color": [a[1]] + [settings["color"]] * count + [b[1]], "kind": "Normal + routine alert"})
            elif alerts:
                previews.extend({"text": text, "color": color, "kind": "Routine alert"} for text, color in alerts)
            if not settings["enabled"]:
                previews = [{"text": " ", "color": settings["color"], "kind": "Display disabled"}]
            for item in previews:
                page_message(item["text"], hub.entry.data["display_id"], hub.entry.data["model"], item["color"], settings["font"], settings["alignment"])
            if msg["action"] == "save":
                hass.config_entries.async_update_entry(hub.entry, options={**hub.entry.options, **changes})
            result = {"pages": previews, "geometry": geometry, "sports": status, "saved": msg["action"] == "save"}
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
    await panel_custom.async_register_panel(hass, "viewmarq", "viewmarq-panel", sidebar_title="ViewMarq", sidebar_icon="mdi:sign-text", module_url="/viewmarq-assets/panel.js?v=0.2.1", require_admin=True)
    hass.data[f"{DOMAIN}_panel"] = True
