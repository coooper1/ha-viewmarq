"""UI setup, content selection, and alert rules."""
import math
import socket
import asyncio
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from .const import DEFAULTS, DOMAIN
from .protocol import Modbus, ProtocolError, inspect, dimensions, FONTS, layout
from .espn import LEAGUES, FAVORITES, team_choices


def identify(config):
    found = []
    for base in (400001, 400000):
        try:
            with socket.create_connection((config["host"], config["port"]), timeout=2) as sock:
                found.append(inspect(Modbus(sock, config["unit_id"]), base))
        except (OSError, ProtocolError):
            continue
    if len(found) != 1:
        raise ProtocolError("Could not identify one unambiguous ViewMarq register mapping")
    info = found[0]
    dimensions(info["model"])
    return {**config, "model": info["model"], "register_base": info["register_base"],
            "display_id": info["display_id"], "byte_order": info["model_byte_order"],
            "heartbeat_seconds": info["heartbeat_seconds"]}


def connection_schema(defaults=None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required("name", default=defaults.get("name", "ViewMarq")): str,
        vol.Required("host", default=defaults.get("host", "")): str,
        vol.Required("port", default=defaults.get("port", 502)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Required("unit_id", default=defaults.get("unit_id", 1)): vol.All(vol.Coerce(int), vol.Range(min=0, max=255)),
    })


class ViewMarqConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = {**user_input, "host": user_input["host"].strip().lower(), "name": user_input["name"].strip() or "ViewMarq"}
            try:
                data = await self.hass.async_add_executor_job(identify, user_input)
            except (OSError, ProtocolError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{data['host']}:{data['port']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data["name"], data=data)
        return self.async_show_form(step_id="user", data_schema=connection_schema(user_input), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ViewMarqOptionsFlow()


def choices(values):
    return selector.SelectSelector(selector.SelectSelectorConfig(options=values, mode=selector.SelectSelectorMode.DROPDOWN))


class ViewMarqOptionsFlow(config_entries.OptionsFlow):
    @property
    def settings(self):
        return {**DEFAULTS, **self.config_entry.options}

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["content", "binary_alerts", "sports", "add_team", "sensor_override", "appearance", "add_alert", "remove_alert"])

    async def async_step_sports(self, user_input=None):
        catalog = {f"{t['league']}:{t['id']}": t for t in [*FAVORITES, *self.settings["teams"]]}
        if user_input is not None:
            selected = [catalog[key] for key in user_input.get("teams", [])]
            return self.async_create_entry(title="", data={**self.config_entry.options, "teams": selected, "sports_max_age": user_input["sports_max_age"]})
        return self.async_show_form(step_id="sports", data_schema=vol.Schema({
            vol.Optional("teams", default=[f"{t['league']}:{t['id']}" for t in self.settings["teams"]]): selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value": key, "label": f"{t['name']} ({t['league']})"} for key, t in catalog.items()], multiple=True)),
            vol.Required("sports_max_age", default=self.settings["sports_max_age"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=15)),
        }))

    async def async_step_add_team(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.team_league = user_input["league"]
            try:
                self.team_catalog = await team_choices(self.hass, self.team_league)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
                errors["base"] = "sports_unavailable"
            else:
                return await self.async_step_choose_team()
        return self.async_show_form(step_id="add_team", data_schema=vol.Schema({
            vol.Required("league", default="NFL"): choices([{"value": key, "label": value[0]} for key, value in LEAGUES.items()]),
        }), errors=errors)

    async def async_step_choose_team(self, user_input=None):
        if user_input is not None:
            names = {t["value"]: t["label"] for t in self.team_catalog}
            teams = {f"{t['league']}:{t['id']}": t for t in self.settings["teams"]}
            for team_id in user_input["teams"]:
                teams[f"{self.team_league}:{team_id}"] = {"league": self.team_league, "id": team_id, "name": names[team_id]}
            return self.async_create_entry(title="", data={**self.config_entry.options, "teams": list(teams.values())})
        return self.async_show_form(step_id="choose_team", data_schema=vol.Schema({
            vol.Required("teams"): selector.SelectSelector(selector.SelectSelectorConfig(options=self.team_catalog, multiple=True)),
        }))

    async def async_step_binary_alerts(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, "binary_sensors": user_input.get("binary_sensors", [])})
        return self.async_show_form(step_id="binary_alerts", data_schema=vol.Schema({
            vol.Optional("binary_sensors", default=self.settings["binary_sensors"]): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor", multiple=True)),
        }))

    async def async_step_sensor_override(self, user_input=None):
        if not self.settings["binary_sensors"]:
            return self.async_abort(reason="no_sensors")
        if user_input is not None:
            self.override_entity = user_input["entity"]
            return await self.async_step_sensor_details()
        return self.async_show_form(step_id="sensor_override", data_schema=vol.Schema({
            vol.Required("entity"): selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor", include_entities=self.settings["binary_sensors"])),
        }))

    async def async_step_sensor_details(self, user_input=None):
        if user_input is not None:
            overrides = {**self.settings["sensor_overrides"], self.override_entity: user_input}
            return self.async_create_entry(title="", data={**self.config_entry.options, "sensor_overrides": overrides})
        current = self.settings["sensor_overrides"].get(self.override_entity, {})
        return self.async_show_form(step_id="sensor_details", data_schema=vol.Schema({
            vol.Required("presentation", default=current.get("presentation", "automatic")): choices(["automatic", "bottom-row", "full-page"]),
            vol.Optional("message", default=current.get("message", "")): vol.All(str, vol.Length(max=190)),
        }))

    async def async_step_content(self, user_input=None):
        s = self.settings
        errors = {}
        if user_input is not None:
            if len(user_input.get("messages", "")) > 10000:
                errors["base"] = "too_long"
            else:
                data = {**self.config_entry.options, **user_input}
                data["weather_entity"] = user_input.get("weather_entity", "")
                return self.async_create_entry(title="", data=data)
        fields = {
            vol.Optional("messages", default=s["messages"]): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            vol.Required("show_clock", default=s["show_clock"]): bool,
            vol.Required("time_format", default=s["time_format"]): choices(["12-hour", "24-hour"]),
            vol.Required("date_style", default=s["date_style"]): choices([
                {"value": "weekday-year", "label": "Thu 10/08/2026"},
                {"value": "full-date", "label": "Oct 08, 2026"},
                {"value": "date-only", "label": "10/08/2026"},
                {"value": "iso-date", "label": "2026-10-08"},
                {"value": "weekday-date", "label": "Thu 10/08 (no year)"},
                {"value": "time-only", "label": "Time only"}]),
            vol.Optional("weather_entity", **({"default": s["weather_entity"]} if s["weather_entity"] else {})): selector.EntitySelector(selector.EntitySelectorConfig(domain="weather")),
        }
        return self.async_show_form(step_id="content", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_appearance(self, user_input=None):
        s = self.settings
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        return self.async_show_form(step_id="appearance", data_schema=vol.Schema({
            vol.Required("font", default=s["font"]): choices([key for key, (_, _, height) in FONTS.items() if height <= dimensions(self.config_entry.data["model"])[0] * 8]),
            vol.Required("alignment", default=s["alignment"]): choices(["left", "center", "right"]),
            vol.Required("color", default=s["color"]): choices(["green", "amber", "red"]),
            vol.Required("alert_color", default=s["alert_color"]): choices(["green", "amber", "red"]),
            vol.Required("sports_color", default=s["sports_color"]): choices(["amber", "green", "red"]),
            vol.Required("scroll", default=s["scroll"]): choices(["static", "left"]),
            vol.Required("speed", default=s["speed"]): choices(["slow", "medium", "fast"]),
        }))

    async def async_step_add_alert(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                if user_input["condition"] in ("above", "below") and not math.isfinite(float(user_input["value"])):
                    raise ValueError
                if not user_input["message"].strip() or len(user_input["message"]) > 190:
                    raise ValueError
            except ValueError:
                errors["base"] = "invalid_rule"
            else:
                alerts = [*self.settings["alerts"], user_input]
                return self.async_create_entry(title="", data={**self.config_entry.options, "alerts": alerts})
        return self.async_show_form(step_id="add_alert", data_schema=vol.Schema({
            vol.Required("entity"): selector.EntitySelector(),
            vol.Required("condition", default="equals"): choices(["equals", "not_equals", "above", "below"]),
            vol.Required("value", default="on"): str,
            vol.Required("message", default="{name}: {state}"): str,
            vol.Required("presentation", default="bottom-row"): choices(["bottom-row", "full-page"]),
        }), errors=errors)

    async def async_step_remove_alert(self, user_input=None):
        alerts = self.settings["alerts"]
        if not alerts:
            return self.async_abort(reason="no_alerts")
        if user_input is not None:
            index = int(user_input["rule"])
            return self.async_create_entry(title="", data={**self.config_entry.options, "alerts": [r for i, r in enumerate(alerts) if i != index]})
        options = [{"value": str(i), "label": f"{r['entity']} {r['condition']} {r['value']} — {r['message']}"} for i, r in enumerate(alerts)]
        return self.async_show_form(step_id="remove_alert", data_schema=vol.Schema({vol.Required("rule"): choices(options)}))
