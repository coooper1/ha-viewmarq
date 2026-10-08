"""Persistent page model and deterministic renderer shared by sign and editor."""
from dataclasses import dataclass, replace
from copy import deepcopy
import json
import math
import textwrap

from .content import clean, usable, BINARY_MEANINGS, active_alerts, paginate
from .protocol import layout, page_message, FONTS
from .sports_data import SPORT_FIELDS
from .weather_data import WEATHER_FIELDS, reading, nws_alerts

PAGE_TYPES = {"text": "Text", "clock": "Clock and date", "weather": "Weather", "sports": "Live sports", "entity": "Home Assistant entity", "status": "External status", "alerts": "Active alert list", "custom": "Custom layout"}
FIELDS = {"text": "Your text", "clock": "Wall clock", "date": "Date", "temperature": "Weather temperature", "condition": "Weather condition", "humidity": "Weather humidity", "wind": "Weather wind", "entity_name": "Entity name", "entity_value": "Entity state", "entity_attribute": "Entity attribute", "status_text": "External status message", "alert_text": "Active alert message", **SPORT_FIELDS}
DATE_FORMATS = {"weekday-year": "%a %m/%d/%Y", "weekday-date": "%a %m/%d", "full-date": "%b %d, %Y", "date-only": "%m/%d/%Y", "iso-date": "%Y-%m-%d", "time-only": ""}
PAGE_TYPES["media"] = "Now Playing"
MEDIA_FIELDS = {"media_title": "Now Playing: title", "media_artist": "Now Playing: artist", "media_album_name": "Now Playing: album", "media_source": "Now Playing: source", "media_app_name": "Now Playing: app", "media_channel": "Now Playing: station / channel", "media_state": "Now Playing: playback state"}
FIELDS.update(MEDIA_FIELDS)
FIELDS.update(WEATHER_FIELDS)
PAGE_TYPES["weather_detail"] = "Detailed weather"


@dataclass(frozen=True)
class Frame:
    key: str
    text: str
    color: object
    font: str = "standard"
    alignment: str = "left"
    motion: str = "static"
    speed: str = "medium"
    dwell: int = 5
    kind: str = "Normal"
    page_id: str = ""
    start_row: int = 0

    def as_dict(self, model):
        return {**self.__dict__, "geometry": layout(model, self.font)}


def field(source, row=0, text="", height=1):
    return {"source": source, "row": row, "column": 0, "width": 0, "height": height, "align": None, "text": text}


def new_page(kind, page_id, settings=None):
    settings = settings or {}
    fields = {
        "text": [field("text", text="Your message", height=0)],
        "clock": [field("clock"), field("date", 1)],
        "weather": [field("temperature"), field("condition", 1)],
        "weather_detail": [field("temperature_f"), field("condition", 1),
                           {**field("rain_chance", 2), "label": "Rain next:"},
                           {**field("uv_index", 3), "label": "UV:"},
                           {**field("heat_index", 4), "label": "Heat:"},
                           {**field("feels_like", 5), "label": "Feels:"}],
        "sports": [field("match_score"), field("game_status", 1)],
        "entity": [field("entity_name"), field("entity_value", 1)],
        "status": [field("status_text", height=0)],
        "alerts": [field("alert_text", height=0)],
        "custom": [field("text", text="Your text")],
        "media": [field("media_title"), field("media_artist", 1)],
    }[kind]
    return {"id": page_id, "name": PAGE_TYPES[kind], "type": kind, "enabled": True,
            "fields": fields, "font": None, "color": None, "dwell": None, "motion": None,
            "speed": None, "visibility": {"mode": "always"}, "entity": "",
            "weather_entity": settings.get("weather_entity", ""), "teams": [], "hide_idle": True, "hide_paused": False,
            "time_format": settings.get("time_format", "12-hour"), "date_style": settings.get("date_style", "weekday-year")}


