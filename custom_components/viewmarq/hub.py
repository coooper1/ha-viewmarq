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
from .content import Rotation, pages, active_alerts, paginate
from .protocol import Modbus, send, layout
from .espn import ESPNCache
from .status_feed import status_pages

_LOGGER = logging.getLogger(__name__)


class DisplayHub:
    def __init__(self, hass, entry):
        self.hass, self.entry = hass, entry
        self.settings = {**DEFAULTS, **entry.options}
        self.geometry = layout(entry.data["model"], self.settings["font"])
        self.settings.update({key: self.geometry[key] for key in ("rows", "columns")})
        self.rotation = Rotation()
        self.top_rotation = Rotation()
        self.alert_rotation = Rotation()
        self.espn = hass.data.setdefault(f"{DOMAIN}_espn", ESPNCache(hass))
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

    def transmit(self, text, color):
        config = {**self.entry.data, "color": color, "font": self.settings["font"], "alignment": self.settings["alignment"], "scroll": self.settings["scroll"], "speed": self.settings["speed"], "page_layout": self.settings["scroll"] == "static" or isinstance(color, tuple)}
        if not config["page_layout"]:
            text = text.replace("\n", " ").replace("°", chr(96))
        with socket.create_connection((config["host"], config["port"]), timeout=2) as sock:
            return send(Modbus(sock, config["unit_id"]), config, text)

    async def update(self):
        now = time.monotonic()
        if now < self.next_attempt:
            return
        try:
            if self.settings["enabled"]:
                ordinary, alerts = pages(self.settings, self.hass.states.get, dt_util.now())
                sports_pages, self.sports_status = self.espn.pages(self.settings)
                ordinary.extend(sports_pages)
                ordinary.extend(status_pages(self.hass, self.entry.entry_id, self.settings))
                active_items = active_alerts(self.settings, self.hass.states.get)
                urgent = [(text, self.settings["alert_color"]) for text, layout, _ in active_items if layout == "full-page"]
                if urgent:
                    urgent_pages = paginate(urgent, self.settings["rows"], self.settings["columns"])
                    selected = self.rotation.select([], urgent_pages, {**self.settings, "alert_priority": True}, now)
                elif alerts and self.settings["rows"] >= 2:
                    split = {**self.settings, "rows": 1, "alert_priority": False}
                    top, bottom = pages(split, self.hass.states.get, dt_util.now())
                    sports_top, _ = self.espn.pages(split)
                    top.extend(sports_top)
                    top.extend(status_pages(self.hass, self.entry.entry_id, split))
                    top_page = self.top_rotation.select(top, [], split, now)
                    bottom_page = self.alert_rotation.select(bottom, [], split, now)
                    padding = self.settings["rows"] - 2
                    selected = (top_page[0] + "\n" * (padding + 1) + bottom_page[0], (top_page[1],) + (self.settings["color"],) * padding + (bottom_page[1],))
                else:
                    selected = self.rotation.select(ordinary, alerts, {**self.settings, "alert_priority": False}, now)
            else:
                selected = (" ", self.settings["color"])
            # Refresh below any configured device heartbeat, but avoid restarting scrolling each second.
            heartbeat = self.entry.data.get("heartbeat_seconds", 0)
            refresh = max(1, heartbeat / 2) if heartbeat else 60
            if selected == self.last and now - self.last_sent < refresh:
                return
            async with self.io_limit:
                if self.stopped:
                    return
                await self.hass.async_add_executor_job(self.transmit, *selected)
            if selected != self.last:
                self.rotation.deadline = time.monotonic() + self.settings["dwell"]
            self.last, self.last_sent = selected, time.monotonic()
            self.displayed = selected[0].strip()
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
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, key: value})
