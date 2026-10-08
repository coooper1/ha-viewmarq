from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN
from .entity import ViewMarqEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DisplayStatus(hass.data[DOMAIN][entry.entry_id], "status", "Connection")])


class DisplayStatus(ViewMarqEntity, SensorEntity):
    @property
    def native_value(self):
        return "error" if self.hub.failures else self.hub.status.lower()

    @property
    def extra_state_attributes(self):
        return {"displayed_text": self.hub.displayed, "detail": self.hub.status, "consecutive_failures": self.hub.failures, "sports_feeds": self.hub.sports_status}
