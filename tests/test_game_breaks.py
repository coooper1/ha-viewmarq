from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from custom_components.viewmarq.game_breaks import break_kind, track_breaks
from custom_components.viewmarq.sports_data import live_games
from custom_components.viewmarq.builder import compose, new_page
from custom_components.viewmarq.const import DEFAULTS


class GameBreakTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 9, 1, 30, tzinfo=timezone.utc)
        self.event = {"id": "game", "status": {"period": 2, "clock": 0, "type": {"state": "in", "name": "STATUS_IN_PROGRESS"}}, "competitions": [{"competitors": [{"team": {"id": "6", "abbreviation": "DAL"}, "score": "7"}, {"team": {"id": "27", "abbreviation": "TB"}, "score": "7"}]}]}
        self.data = {"events": [self.event]}
        self.teams = [{"league": "NFL", "id": "6"}]
        self.settings = deepcopy(DEFAULTS)
        self.settings.update(sports_mode="only", sports_breaks=True, pages=[new_page("clock", "clock"), new_page("sports", "score"), new_page("football", "downs"), new_page("halftime", "half")])

    def render(self, games, now=None):
        return compose(self.settings, "MD4-0224", lambda _: None, now or self.now, games)

    def test_explicit_break_only_and_halftime_transition(self):
        stamp = self.now.timestamp()
        tracking = track_breaks(self.data, {}, stamp - 5)
        games = live_games(self.data, self.teams, "NFL", breaks=tracking)
        self.assertEqual(break_kind(self.event["status"]), "")
        self.assertEqual({f.page_id for f in self.render(games)}, {"score", "downs"})
        self.event["status"]["type"]["name"] = "STATUS_HALFTIME"
        tracking = track_breaks(self.data, tracking, stamp)
        games = live_games(self.data, self.teams, "NFL", breaks=tracking)
        frames = self.render(games)
        self.assertEqual({f.page_id for f in frames}, {"clock", "half"})
        self.assertIn("Est. return 13:00", frames[-1].text)
        self.assertIn("12:59", self.render(games, self.now + timedelta(seconds=1))[-1].text)
        self.assertIn("Awaiting live play", self.render(games, self.now + timedelta(minutes=14))[-1].text)
        self.assertEqual(track_breaks(self.data, tracking, stamp + 5)["game"]["started"], stamp)
        self.event["status"]["type"]["name"] = "STATUS_IN_PROGRESS"
        self.event["status"]["period"] = 3
        tracking = track_breaks(self.data, tracking, stamp + 780)
        self.assertIsNone(tracking["game"]["started"])
        games = live_games(self.data, self.teams, "NFL", breaks=tracking)
        self.assertEqual({f.page_id for f in self.render(games)}, {"score", "downs"})

    def test_mid_halftime_connection_and_stale_transition_have_no_timer(self):
        stamp = self.now.timestamp()
        self.event["status"]["type"]["name"] = "STATUS_HALFTIME"
        for previous in ({}, {"game": {"kind": "", "seen": stamp - 90}}):
            tracking = track_breaks(self.data, previous, stamp)
            games = live_games(self.data, self.teams, "NFL", breaks=tracking)
            self.assertIsNone(tracking["game"]["started"])
            self.assertIn("Return time unknown", self.render(games)[-1].text)

    def test_quarter_break_and_other_game_still_live(self):
        self.event["status"].update(period=1)
        self.event["status"]["type"]["name"] = "STATUS_END_PERIOD"
        games = live_games(self.data, self.teams, "NFL")
        self.assertEqual([f.page_id for f in self.render(games)], ["clock"])
        active = deepcopy(games[0]); active.update(id="other", break_kind="")
        self.assertEqual({f.page_id for f in self.render([*games, active])}, {"score", "downs"})
        self.settings["sports_breaks"] = False
        self.assertEqual({f.page_id for f in self.render(games)}, {"score", "downs"})
        self.event["status"]["type"].update(name="STATUS_IN_PROGRESS")
        self.assertEqual(break_kind(self.event["status"]), "")
        self.event["status"]["type"].update(name="STATUS_END_PERIOD", state="post", completed=True)
        self.assertEqual(break_kind(self.event["status"]), "")
