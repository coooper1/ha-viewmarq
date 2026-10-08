"""Expiring, authenticated HA action for optional host-supplied status pages."""
import time
import voluptuous as vol
from homeassistant.exceptions import HomeAssistantError
from .const import DOMAIN
from .content import clean, paginate


def register(hass):
    if hass.services.has_service(DOMAIN, "publish_status"):
        return

    async def publish(call):
        entry_id = call.data["entry_id"]
        if entry_id not in hass.data.get(DOMAIN, {}):
            raise HomeAssistantError("Choose a loaded ViewMarq display")
        feeds = hass.data.setdefault(f"{DOMAIN}_status_feeds", {}).setdefault(entry_id, {})
        source = call.data["source"]
        if not call.data["message"].strip():
            feeds.pop(source, None)
        else:
            if source not in feeds and len(feeds) >= 10:
                raise HomeAssistantError("A display supports at most 10 status sources")
            feeds[source] = (clean(call.data["message"]), time.monotonic() + call.data["ttl"], call.data.get("color"))

    hass.services.async_register(DOMAIN, "publish_status", publish, schema=vol.Schema({
        vol.Required("entry_id"): str,
        vol.Required("source"): vol.All(str, vol.Length(min=1, max=40)),
        vol.Required("message"): vol.All(str, vol.Length(max=500)),
        vol.Optional("ttl", default=120): vol.All(vol.Coerce(int), vol.Range(min=10, max=900)),
        vol.Optional("color"): vol.In(["green", "amber", "red"]),
    }))


def status_pages(hass, entry_id, settings):
    feeds = hass.data.get(f"{DOMAIN}_status_feeds", {}).get(entry_id, {})
    now = time.monotonic()
    for source in list(feeds):
        if feeds[source][1] <= now:
            feeds.pop(source)
    return paginate([(item[0], item[2] or settings["color"]) for item in feeds.values()], settings["rows"], settings["columns"])


def records(hass, entry_id):
    feeds = hass.data.get(f"{DOMAIN}_status_feeds", {}).get(entry_id, {})
    now = time.monotonic()
    for source in list(feeds):
        if feeds[source][1] <= now:
            feeds.pop(source)
    return [{"id": source, "fields": {"status_text": value[0]}, "color": value[2]} for source, value in feeds.items()]
