"""Content formatting and rotation, independent of Home Assistant runtime."""
from datetime import datetime
import math
import unicodedata
import textwrap


def clean(text):
    text = str(text).replace("<", "(").replace(">", ")")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "xmlcharrefreplace").decode().replace("&#176;", "°")
    # Keep explicit line boundaries; unsupported glyphs become their Unicode reference rather than disappearing.
    return "\n".join(" ".join(line.split()) for line in text.split("\n")).strip()


def paginate(items, rows, columns):
    result = []
    for text, color in items:
        lines = []
        for line in text.split("\n"):
            lines.extend(textwrap.wrap(line, width=columns, break_long_words=True, break_on_hyphens=False) or [""])
        for start in range(0, len(lines), rows):
            result.append(("\n".join(lines[start:start + rows]), color))
    return list(dict.fromkeys(result))


def usable(state):
    return state is not None and state.state not in ("unknown", "unavailable", "")


# HA device classes describe the meaning of the raw binary state.
BINARY_MEANINGS = {
    "door": ("on", "open"), "window": ("on", "open"),
    "opening": ("on", "open"), "garage_door": ("on", "open"),
    "motion": ("on", "motion detected"), "occupancy": ("on", "occupied"),
    "presence": ("on", "present"), "moisture": ("on", "wet"),
    "smoke": ("on", "smoke detected"), "gas": ("on", "gas detected"),
    "carbon_monoxide": ("on", "CO detected"), "problem": ("on", "problem detected"),
    "safety": ("on", "unsafe"), "tamper": ("on", "tampering detected"),
    "battery": ("on", "battery low"), "connectivity": ("off", "disconnected"),
    "plug": ("off", "unplugged"), "lock": ("on", "unlocked"),
    "heat": ("on", "hot"), "cold": ("on", "cold"),
    "vibration": ("on", "vibration detected"), "sound": ("on", "sound detected"),
    "running": ("on", "running"), "power": ("on", "power detected"),
    "battery_charging": ("on", "charging"), "light": ("on", "light detected"),
    "moving": ("on", "moving"), "update": ("on", "update available"),
}
HAZARDS = {"smoke", "gas", "carbon_monoxide", "safety", "moisture"}


class SensorAlert(tuple):
    """Preserve the message/layout/severity tuple while retaining its source."""
    def __new__(cls, message, presentation, severity, entity):
        value = super().__new__(cls, (message, presentation, severity))
        value.entity = entity
        return value


def active_alerts(settings, get_state):
    """Return message, layout and severity; unknown states never raise an alert."""
    result = []
    overrides = settings.get("sensor_overrides", {})
    selected = settings.get("binary_sensors", [])
    for entity_id in selected:
        state = get_state(entity_id)
        if not usable(state) or state.state not in ("on", "off"):
            continue
        device_class = state.attributes.get("device_class", "")
        expected, wording = BINARY_MEANINGS.get(device_class, ("on", "active"))
        if state.state != expected:
            continue
        override = overrides.get(entity_id, {})
        layout = override.get("presentation", "automatic")
        if layout == "automatic":
            layout = "full-page" if device_class in HAZARDS else "bottom-row"
        name = state.attributes.get("friendly_name", entity_id)
        message = override.get("message") or f"{name}: {wording}"
        result.append(SensorAlert(clean(message), layout, 2 if layout == "full-page" else 1, entity_id))
    for rule in settings["alerts"]:
        # A selected sensor's automatic rule replaces its legacy manual rule.
        if rule["entity"] in selected:
            continue
        state = get_state(rule["entity"])
        if active(rule, state):
            text = rule["message"].replace("{state}", state.state).replace("{name}", str(state.attributes.get("friendly_name", rule["entity"])))
            layout = rule.get("presentation", settings.get("alert_layout", "bottom-row"))
            if clean(text):
                result.append(SensorAlert(clean(text), layout, 2 if layout == "full-page" else 1, rule["entity"]))
    return result


