"""Shared ESPN scoreboard cache. Network work never blocks sign updates."""
import asyncio
import time

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .content import clean, paginate
from .sports_data import live_games, upcoming_games, SUMMARY_FIELDS
from .builder import effective_pages
from .game_breaks import track_breaks

LEAGUES = {
    "NCAAF": ("College football", "football/college-football"),
    "NFL": ("NFL football", "football/nfl"),
    "NBA": ("NBA basketball", "basketball/nba"),
    "WNBA": ("WNBA basketball", "basketball/wnba"),
    "MLB": ("MLB baseball", "baseball/mlb"),
    "NHL": ("NHL hockey", "hockey/nhl"),
    "MLS": ("MLS soccer", "soccer/usa.1"),
    "EPL": ("Premier League soccer", "soccer/eng.1"),
}
FAVORITES = [
    {"league": "NCAAF", "id": "201", "name": "Oklahoma Sooners"},
    {"league": "NFL", "id": "6", "name": "Dallas Cowboys"},
]
BASE = "https://site.api.espn.com/apis/site/v2/sports/"
LIVE_REFRESH_SECONDS = 5


async def team_choices(hass, league):
    """ESPN supplies friendly team names for the selected league."""
    async with async_get_clientsession(hass).get(
        BASE + LEAGUES[league][1] + "/teams", params={"limit": 1000},
        timeout=aiohttp.ClientTimeout(total=10),
    ) as response:
        response.raise_for_status()
        data = await response.json()
    teams = {}
    for sport in data.get("sports", []):
        for item in sport.get("leagues", []):
            for entry in item.get("teams", []):
                team = entry["team"]
                teams[str(team["id"])] = team["displayName"]
    if not teams:
        raise ValueError("ESPN returned no teams")
    return [{"value": key, "label": name} for key, name in sorted(teams.items(), key=lambda x: x[1])]


def live_pages(data, teams, color, rows, columns):
    """Use only actual in-progress competitions with both scores present."""
    selected = {str(team["id"]) for team in teams}
    output = []
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            status = competition.get("status") or event.get("status", {})
            if status.get("type", {}).get("state") != "in" or status.get("type", {}).get("completed"):
                continue
            competitors = competition.get("competitors", [])
            if len(competitors) != 2 or not any(str(c.get("team", {}).get("id")) in selected for c in competitors):
                continue
            if any(c.get("score") is None or not str(c["score"]).isdigit() for c in competitors):
                continue
            names = [c.get("team", {}).get("abbreviation") for c in competitors]
            if not all(names):
                continue
            score = f"{names[0]} {competitors[0]['score']} - {names[1]} {competitors[1]['score']}"
            detail = status.get("type", {}).get("shortDetail") or status.get("displayClock", "Live")
            output.append((clean(score + "\n" + detail), color))
    return paginate(output, rows, columns)


class ESPNCache:
    def __init__(self, hass):
        self.hass = hass
        self.feeds = {}
        self.limit = asyncio.Semaphore(2)
        self.summaries = {}

    def games(self, settings):
        # Reuse league cache refresh and freshness policy across every display.
        _, statuses = self.pages(settings)
        now = time.monotonic()
        needs_summary = any(p.get("enabled", True) and any(f["source"] in SUMMARY_FIELDS for f in p["fields"]) for p in effective_pages(settings))
        games = []
        for league, feed in self.feeds.items():
            if not feed["updated"] or now - feed["updated"] > settings["sports_max_age"] * 60:
                continue
            summaries = {event: item["data"] for (sport, event), item in self.summaries.items() if sport == league and now - item["updated"] <= settings["sports_max_age"] * 60}
            current = live_games(feed["data"], settings.get("teams", []), league, summaries, feed.get("breaks"))
            games.extend(current)
            games.extend(upcoming_games(feed["data"], settings.get("teams", []), league))
            if needs_summary:
                for game in current:
                    key = (league, game["event_id"])
                    if key not in self.summaries and len(self.summaries) >= 200:
                        continue
                    item = self.summaries.setdefault(key, {"data": {}, "updated": 0, "next": 0, "used": now, "task": None, "failures": 0})
                    item["used"] = now
                    if now >= item["next"] and (item["task"] is None or item["task"].done()):
                        item["task"] = self.hass.async_create_task(self.refresh_summary(key, item))
        for key, item in list(self.summaries.items()):
            if now - item["used"] > 600 and (item["task"] is None or item["task"].done()):
                del self.summaries[key]
        return games, statuses

    async def refresh_summary(self, key, item):
        try:
            async with self.limit:
                async with async_get_clientsession(self.hass).get(BASE + LEAGUES[key[0]][1] + "/summary", params={"event": key[1]}, timeout=aiohttp.ClientTimeout(total=8)) as response:
                    response.raise_for_status()
                    data = await response.json()
                if not isinstance(data, dict):
                    raise ValueError("Invalid ESPN summary")
                item.update(data=data, updated=time.monotonic(), next=time.monotonic() + LIVE_REFRESH_SECONDS, failures=0)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            item["failures"] += 1
            item["next"] = time.monotonic() + min(300, 30 * 2 ** min(item["failures"] - 1, 4))

    def pages(self, settings):
        pages_out, statuses = [], {}
        teams = settings.get("teams", [])
        for league in dict.fromkeys(t["league"] for t in teams):
            if league not in LEAGUES:
                continue
            feed = self.feeds.setdefault(league, {"data": {}, "updated": 0, "next": 0, "failures": 0, "task": None, "status": "Loading"})
            now = time.monotonic()
            if now >= feed["next"] and (feed["task"] is None or feed["task"].done()):
                feed["task"] = self.hass.async_create_task(self.refresh(league, feed))
            fresh = feed["updated"] and now - feed["updated"] <= settings["sports_max_age"] * 60
            statuses[league] = feed["status"] if fresh else ("Loading" if not feed["updated"] and not feed["failures"] else "Unavailable or stale; hidden")
            if fresh:
                pages_out.extend(live_pages(feed["data"], [t for t in teams if t["league"] == league], settings["sports_color"], settings["rows"], settings["columns"]))
        return pages_out, statuses

    async def refresh(self, league, feed):
        try:
            async with self.limit:
                params = {"limit": 1000}
                if league == "NCAAF":
                    params["groups"] = "80"  # All FBS, including unranked games.
                async with async_get_clientsession(self.hass).get(
                    BASE + LEAGUES[league][1] + "/scoreboard", params=params,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                if not isinstance(data, dict) or not isinstance(data.get("events"), list):
                    raise ValueError("Invalid ESPN scoreboard")
                feed["breaks"] = track_breaks(data, feed.get("breaks", {}), time.time())
                feed.update(data=data, updated=time.monotonic(), failures=0, status="Current")
                live = any(e.get("status", {}).get("type", {}).get("state") == "in" for e in data["events"])
                scheduled_teams = [{"league": league, "id": c.get("team", {}).get("id")} for e in data["events"] for competition in e.get("competitions", []) for c in competition.get("competitors", [])]
                live = live or bool(upcoming_games(data, scheduled_teams, league))
                feed["next"] = time.monotonic() + (LIVE_REFRESH_SECONDS if live else 120)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            feed["failures"] += 1
            feed["status"] = "ESPN unavailable; cached scores expire automatically"
            feed["next"] = time.monotonic() + min(300, 30 * 2 ** min(feed["failures"] - 1, 4))