def effective_pages(settings):
    """An explicit empty list stays empty. Old options migrate without writes/loss."""
    if settings.get("pages") is not None:
        return deepcopy(settings["pages"])
    result = []
    for index, text in enumerate([settings.get("quick_message", ""), *settings.get("messages", "").splitlines()]):
        if clean(text):
            page = new_page("text", "quick-message" if index == 0 else f"message-{index}", settings)
            page["name"] = "Quick message" if index == 0 else f"Message {index}"
            page["fields"][0]["text"] = text
            page["fields"][0]["align"] = settings.get("alignment", "center")
            result.append(page)
    if settings.get("show_clock"):
        result.append(new_page("clock", "clock-date", settings))
    if settings.get("weather_entity"):
        result.append(new_page("weather", "weather", settings))
    # Keep a sports page even before teams are chosen; it is hidden outside live games.
    result.append(new_page("sports", "live-sports", settings))
    result.append(new_page("status", "external-status", settings))
    return result


def arranged_fields(fields, columns, alignment):
    """Share a row between distinct automatic left/center/right fields."""
    result = deepcopy(fields)
    groups = {}
    for item in result:
        if item.get("column", 0) == 0 and item.get("width", 0) == 0 and item.get("height", 1) == 1:
            groups.setdefault(item.get("row", 0), []).append(item)
    for group in groups.values():
        aligns = [item.get("align") or alignment for item in group]
        if len(group) < 2 or len(set(aligns)) != len(group):
            continue
        for item, align in zip(group, aligns):
            slot = ("left", "center", "right").index(align)
            start, end = slot * columns // 3, (slot + 1) * columns // 3
            item.update(column=start, width=end - start)
    for item in result:
        if item.get("width", 0) == 0 and item.get("height", 1) == 1:
            col, row = item.get("column", 0), item.get("row", 0)
            next_columns = [other.get("column", 0) for other in result
                            if other.get("row", 0) == row and other.get("column", 0) > col]
            item["width"] = min(next_columns, default=columns) - col
    return result


def validate_pages(pages, settings, model, allow_overlap=False):
    if not isinstance(pages, list) or len(pages) > 1000 or len(json.dumps(pages)) > 524288:
        raise ValueError("Page collection must fit within 512 KiB and 1,000 pages")
    ids = set()
    for page in pages:
        if not isinstance(page, dict) or page.get("type") not in PAGE_TYPES:
            raise ValueError("Choose a supported page type")
        page_id = page.get("id")
        if not isinstance(page_id, str) or not 1 <= len(page_id) <= 80 or page_id in ids:
            raise ValueError("Every page needs its own unique ID")
        ids.add(page_id)
        if not isinstance(page.get("name"), str) or not 1 <= len(page["name"]) <= 100:
            raise ValueError("Give each page a name of 1 to 100 characters")
        if type(page.get("enabled", True)) is not bool:
            raise ValueError("Invalid page enable setting")
        if any(type(page.get(key, True if key == "hide_idle" else False)) is not bool for key in ("hide_idle", "hide_paused")):
            raise ValueError("Invalid media visibility")
        font = page.get("font") or settings["font"]
        if font not in FONTS:
            raise ValueError("Choose a supported font")
        geometry = layout(model, font)
        for key, allowed in (("color", (None, "green", "amber", "red")), ("motion", (None, "static", "left")), ("speed", (None, "slow", "medium", "fast"))):
            if page.get(key) not in allowed:
                raise ValueError(f"Invalid page {key}")
        if page.get("dwell") is not None and (type(page["dwell"]) is not int or not 3 <= page["dwell"] <= 300):
            raise ValueError("Page duration must be 3 to 300 seconds")
        if page.get("time_format", "12-hour") not in ("12-hour", "24-hour") or page.get("date_style", "weekday-year") not in DATE_FORMATS:
            raise ValueError("Invalid clock or date format")
        for key in ("entity", "weather_entity"):
            if not isinstance(page.get(key, ""), str):
                raise ValueError("Choose an entity")
        if page.get("weather_entity") and not page["weather_entity"].startswith("weather."):
            raise ValueError("Choose a weather entity")
        if not isinstance(page.get("teams", []), list) or any(not isinstance(key, str) or len(key) > 80 for key in page.get("teams", [])):
            raise ValueError("Invalid page team selection")
        visibility = page.get("visibility", {})
        if not isinstance(visibility, dict) or visibility.get("mode", "always") not in ("always", "live_games", "no_live_games", "sensor_active", "sensor_inactive", "entity_state"):
            raise ValueError("Invalid page visibility condition")
        if not all(isinstance(visibility.get(key, ""), str) for key in ("entity", "value")):
            raise ValueError("Invalid visibility entity or state")
        fields = page.get("fields")
        if not isinstance(fields, list) or len(fields) > 128:
            raise ValueError("Use up to 128 fields per page")
        occupied = set()
        for item in fields:
            if not isinstance(item, dict) or item.get("source") not in FIELDS:
                raise ValueError("Choose a supported field")
            for key in ("row", "column", "width", "height"):
                if type(item.get(key, 0)) is not int or item.get(key, 0) < 0:
                    raise ValueError("Field positions and sizes must be whole numbers")
            row, col = item.get("row", 0), item.get("column", 0)
            width = item.get("width", 0) or geometry["columns"] - col
            height = item.get("height", 1) or max(1, geometry["rows"] - row % geometry["rows"])
            if row > 63 or not 0 <= col < geometry["columns"] or not 1 <= width <= geometry["columns"] - col or not 1 <= height <= 64:
                raise ValueError(f"A field in {page['name']} does not fit its {geometry['columns']}-column font grid")
            if item.get("align") not in (None, "left", "center", "right"):
                raise ValueError("Invalid field alignment")
            if item.get("color") not in (None, "green", "amber", "red"):
                raise ValueError("Invalid field color")
            for key in ("text", "label", "entity", "attribute"):
                if not isinstance(item.get(key, ""), str) or len(item.get(key, "")) > (10000 if key == "text" else 190):
                    raise ValueError(f"Invalid field {key}")
        for item in arranged_fields(fields, geometry["columns"], settings.get("alignment", "center")):
            row, col = item.get("row", 0), item.get("column", 0)
            width = item.get("width", 0) or geometry["columns"] - col
            height = item.get("height", 1) or max(1, geometry["rows"] - row % geometry["rows"])
            cells = {(y, x) for y in range(row, row + height) for x in range(col, col + width)}
            if occupied & cells and not allow_overlap:
                raise ValueError(f"Fields overlap on {page['name']}. Move a field or reduce its width/height.")
            occupied |= cells
    return deepcopy(pages)


