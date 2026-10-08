"""Bounded Home Assistant hourly forecast cache for preview and display."""
import asyncio
import time
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.util import dt as dt_util

from .weather_data import timestamp


class WeatherCache:
    def __init__(self, hass):
        self.hass = hass
        self.data, self.next_poll, self.tasks = {}, {}, {}
        self.limit = asyncio.Semaphore(2)

    def state(self, entity_id):
        state = self.hass.states.get(entity_id)
        if not state or not entity_id.startswith("weather."):
            return state
        tick = time.monotonic()
        if tick >= self.next_poll.get(entity_id, 0) and entity_id not in self.tasks:
            self.next_poll[entity_id] = tick + 600
            self.tasks[entity_id] = self.hass.async_create_task(self.refresh(entity_id))
        cached = self.data.get(entity_id)
        if cached and tick - cached[0] < 1800:
            now = dt_util.now()
            forecast = next((item for item in cached[1] if (when := timestamp(item.get("datetime"))) and now <= when <= now + timedelta(hours=2)), {})
            return SimpleNamespace(state=state.state, attributes={**state.attributes, "_viewmarq_forecast": forecast})
        return state

    async def refresh(self, entity_id):
        try:
            async with self.limit:
                async with asyncio.timeout(8):
                    response = await self.hass.services.async_call("weather", "get_forecasts", {"entity_id": entity_id, "type": "hourly"}, blocking=True, return_response=True)
            items = (response or {}).get(entity_id, {}).get("forecast", [])
            if isinstance(items, list):
                self.data[entity_id] = (time.monotonic(), [x for x in items if isinstance(x, dict)])
        except Exception:
            self.next_poll[entity_id] = time.monotonic() + 120
        finally:
            self.tasks.pop(entity_id, None)
