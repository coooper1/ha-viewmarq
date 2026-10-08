"""Weather readings and actual, unexpired NWS alerts. No synthetic live data."""
from datetime import datetime
import math

from .content import clean, usable

WEATHER_FIELDS = {
    "temperature_f": "Weather temperature (Fahrenheit)",
    "rain_chance": "Weather rain chance (next forecast hour)",
    "uv_index": "Weather UV index",
    "heat_index": "Weather heat index (Fahrenheit)",
    "feels_like": "Weather feels-like (Fahrenheit)",
}


def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def fahrenheit(value, unit):
    value = number(value)
    if value is None or unit not in ("°F", "F", "°C", "C"):
        return None
    return value * 9 / 5 + 32 if unit in ("°C", "C") else value


def estimated_temperature(source, attrs):
    """NWS heat-index / wind-chill estimates, explicitly labeled by reading()."""
    t = fahrenheit(attrs.get("temperature"), attrs.get("temperature_unit"))
    if t is None:
        return None
    if t >= 80:
        rh = number(attrs.get("humidity"))
        if rh is None or not 0 <= rh <= 100 or t > 112:
            return None
        simple = .5 * (t + 61 + (t - 68) * 1.2 + rh * .094)
        if (simple + t) / 2 < 80:
            return simple
        hi = (-42.379 + 2.04901523*t + 10.14333127*rh - .22475541*t*rh
              - .00683783*t*t - .05481717*rh*rh + .00122874*t*t*rh
              + .00085282*t*rh*rh - .00000199*t*t*rh*rh)
        if rh < 13:
            hi -= (13-rh)/4 * math.sqrt((17-abs(t-95))/17)
        elif rh > 85 and t <= 87:
            hi += (rh-85)/10 * (87-t)/5
        return hi
    if source == "heat_index":
        return None
    if t <= 50:
        wind = number(attrs.get("wind_speed"))
        factor = {"mph": 1, "km/h": .621371, "m/s": 2.23694, "kn": 1.15078}.get(attrs.get("wind_speed_unit"))
        if wind is None or wind < 0 or factor is None:
            return None
        wind *= factor
        if wind > 3:
            return 35.74 + .6215*t - 35.75*wind**.16 + .4275*t*wind**.16
    return t


def reading(source, weather, override=None):
    if override is not None:
        if not usable(override):
            return "Unavailable"
        attrs, value = override.attributes, override.state
        unit = attrs.get("unit_of_measurement", "")
    else:
        if not usable(weather):
            return "Unavailable"
        attrs = weather.attributes
        key = {"temperature_f": "temperature", "rain_chance": "precipitation_probability",
               "uv_index": "uv_index", "heat_index": "heat_index", "feels_like": "apparent_temperature"}[source]
        value = attrs.get(key)
        if source == "rain_chance" and value is None:
            value = attrs.get("_viewmarq_forecast", {}).get(key)
        unit = attrs.get("temperature_unit", "")
        if value is None and source in ("heat_index", "feels_like"):
            estimate = estimated_temperature(source, attrs)
            return f"{estimate:.0f}°F est." if estimate is not None else "Unavailable"
    if source in ("temperature_f", "heat_index", "feels_like"):
        value = fahrenheit(value, unit)
        return f"{value:.0f}°F" if value is not None else "Unavailable"
    value = number(value)
    if value is None or value < 0 or (source == "rain_chance" and value > 100):
        return "Unavailable"
    if source == "rain_chance":
        return f"{value:g}%"
    level = "Low" if value < 3 else "Moderate" if value < 6 else "High" if value < 8 else "Very high" if value < 11 else "Extreme"
    return f"{value:g} {level}"


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def nws_alerts(state, now):
    """Return current actual alerts only, with warnings ordered first."""
    if not usable(state):
        return [], "NWS alerts unavailable"
    alerts = state.attributes.get("Alerts")
    if not isinstance(alerts, list):
        return [], "NWS alert data unavailable"
    result, malformed = [], False
    for alert in alerts:
        if not isinstance(alert, dict) or str(alert.get("Status", "")).lower() != "actual":
            continue
        if str(alert.get("MessageType", "")).lower() == "cancel":
            continue
        expiry = timestamp(alert.get("Expires"))
        ends = timestamp(alert.get("Ends"))
        if expiry is None:
            malformed = True
            continue
        if expiry <= now or (ends is not None and ends <= now):
            continue
        event = clean(alert.get("Event", ""))
        if not event:
            continue
        warning = "warning" in event.lower()
        until = (min(expiry, ends) if ends else expiry).astimezone(now.tzinfo).strftime("%I:%M %p").lstrip("0")
        result.append({"text": f"{event}\nUntil {until}", "warning": warning,
                       "fields": {"nws_event": event, "nws_until": f"Until {until}",
                                  "nws_area": clean(alert.get("AreasAffected") or ""),
                                  "nws_headline": clean(alert.get("Headline") or ""),
                                  "nws_instruction": clean(alert.get("Instruction") or ""),
                                  "nws_severity": clean(alert.get("Severity") or "")},
                       "priority": 0 if "tornado warning" in event.lower() else 1 if warning else 2})
    result.sort(key=lambda x: x["priority"])
    return result, "NWS alert data unavailable" if malformed else "NWS: no active alerts" if not result else f"NWS: {len(result)} active alerts"