def visible(page, get_state, has_games):
    if not page.get("enabled", True):
        return False
    condition = page.get("visibility", {})
    mode = condition.get("mode", "always")
    if mode == "always":
        return True
    if mode in ("live_games", "no_live_games"):
        return has_games == (mode == "live_games")
    state = get_state(condition.get("entity", ""))
    if not usable(state):
        return False
    if mode == "entity_state":
        return state.state == condition.get("value", "")
    if state.state not in ("on", "off"):
        return False
    expected = BINARY_MEANINGS.get(state.attributes.get("device_class"), ("on", "active"))[0]
    return (state.state == expected) == (mode == "sensor_active")


def entity_text(state):
    if not usable(state):
        return "--"
    if state.state in ("on", "off"):
        meanings = {"door": ("Open", "Closed"), "window": ("Open", "Closed"), "opening": ("Open", "Closed"), "garage_door": ("Open", "Closed"), "connectivity": ("Connected", "Disconnected"), "battery": ("Low", "Normal"), "moisture": ("Wet", "Dry"), "lock": ("Unlocked", "Locked"), "safety": ("Unsafe", "Safe"), "presence": ("Home", "Away")}
        on, off = meanings.get(state.attributes.get("device_class"), ("Active", "Inactive"))
        return on if state.state == "on" else off
    return clean(str(state.state) + (" " + str(state.attributes["unit_of_measurement"]) if state.attributes.get("unit_of_measurement") else ""))


