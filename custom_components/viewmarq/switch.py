from homeassistant.components.switch import SwitchEntity
from .const import DOMAIN
from .entity import ViewMarqEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Enabled(hass.data[DOMAIN][entry.entry_id], "enabled", "Display enabled")])


class Enabled(ViewMarqEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.hub.settings["enabled"]

    async def async_turn_on(self, **kwargs):
        self.hub.save("enabled", True)

    async def async_turn_off(self, **kwargs):
        self.hub.save("enabled", False)
