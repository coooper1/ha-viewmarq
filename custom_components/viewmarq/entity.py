from homeassistant.helpers.entity import Entity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN


class ViewMarqEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, hub, key, name):
        self.hub = hub
        self._attr_unique_id = f"{hub.entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, hub.entry.entry_id)},
            "name": hub.entry.title, "manufacturer": "AutomationDirect",
            "model": hub.entry.data.get("model", "ViewMarq"),
        }

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, self.hub.signal, self.async_write_ha_state))