def field_value(item, page, settings, get_state, now, record):
    source = item["source"]
    if source == "text":
        value = item.get("text", "")
    elif source == "clock":
        value = now.strftime("%I:%M %p").lstrip("0") if page.get("time_format", settings["time_format"]) == "12-hour" else now.strftime("%H:%M")
    elif source == "date":
        value = now.strftime(DATE_FORMATS[page.get("date_style", settings["date_style"])])
    elif source in WEATHER_FIELDS:
        weather = get_state(page.get("weather_entity") or settings.get("weather_entity", ""))
        override = get_state(item["entity"]) if item.get("entity") else None
        value = "Unavailable" if item.get("entity") and override is None else reading(source, weather, override)
    elif source in ("temperature", "condition", "humidity", "wind"):
        state = get_state(page.get("weather_entity") or settings.get("weather_entity", ""))
        value = "--"
        if usable(state):
            attrs = state.attributes
            if source == "condition":
                value = state.state.replace("-", " ").title()
            else:
                key, unit = {"temperature": ("temperature", attrs.get("temperature_unit", "")), "humidity": ("humidity", "%"), "wind": ("wind_speed", attrs.get("wind_speed_unit", ""))}[source]
                number = attrs.get(key)
                if number is not None:
                    value = (f"{number:g}" if isinstance(number, (int, float)) else str(number)) + str(unit)
    elif source in MEDIA_FIELDS:
        state = get_state(item.get("entity") or page.get("entity", ""))
        key = {"media_source": "source", "media_app_name": "app_name"}.get(source, source)
        value = (state.state.title() if source == "media_state" else state.attributes.get(key, "")) if usable(state) else ""
    elif source.startswith("entity_"):
        state = get_state(item.get("entity") or page.get("entity", ""))
        if source == "entity_name":
            value = state.attributes.get("friendly_name", "Entity") if state else "Entity"
        elif source == "entity_attribute":
            value = state.attributes.get(item.get("attribute"), "--") if usable(state) else "--"
            if not isinstance(value, (str, int, float, bool)):
                value = "--"
        else:
            value = entity_text(state)
    else:
        value = record.get("fields", {}).get(source, "")
    return clean((item.get("label", "") + " " if item.get("label") else "") + str(value))


def render_page(page, settings, model, get_state, now, record):
    font = page.get("font") or settings["font"]
    geometry = layout(model, font)
    rows, columns = geometry["rows"], geometry["columns"]
    fields, slices, logical_rows = [], 1, rows
    for item in arranged_fields(page["fields"], columns, settings.get("alignment", "center")):
        row, col = item.get("row", 0), item.get("column", 0)
        width = item.get("width", 0) or columns - col
        height = item.get("height", 1) or max(1, rows - row % rows)
        text = field_value(item, page, settings, get_state, now, record)
        chunks = []
        for line in text.split("\n"):
            chunks.extend(textwrap.wrap(line, width, break_long_words=True, break_on_hyphens=False) or [""])
        slices = max(slices, math.ceil(len(chunks) / height))
        logical_rows = max(logical_rows, row + height)
        fields.append((item, chunks, width, height))
    category_color = settings["sports_color"] if page["type"] == "sports" else settings["alert_color"] if page["type"] == "alerts" else record.get("color") or settings["color"]
    result, seen = [], set()
    base_color = page.get("color") or category_color
    for part in range(slices):
        grid = [[" "] * columns for _ in range(logical_rows)]
        color_grid = [[base_color] * columns for _ in range(logical_rows)]
        for item, chunks, width, height in fields:
            start = min(part * height, max(0, math.ceil(len(chunks) / height) - 1) * height)
            for offset, chunk in enumerate(chunks[start:start + height]):
                align = item.get("align") or settings.get("alignment", "center")
                text = chunk.ljust(width) if align == "left" else chunk.rjust(width) if align == "right" else chunk.center(width)
                row, col = item.get("row", 0) + offset, item.get("column", 0)
                grid[row][col:col + width] = list(text)
                color_grid[row][col:col + width] = [item.get("color") or base_color] * width
        for start_row in range(0, logical_rows, rows):
            lines = ["".join(line).rstrip() for line in grid[start_row:start_row + rows]]
            lines += [""] * (rows - len(lines))
            text = "\n".join(lines)
            shades = tuple(tuple(color_grid[start_row + i][:len(line)]) if start_row + i < logical_rows else () for i, line in enumerate(lines))
            frame_color = base_color if all(c == base_color for line in shades for c in line) else shades
            signature = (text, frame_color)
            if not text.strip() or signature in seen:
                continue
            seen.add(signature)
            frame = Frame(f"{page['id']}:{record.get('id', 'main')}:{part}:{start_row}", text,
                          frame_color, font, "left",
                          "static" if isinstance(frame_color, tuple) else page.get("motion") or settings["scroll"], page.get("speed") or settings["speed"],
                          page.get("dwell") or settings["dwell"], page["type"], page["id"], start_row)
            page_message(frame.text, 1, model, frame.color, frame.font, frame.alignment)
            result.append(frame)
    return result


