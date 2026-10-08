"""Serialized, bounded device IO and HA state-driven content."""
import asyncio
from datetime import timedelta
import logging
import random
import socket
import time

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN
from .builder import Player, compose, effective_pages, new_page
from .protocol import Modbus, send, layout
from .espn import ESPNCache
from .status_feed import records
from .weather_cache import WeatherCache

_LOGGER = logging.getLogger(__name__)


class DisplayHub:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.settings = {**DEFAULTS, **entry.options}
        self.geometry = layout(entry.data["model"], self.settings["font"])
        self.settings.update({key: self.geometry[key] for key in ("rows", "columns")})
        self.rotation = Player()
        self.espn = hass.data.setdefault(f"{DOMAIN}_espn", ESPNCache(hass))
        self.weather = hass.data.setdefault(f"{DOMAIN}_weather", WeatherCache(hass))
        self.sports_status = {}
        self.last = None
        self.last_sent = 0
        self.next_attempt = time.monotonic() + random.uniform(0, 3)
        self.io_limit = hass.data.setdefault(f"{DOMAIN}_io_limit", asyncio.Semaphore(4))
        self.failures = 0
        self.status = "Starting"
        self.displayed = ""
        self.task = None
        self.unsub = None
        self.signal = f"{DOMAIN}_{entry.entry_id}"
        self.stopped = False

    @callback
    def start(self):
        self.stopped = False
        self.unsub = async_track_time_interval(self.hass, self.tick, timedelta(seconds=1))
        self.tick()

    async def stop(self):
        self.stopped = True
        if self.unsub:
            self.unsub()
            self.unsub = None
        # Executor writes must finish before an integration reload creates another writer.
        if self.task:
            await self.task

    @callback
    def tick(self, *_):
        if self.stopped or (self.task and not self.task.done()):
            return
        self.task = self.hass.async_create_task(self.update())

    def transmit(self, frame):
        config = {**self.entry.data, "color": frame.color, "font": frame.font, "alignment": frame.alignment, "scroll": frame.motion, "speed": frame.speed, "page_layout": frame.motion == "static" or isinstance(frame.color, tuple)}
        text = frame.text
        if not config["page_layout"]:
            text = " ".join(text.split()).replace("°", chr(96))
        with socket.create_connection((config["host"], config["port"]), timeout=2) as sock:
            return send(Modbus(sock, config["unit_id"]), config, text)

    def frames(self, settings=None):
        settings = settings or self.settings
        games, status = self.espn.games(settings)
        frames = compose(settings, self.entry.data["model"], self.weather.state, dt_util.now(), games, records(self.hass, self.entry.entry_id))
        return frames, status

    async def update(self):
        now = time.monotonic()
        if now < self.next_attempt:
            return
        try:
            frames, self.sports_status = self.frames()
            selected = self.rotation.choose(frames, now)
            # Refresh below any configured device heartbeat, but avoid restarting scrolling each second.
            heartbeat = self.entry.data.get("heartbeat_seconds", 0)
            refresh = max(1, heartbeat / 2) if heartbeat else 60
            if selected == self.last and now - self.last_sent < refresh:
                return
            async with self.io_limit:
                if self.stopped:
                    return
                await self.hass.async_add_executor_job(self.transmit, selected)
            self.last, self.last_sent = selected, time.monotonic()
            self.displayed = selected.text
            self.status = "Connected" if self.settings["enabled"] else "Paused"
            self.failures = 0
        except (OSError, ValueError, RuntimeError) as error:
            self.status = str(error)
            self.failures += 1
            # Next scheduled content update after backoff; never retry inside an uncertain transaction.
            self.next_attempt = time.monotonic() + min(60, 5 * 2 ** min(self.failures - 1, 4)) + random.uniform(0, 2)
            _LOGGER.warning("ViewMarq update failed: %s", error)
        async_dispatcher_send(self.hass, self.signal)

    @callback
    def save(self, key, value):
        changes = {key: value}
        if key == "quick_message" and self.settings.get("pages") is not None:
            pages = effective_pages(self.settings)
            page = next((p for p in pages if p["id"] == "quick-message"), None)
            if page:
                pages.remove(page)
            if value.strip():
                page = new_page("text", "quick-message", self.settings)
                page["name"] = "Quick message"
                page["fields"][0]["text"] = value
                pages.insert(0, page)
            changes["pages"] = pages
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, **changes})
