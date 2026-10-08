from homeassistant.components.text import TextEntity
from .const import DOMAIN
from .entity import ViewMarqEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([QuickMessage(hass.data[DOMAIN][entry.entry_id], "quick_message", "Quick message")])


class QuickMessage(ViewMarqEntity, TextEntity):
    _attr_native_max = 190
    _attr_native_min = 0

    @property
    def native_value(self):
        return self.hub.settings["quick_message"]

    async def async_set_value(self, value):
        self.hub.save("quick_message", value)