def render_pages(settings, model, get_state, now, games, statuses=(), alerts=()):
    result = []
    for page in effective_pages(settings):
        if not visible(page, get_state, bool(games)):
            continue
        has_sports = page["type"] == "sports" or any(f["source"] in SPORT_FIELDS for f in page["fields"])
        if has_sports:
            records = [game for game in games if not page.get("teams") or game["team_key"] in page["teams"]]
        elif page["type"] == "weather" and not usable(get_state(page.get("weather_entity") or settings.get("weather_entity", ""))):
            continue
        elif page["type"] == "entity" and not usable(get_state(page.get("entity", ""))):
            continue
        elif page["type"] == "media":
            state = get_state(page.get("entity", ""))
            if not usable(state) or (page.get("hide_idle", True) and state.state in ("idle", "off", "standby")) or (page.get("hide_paused", False) and state.state == "paused"):
                continue
            records = [{"id": "media", "fields": {}}]
        elif page["type"] == "status":
            records = list(statuses)
        elif page["type"] == "alerts":
            records = [{"id": str(i), "fields": {"alert_text": text}} for i, (text, _layout, _severity) in enumerate(alerts)]
        else:
            if games and settings.get("sports_mode") == "hide_clock" and page["type"] == "clock":
                continue
            records = [{"id": "main", "fields": {}}]
        for record in records:
            result.extend(render_page(page, settings, model, get_state, now, record))
    if games and settings.get("sports_mode") == "only":
        sports_ids = {p["id"] for p in effective_pages(settings) if p["type"] == "sports" or any(f["source"] in SPORT_FIELDS for f in p["fields"])}
        selected = [frame for frame in result if frame.page_id in sports_ids]
        if selected:
            result = selected
    return result


def compose(settings, model, get_state, now, games, statuses=()):
    """The same final frames are used by hardware and the editor preview."""
    blank = Frame("blank", " ", settings["color"], font=settings["font"])
    if not settings["enabled"]:
        return [replace(blank, kind="Display disabled")]
    alerts = active_alerts(settings, get_state)
    nws, nws_status = nws_alerts(get_state(settings["nws_alert_entity"]), now) if settings.get("nws_alert_entity") else ([], "")
    urgent = [(text, settings["alert_color"]) for text, mode, _ in alerts if mode == "full-page"]
    urgent = [(item["text"], "red") for item in nws if item["warning"]] + urgent
    geometry = layout(model, settings["font"])
    if urgent:
        return [Frame(f"urgent:{i}", text, color, settings["font"], "center", dwell=settings["dwell"], kind="Priority alert") for i, (text, color) in enumerate(paginate(urgent, geometry["rows"], geometry["columns"]))]
    normal = render_pages(settings, model, get_state, now, games, statuses, alerts)
    advisories = [item["text"] for item in nws if not item["warning"]]
    if nws_status and "unavailable" in nws_status:
        advisories.append(nws_status)
    normal.extend(Frame(f"weather-advisory:{i}", text, "amber", settings["font"], "center", dwell=settings["dwell"], kind="Weather advisory") for i, (text, _) in enumerate(paginate([(text, "amber") for text in advisories], geometry["rows"], geometry["columns"])))
    routine = [(text, settings["alert_color"]) for text, mode, _ in alerts if mode != "full-page"]
    if not routine:
        return normal or [blank]
    result = []
    for frame in normal or [blank]:
        grid = layout(model, frame.font)
        if grid["rows"] < 2:
            result.append(frame)
            result.extend(Frame(f"{frame.key}:alert:{i}", text, color, frame.font, "center", dwell=settings["dwell"], kind="Routine alert") for i, (text, color) in enumerate(paginate(routine, 1, grid["columns"])))
            continue
        source_lines = frame.text.split("\n")
        source_colors = [frame.color] * len(source_lines) if isinstance(frame.color, str) else list(frame.color)
        tops = [(source_lines[i:i + grid["rows"] - 1], source_colors[i:i + grid["rows"] - 1]) for i in range(0, len(source_lines), grid["rows"] - 1)]
        tops = [(lines, shades) for lines, shades in tops if any(line.strip() for line in lines)] or [([""], [settings["color"]])]
        bottoms = paginate(routine, 1, grid["columns"])
        for index in range(max(len(tops), len(bottoms))):
            lines, shades = tops[index % len(tops)]
            bottom = bottoms[index % len(bottoms)][0].center(grid["columns"])
            text = "\n".join(lines + [""] * (grid["rows"] - 1 - len(lines)) + [bottom])
            result.append(replace(frame, key=f"{frame.key}:split:{index}", text=text, color=tuple(shades) + (settings["color"],) * (grid["rows"] - 1 - len(lines)) + (settings["alert_color"],), motion="static", kind="Normal + routine alert"))
    return result