def active(rule, state):
    if not usable(state):
        return False
    value, expected, condition = state.state, rule["value"], rule["condition"]
    if condition == "equals":
        return value == expected
    if condition == "not_equals":
        return value != expected
    try:
        number, threshold = float(value), float(expected)
        if not math.isfinite(number) or not math.isfinite(threshold):
            return False
        return number > threshold if condition == "above" else number < threshold
    except (TypeError, ValueError):
        return False


def sports(state, now, max_age, live_only):
    if not usable(state) or state.state not in (("IN",) if live_only else ("PRE", "IN", "POST")):
        return None
    attrs = state.attributes
    try:
        updated = attrs.get("last_update")
        updated = updated if isinstance(updated, datetime) else datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
        age = (now - updated).total_seconds()
        if not 0 <= age <= max_age * 60:
            return None
    except (TypeError, ValueError):
        return None
    team = attrs.get("team_abbr") or attrs.get("team_name")
    opponent = attrs.get("opponent_abbr") or attrs.get("opponent_name")
    if not team or not opponent:
        return None
    if state.state == "PRE":
        return clean(f"{team} vs {opponent} {attrs.get('date', 'Upcoming')}")
    a, b = attrs.get("team_score"), attrs.get("opponent_score")
    if a is None or b is None:
        return None
    detail = "Final" if state.state == "POST" else " ".join(str(x) for x in ((f"Q{attrs['quarter']}" if attrs.get("quarter") else None), attrs.get("clock")) if x is not None)
    return clean(f"{team} {a} - {opponent} {b}\n{detail}")


def pages(settings, get_state, now):
    ordinary, alerts = [], []
    for text in [settings["quick_message"], *settings["messages"].splitlines()]:
        if clean(text):
            ordinary.append((clean(text), settings["color"]))
    if settings["show_clock"]:
        clock = now.strftime("%I:%M %p").lstrip("0") if settings.get("time_format", "12-hour") == "12-hour" else now.strftime("%H:%M")
        date_format = {"weekday-date": "%a %m/%d", "weekday-year": "%a %m/%d/%Y", "full-date": "%b %d, %Y", "date-only": "%m/%d/%Y", "iso-date": "%Y-%m-%d", "time-only": ""}[settings["date_style"]]
        ordinary.append((clean(f"{clock}\n{now.strftime(date_format)}"), settings["color"]))
    weather = get_state(settings["weather_entity"]) if settings["weather_entity"] else None
    if usable(weather):
        attrs = weather.attributes
        temperature = attrs.get("temperature")
        temperature = f"{temperature:g}" if isinstance(temperature, (int, float)) else temperature
        ordinary.append((clean((f"{temperature}{attrs.get('temperature_unit', '')}\n" if temperature is not None else "") + weather.state.replace('-', ' ').title()), settings["color"]))
    for entity_id in settings["sports_entities"]:
        text = sports(get_state(entity_id), now, settings["sports_max_age"], settings["sports_live_only"])
        if text:
            ordinary.append((text, settings["color"]))
    for text, _layout, _severity in active_alerts(settings, get_state):
        alerts.append((text, settings["alert_color"]))
    return paginate(ordinary, settings.get("rows", 2), settings.get("columns", 24)), paginate(alerts, settings.get("rows", 2), settings.get("columns", 24))


class Rotation:
    def __init__(self):
        self.index = {False: 0, True: 0}
        self.deadline = 0
        self.priority = False
        self.current = None

    def select(self, ordinary, alerts, settings, monotonic):
        priority = bool(alerts and settings["alert_priority"])
        choices = alerts if priority else ordinary + alerts
        if not choices:
            self.current = None
            return (" ", settings["color"])
        if self.current not in choices:
            self.current = None
        if priority != self.priority:
            self.priority = priority
            self.deadline = monotonic + settings["dwell"]
            self.current = None
        elif monotonic >= self.deadline:
            if self.deadline:
                self.index[priority] += 1
            self.deadline = monotonic + settings["dwell"]
            self.current = None
        self.index[priority] %= len(choices)
        if self.current is None:
            self.current = choices[self.index[priority]]
        return self.current
