"""Normalize actual ESPN game fields without substituting season averages."""
from .content import clean
from datetime import datetime, timezone
from .game_breaks import break_kind

BREAK_FIELDS = {"break_label": "Halftime: team", "break_countdown": "Halftime: estimated return countdown"}

COUNTDOWN_FIELDS = {"game_matchup": "Pregame: teams", "game_countdown": "Pregame: time until start", "game_broadcast": "Pregame: broadcaster"}


def upcoming_games(data, teams, league, now=None):
    """Actual scheduled games within two hours; never infer that kickoff occurred."""
    now = now or datetime.now(timezone.utc)
    selected = {str(t["id"]) for t in teams if t["league"] == league}
    records = []
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            status = (competition.get("status") or event.get("status", {})).get("type", {})
            if status.get("state") != "pre" or status.get("name") != "STATUS_SCHEDULED":
                continue
            try:
                start = datetime.fromisoformat(competition.get("date", event.get("date", "")).replace("Z", "+00:00"))
                if start.tzinfo is None:
                    continue
                remaining = (start - now).total_seconds()
            except (ValueError, TypeError, AttributeError):
                continue
            if not -900 <= remaining <= 7200:
                continue
            competitors = competition.get("competitors", [])
            if len(competitors) != 2:
                continue
            channels = []
            for broadcast in competition.get("broadcasts", []):
                for channel in broadcast.get("names", []):
                    if isinstance(channel, str) and channel not in channels:
                        channels.append(channel)
            for team in competitors:
                identity = str(team.get("team", {}).get("id"))
                if identity not in selected:
                    continue
                opponent = next(c for c in competitors if c is not team)
                ours = clean(team.get("team", {}).get("abbreviation", ""))
                theirs = clean(opponent.get("team", {}).get("abbreviation", ""))
                if not ours or not theirs:
                    continue
                records.append({"id": f"pregame:{league}:{event.get('id')}:{identity}",
                                "state": "pre", "team_key": f"{league}:{identity}", "league": league,
                                "start": start.isoformat(), "fields": {"game_matchup": f"{ours} vs {theirs}", "game_broadcast": clean("/".join(channels)) or "TV TBD"}})
    return records

SPORT_FIELDS = {
    "match_score": "Selected team and opponent scores",
    "team_abbr": "Selected team abbreviation", "team_name": "Selected team name",
    "team_score": "Selected team score", "opponent_abbr": "Opponent abbreviation",
    "opponent_name": "Opponent name", "opponent_score": "Opponent score",
    "home_abbr": "Home team abbreviation", "home_name": "Home team name",
    "home_score": "Home score", "away_abbr": "Away team abbreviation",
    "away_name": "Away team name", "away_score": "Away score",
    "game_clock": "Game clock", "game_period": "Game period / quarter",
    "game_status": "Game status", "league": "League",
    "down_distance": "Football: down and distance", "yard_line": "Football: ball position",
    "possession": "Team in possession",
    "football_play": "Football: possession, down and yards",
    "team_total_yards": "Football: selected team's total yards",
    "opponent_total_yards": "Football: opponent's total yards",
    "team_passing_yards": "Football: selected team's passing yards",
    "opponent_passing_yards": "Football: opponent's passing yards",
    "team_rushing_yards": "Football: selected team's rushing yards",
    "opponent_rushing_yards": "Football: opponent's rushing yards",
    "team_first_downs": "Football: selected team's first downs",
    "opponent_first_downs": "Football: opponent's first downs",
    "team_rebounds": "Basketball: selected team's rebounds",
    "opponent_rebounds": "Basketball: opponent's rebounds",
    "team_assists": "Basketball: selected team's assists",
    "opponent_assists": "Basketball: opponent's assists",
    "team_field_goal_pct": "Basketball: selected team's field goal %",
    "opponent_field_goal_pct": "Basketball: opponent's field goal %",
    "team_turnovers": "Selected team's turnovers", "opponent_turnovers": "Opponent's turnovers",
}
STAT_KEYS = {
    "total_yards": "totalYards", "passing_yards": "netPassingYards",
    "rushing_yards": "rushingYards", "first_downs": "firstDowns",
    "rebounds": "totalRebounds", "assists": "assists",
    "field_goal_pct": "fieldGoalPct", "turnovers": "turnovers",
}
SUMMARY_FIELDS = {f"{side}_{key}" for side in ("team", "opponent") for key in STAT_KEYS}