def sample_frames(page, settings, model, get_state, now):
    """Explicit editor-only layout sample. Never called by DisplayHub."""
    from types import SimpleNamespace
    def sample_state(entity):
        actual = get_state(entity)
        if entity == page.get("entity") and page["type"] == "media":
            return SimpleNamespace(state="playing", attributes={"media_title": "Sample song", "media_artist": "Sample artist", "media_album_name": "Sample album", "source": "Sample source", "app_name": "Sample app", "media_channel": "Sample station"})
        return actual
    values = {key: "Sample" for key in FIELDS}
    # Representative editor-only numbers for every supported box-score field.
    for side, stats in (
        ("team", (248, 176, 72, 14, 32, 18, "47.5%", 1)),
        ("opponent", (213, 152, 61, 11, 29, 15, "44.2%", 2)),
    ):
        for name, value in zip(("total_yards", "passing_yards", "rushing_yards", "first_downs", "rebounds", "assists", "field_goal_pct", "turnovers"), stats):
            values[f"{side}_{name}"] = str(value)
    values["league"] = "NCAAF"
    values.update(match_score="HOME 14 - AWAY 7", team_abbr="HOME", opponent_abbr="AWAY", home_abbr="HOME", away_abbr="AWAY", team_name="Home team", opponent_name="Away team", home_name="Home team", away_name="Away team", team_score="14", opponent_score="7", home_score="14", away_score="7", game_clock="04:32", game_period="Q2", game_status="Q2 04:32", down_distance="2nd & 7", yard_line="HOME 35", possession="HOME", status_text="Sample status message", alert_text="Sample alert")
    return [replace(frame, kind="SAMPLE — editor only") for frame in render_page(page, settings, model, sample_state, now, {"id":"sample", "fields":values})]


def live_game_preview(settings, model, get_state, now, games):
    """Preview actual games independently of the currently rotating sign page."""
    pages = [p for p in effective_pages(settings) if p.get("enabled", True) and (p["type"] == "sports" or any(f["source"] in SPORT_FIELDS for f in p["fields"]))]
    preview = {**settings, "pages": pages or [new_page("sports", "preview-live-games", settings)]}
    return render_pages(preview, model, get_state, now, games)


class Player:
    """Keep time by stable page identity, not by a changing clock or score value."""
    def __init__(self):
        self.key = None
        self.index = 0
        self.deadline = 0

    def choose(self, frames, now):
        if not frames:
            self.key = None
            return None
        keys = [frame.key for frame in frames]
        if self.key in keys:
            self.index = keys.index(self.key)
            if now >= self.deadline:
                self.index = (self.index + 1) % len(frames)
                self.deadline = now + frames[self.index].dwell
        else:
            self.index %= len(frames)
            self.deadline = now + frames[self.index].dwell
        current = frames[self.index]
        self.key = current.key
        return current
