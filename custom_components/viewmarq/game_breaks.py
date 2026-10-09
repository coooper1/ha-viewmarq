"""Explicit football break status and observed halftime transitions."""


def break_kind(status):
    kind = status.get("type", {})
    if kind.get("state") != "in" or kind.get("completed"):
        return ""
    if kind.get("name") == "STATUS_HALFTIME":
        return "halftime"
    if kind.get("name") == "STATUS_END_PERIOD" and status.get("period") in (1, 2, 3):
        return "quarter"
    return ""


def track_breaks(data, previous, now):
    """Never start a full timer when first connecting during an existing halftime."""
    result = {}
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            status = competition.get("status") or event.get("status", {})
            key = str(event.get("id", ""))
            kind = break_kind(status)
            old = previous.get(key, {})
            started = None
            if kind == "halftime":
                if old.get("kind") == "halftime":
                    started = old.get("started")
                elif old and now - old.get("seen", 0) <= 30:
                    started = now
            result[key] = {"kind": kind, "started": started, "seen": now}
    return result
