"""Home Assistant ViewMarq integration."""
from .const import DOMAIN, PLATFORMS


async def async_setup_entry(hass, entry):
    from .hub import DisplayHub
    from .panel import register
    from .status_feed import register as register_status
    await register(hass)
    register_status(hass)
    hub = DisplayHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload))
    hub.start()
    return True


async def async_reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    hub = hass.data[DOMAIN][entry.entry_id]
    await hub.stop()
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    hub.start()
    return False
