from homeassistant.components.number import NumberEntity, NumberMode
from .const import DOMAIN
from .entity import ViewMarqEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([Dwell(hass.data[DOMAIN][entry.entry_id], "dwell", "Page duration")])


class Dwell(ViewMarqEntity, NumberEntity):
    _attr_native_min_value = 3
    _attr_native_max_value = 300
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "s"
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self):
        return self.hub.settings["dwell"]

    async def async_set_native_value(self, value):
        self.hub.save("dwell", int(value))