def live_games(data, teams, league, summaries=None, breaks=None):
    """One record for each selected team's actual in-progress competition."""
    selected = {str(team["id"]) for team in teams if team["league"] == league}
    records = []
    for event in data.get("events", []):
        for competition in event.get("competitions", []):
            status = competition.get("status") or event.get("status", {})
            if status.get("type", {}).get("state") != "in" or status.get("type", {}).get("completed"):
                continue
            competitors = competition.get("competitors", [])
            if len(competitors) != 2 or any(c.get("score") is None or not str(c["score"]).isdigit() for c in competitors):
                continue
            for team in competitors:
                if str(team.get("team", {}).get("id")) not in selected:
                    continue
                opponent = next(c for c in competitors if c is not team)
                fields = {key: "" for key in SPORT_FIELDS}
                fields["league"] = league
                for prefix, competitor in [("team", team), ("opponent", opponent), *[(c.get("homeAway"), c) for c in competitors]]:
                    if prefix not in ("team", "opponent", "home", "away"):
                        continue
                    details = competitor.get("team", {})
                    fields[f"{prefix}_abbr"] = clean(details.get("abbreviation", ""))
                    fields[f"{prefix}_name"] = clean(details.get("displayName", ""))
                    fields[f"{prefix}_score"] = str(competitor["score"])
                fields["match_score"] = f"{fields['team_abbr']} {fields['team_score']} - {fields['opponent_abbr']} {fields['opponent_score']}"
                fields["game_clock"] = clean(status.get("displayClock") or "")
                period = status.get("period")
                if period is not None:
                    prefix = "Q" if league in ("NFL", "NCAAF", "NBA", "WNBA") else "P" if league == "NHL" else "Period "
                    fields["game_period"] = prefix + str(period)
                fields["game_status"] = clean(status.get("type", {}).get("shortDetail") or status.get("type", {}).get("description") or "Live")
                situation = competition.get("situation", {})
                if league in ("NFL", "NCAAF"):
                    fields["down_distance"] = clean(situation.get("downDistanceText") or situation.get("shortDownDistanceText") or "")
                    yard_line = situation.get("possessionText")
                    if yard_line:
                        fields["yard_line"] = clean(yard_line)
                    elif situation.get("yardLine") is not None:
                        fields["yard_line"] = str(situation["yardLine"])
                possession = str(situation.get("possession", ""))
                fields["possession"] = next((clean(c.get("team", {}).get("abbreviation", "")) for c in competitors if str(c.get("team", {}).get("id")) == possession), "")
                fields["possession_side"] = "team" if possession == str(team.get("team", {}).get("id")) else "opponent" if possession == str(opponent.get("team", {}).get("id")) else ""
                if league in ("NFL", "NCAAF"):
                    fields["football_play"] = f"{fields['possession'] or '?'} {fields['down_distance'] or '--'} @ {fields['yard_line'] or '--'}"
                summary = (summaries or {}).get(str(event["id"]), {})
                # Exact game-stat names only. Never treat yardsPerGame or season averages as game totals.
                for side, competitor in (("team", team), ("opponent", opponent)):
                    stats = next((t.get("statistics", []) for t in summary.get("boxscore", {}).get("teams", []) if str(t.get("team", {}).get("id")) == str(competitor.get("team", {}).get("id"))), [])
                    values = {s.get("name"): s.get("displayValue") for s in stats}
                    for key, source in STAT_KEYS.items():
                        if key in ("total_yards", "passing_yards", "rushing_yards", "first_downs") and league not in ("NFL", "NCAAF"):
                            continue
                        if key in ("rebounds", "assists", "field_goal_pct") and league not in ("NBA", "WNBA"):
                            continue
                        value = values.get(source)
                        if value is not None and str(value).strip() not in ("", "--", "-"):
                            fields[f"{side}_{key}"] = clean(value) + ("%" if key == "field_goal_pct" else "")
                fields["break_label"] = f"{fields['team_abbr']} Halftime"
                records.append({"id": f"{league}:{event['id']}:{team['team']['id']}", "event_id": str(event["id"]), "league": league, "team_key": f"{league}:{team['team']['id']}", "fields": fields,
                                "break_kind": break_kind(status) if league in ("NFL", "NCAAF") else "",
                                "break_started": (breaks or {}).get(str(event["id"]), {}).get("started")})
    return records
