"""Behavioral tests for persistent layouts, rotation, alerts and live metadata."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
import unittest

from custom_components.viewmarq.builder import (Frame, Player, compose, effective_pages,
    field, new_page, render_pages, validate_pages, live_game_preview, sample_frames)
from custom_components.viewmarq.const import DEFAULTS
from custom_components.viewmarq.sports_data import live_games, upcoming_games
from custom_components.viewmarq.protocol import page_message, layout

NOW = datetime(2026, 10, 8, 14, 3)
MODEL = "MD4-0224"


def state(value, **attrs):
    return SimpleNamespace(state=value, attributes=attrs)


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.settings = deepcopy(DEFAULTS)
        self.states = {}

    def render(self, games=()):
        return compose(self.settings, MODEL, self.states.get, NOW, games)

    def test_pregame_window_transition_and_restore(self):
        now = datetime(2026, 10, 8, 22, 15, tzinfo=timezone.utc)
        event = {"id": "123", "date": (now + timedelta(hours=2)).isoformat(),
                 "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}},
                 "competitions": [{"competitors": [{"team": {"id": "6", "abbreviation": "DAL"}, "score": "0"}, {"team": {"id": "27", "abbreviation": "TB"}, "score": "0"}]}]}
        data = {"events": [event]}
        teams = [{"league": "NFL", "id": "6"}]
        upcoming = upcoming_games(data, teams, "NFL", now)
        self.assertEqual(len(upcoming), 1)
        self.assertEqual(upcoming_games(data, teams, "NFL", now - timedelta(seconds=1)), [])
        countdown = new_page("pregame", "countdown")
        self.settings.update(pages=[new_page("clock", "clock"), new_page("sports", "score"), countdown], sports_mode="only")
        validate_pages(self.settings["pages"], self.settings, MODEL)
        render = lambda games, at=now: compose(self.settings, MODEL, self.states.get, at, games)
        frames = render(upcoming)
        self.assertEqual([f.page_id for f in frames], ["clock", "countdown"])
        frames = frames[1:]
        self.assertIn("DAL vs TB", frames[0].text)
        self.assertIn("Starts in 2:00:00", frames[0].text)
        self.assertIn("1:59:59", render(upcoming, now + timedelta(seconds=1))[-1].text)
        self.assertEqual([f.page_id for f in render(upcoming, now + timedelta(minutes=105))], ["countdown"])
        self.assertEqual([f.page_id for f in render(upcoming, now + timedelta(minutes=104, seconds=59))], ["clock", "countdown"])
        self.assertIn("TV TBD", frames[0].text)
        self.assertIn("Awaiting start", render(upcoming, now + timedelta(hours=2))[0].text)
        event["status"]["type"].update(state="in", name="STATUS_IN_PROGRESS")
        live = live_games(data, teams, "NFL")
        self.assertEqual(upcoming_games(data, teams, "NFL", now), [])
        self.assertEqual([f.page_id for f in render(live)], ["score"])
        self.assertEqual([f.page_id for f in render([])], ["clock"])
        countdown["teams"] = ["NFL:99"]
        self.assertEqual([f.page_id for f in render(upcoming)], ["clock"])

    def test_pregame_invalid_and_delayed_events(self):
        now = datetime(2026, 10, 8, 22, 15, tzinfo=timezone.utc)
        event = {"id": "123", "date": now.isoformat(), "status": {"type": {"state": "pre", "name": "STATUS_SCHEDULED"}}, "competitions": [{"competitors": [{"team": {"id": "6", "abbreviation": "DAL"}}, {"team": {"id": "27", "abbreviation": "TB"}}]}]}
        data, teams = {"events": [event]}, [{"league": "NFL", "id": "6"}]
        self.assertEqual(upcoming_games(data, teams, "NFL", now + timedelta(minutes=16)), [])
        for status in ("STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_DELAYED"):
            event["status"]["type"]["name"] = status
            self.assertEqual(upcoming_games(data, teams, "NFL", now), [])
        event["status"]["type"]["name"] = "STATUS_SCHEDULED"
        for date in ("bad", None, "2026-10-08T22:15:00"):
            event["date"] = date
            self.assertEqual(upcoming_games(data, teams, "NFL", now), [])

    def test_migration_preserves_options_and_restart(self):
        self.settings.update(quick_message="Hello", messages="One\nTwo", weather_entity="weather.home", date_style="full-date", teams=[{"league":"NBA","id":"25","name":"Thunder"}], binary_sensors=["binary_sensor.door"])
        before = deepcopy(self.settings)
        pages = effective_pages(self.settings)
        self.assertEqual(self.settings, before)
        self.assertEqual([p["type"] for p in pages], ["text", "text", "text", "clock", "weather", "sports", "status"])
        stored = json.loads(json.dumps({**self.settings, "pages": validate_pages(pages, self.settings, MODEL)}))
        self.assertEqual(effective_pages(stored), pages)
        self.assertEqual(stored["teams"], before["teams"])
        self.assertEqual(stored["binary_sensors"], before["binary_sensors"])
        self.assertEqual(next(p for p in pages if p["type"] == "clock")["date_style"], "full-date")

    def test_add_duplicate_delete_reorder_persistence(self):
        pages = [new_page("text", "a"), new_page("clock", "b")]
        copy = deepcopy(pages[0]); copy["id"] = "c"; copy["fields"][0]["text"] = "Copy"
        pages.append(copy)
        pages = [pages[2], pages[0], pages[1]]
        pages.pop(1)
        pages[1]["enabled"] = False
        self.settings["pages"] = json.loads(json.dumps(validate_pages(pages, self.settings, MODEL)))
        self.assertEqual([p["id"] for p in effective_pages(self.settings)], ["c", "b"])
        self.assertEqual([f.page_id for f in self.render()], ["c"])
        self.settings["pages"] = []
        self.assertEqual(effective_pages(self.settings), [])
        self.assertEqual(self.render()[0].text, " ")

    def test_invalid_duplicate_id_and_overlap_rejected(self):
        p = new_page("clock", "a")
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_pages([p, p], self.settings, MODEL)
        p["fields"][1]["row"] = 0
        with self.assertRaisesRegex(ValueError, "overlap"):
            validate_pages([p], self.settings, MODEL)
        self.assertEqual(validate_pages([p], self.settings, MODEL, allow_overlap=True), [p])

    def test_grid_and_continuation_preserve_alignment(self):
        p = new_page("custom", "grid")
        p["fields"] = [dict(field("text", text="LEFT"), width=12, align="left"), dict(field("text", text="RIGHT"), column=12, width=12, align="right"), field("text", 1, "Second row"), field("text", 2, "Next frame")]
        self.settings["pages"] = validate_pages([p], self.settings, MODEL)
        frames = self.render()
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0].text.splitlines()[0], "LEFT               RIGHT")
        self.assertIn("Next frame", frames[1].text)
        self.assertEqual(frames[1].as_dict(MODEL)["start_row"], 2)
        for f in frames:
            self.assertLessEqual(len(page_message(f.text, 1, MODEL, f.color, f.font, f.alignment)), 246)

    def test_large_font_uses_one_line_and_multiple_frames(self):
        p = new_page("clock", "clock"); p["font"] = "large"
        self.settings["pages"] = validate_pages([p], self.settings, MODEL)
        self.assertGreaterEqual(len(self.render()), 2)
        self.assertTrue(all(layout(MODEL, f.font)["rows"] == 1 for f in self.render()))

    def test_live_updates_do_not_reset_dwell(self):
        player = Player()
        a, b = Frame("a", "1:00", "green", dwell=5), Frame("b", "B", "green", dwell=7)
        self.assertEqual(player.choose([a,b], 0).key, "a")
        self.assertEqual(player.choose([replace(a,text="1:01"),b], 4).key, "a")
        self.assertEqual(player.choose([a,b], 5).key, "b")
        self.assertEqual(player.choose([a,b], 11).key, "b")
        self.assertEqual(player.choose([a,b], 12).key, "a")
        self.assertEqual(player.choose([b], 13).key, "b")

    def test_unknown_binary_never_alerts_and_connectivity_inverts(self):
        self.settings["binary_sensors"] = ["binary_sensor.link"]
        self.states["binary_sensor.link"] = state("unknown", device_class="connectivity", friendly_name="Link")
        self.assertTrue(all("alert" not in f.kind.lower() for f in self.render()))
        self.states["binary_sensor.link"].state = "off"
        self.assertTrue(any("disconnected" in f.text for f in self.render()))

    def test_door_preserves_clock_date_and_clears(self):
        self.settings["binary_sensors"] = ["binary_sensor.door"]
        self.states["binary_sensor.door"] = state("on", device_class="door", friendly_name="Front door")
        frames = self.render()
        self.assertTrue(any("2:03 PM" in f.text for f in frames))
        self.assertTrue(any("2026" in f.text for f in frames))
        self.assertTrue(all(f.color == ("green", "red") for f in frames))
        self.states["binary_sensor.door"].state = "off"
        self.assertTrue(all("Front door" not in f.text for f in self.render()))
        self.assertEqual(len(self.render()), 1)

    def test_urgent_override_then_restore(self):
        self.settings["binary_sensors"] = ["binary_sensor.smoke"]
        self.states["binary_sensor.smoke"] = state("on", device_class="smoke", friendly_name="Smoke")
        self.assertTrue(all(f.kind == "Priority alert" and f.color == "red" for f in self.render()))
        self.states["binary_sensor.smoke"].state = "off"
        self.assertIn("2:03 PM", self.render()[0].text)

    def test_sports_policies_and_colors(self):
        games = [{"id":"game","team_key":"NFL:6","fields":{"match_score":"DAL 7 - TB 0", "game_status":"Q1 02:00"}}]
        frames = self.render(games)
        self.assertEqual({f.color for f in frames}, {"green", "amber"})
        self.settings["sports_mode"] = "only"
        self.assertTrue(all(f.kind == "sports" for f in self.render(games)))
        self.assertTrue(any(f.kind == "clock" for f in self.render()))
        self.settings["sports_mode"] = "hide_clock"
        self.assertFalse(any(f.kind == "clock" for f in self.render(games)))

    def test_game_preview_does_not_need_current_rotation_or_fake_scores(self):
        self.settings["pages"] = [new_page("clock", "clock")]
        original = deepcopy(self.settings)
        self.assertEqual(live_game_preview(self.settings, MODEL, self.states.get, NOW, []), [])
        games = [{"id":"actual","team_key":"NFL:6","fields":{"match_score":"DAL 0 - TB 7", "game_status":"Q2 04:32"}}]
        frames = live_game_preview(self.settings, MODEL, self.states.get, NOW, games)
        self.assertIn("DAL 0 - TB 7", frames[0].text)
        self.assertEqual(self.settings, original)
        self.assertTrue(all(f.kind == "sports" for f in frames))

    def test_game_layout_sample_is_explicit_and_never_added_to_rotation(self):
        page = new_page("sports", "sports")
        self.settings["pages"] = [page]
        samples = sample_frames(page, self.settings, MODEL, self.states.get, NOW)
        self.assertTrue(samples and all("SAMPLE" in f.kind for f in samples))
        self.assertEqual(self.render()[0].key, "blank")
        page["fields"] = [{**field("team_first_downs", 0), "label": "1st: "}, {**field("opponent_first_downs", 1), "label": "Opp: "}]
        samples = sample_frames(page, self.settings, MODEL, self.states.get, NOW)
        self.assertIn("1st: 14", samples[0].text)
        self.assertIn("Opp: 11", samples[0].text)

    def test_shared_row_alignments_and_neighbor_columns(self):
        page = new_page("custom", "shared")
        page["fields"] = [{**field("text", text=text), "align": align}
                          for text, align in (("LEFT", "left"), ("MID", "center"), ("RIGHT", "right"))]
        page["fields"].append(field("text", 1, "Underneath"))
        original = deepcopy(page)
        validate_pages([page], self.settings, MODEL)
        self.settings["pages"] = [page]
        lines = self.render()[0].text.split("\n")
        self.assertEqual(lines[0], "LEFT      MID      RIGHT")
        self.assertIn("Underneath", lines[1])
        self.assertEqual(page, original)
        page["fields"] = [field("text", text="A"), {**field("text", text="B"), "column": 8}, {**field("text", text="C"), "column": 16}]
        validate_pages([page], self.settings, MODEL)
        line = self.render()[0].text.split("\n")[0]
        self.assertIn("A", line[:8]); self.assertIn("B", line[8:16]); self.assertIn("C", line[16:])
        page["fields"][0]["width"] = 12
        with self.assertRaises(ValueError):
            validate_pages([page], self.settings, MODEL)

    def test_individual_colors_share_row_and_survive_alert_composition(self):
        page = new_page("custom", "colored")
        page["fields"] = [{**field("text", text=text), "align": align, "color": color}
                          for text, align, color in (("LEFT", "left", "red"), ("MID", "center", "amber"), ("RIGHT", "right", "green"))]
        page["fields"].append(field("text", 1, "Underneath"))
        self.settings.update(pages=[page], scroll="left")
        validate_pages([page], self.settings, MODEL)
        frame = self.render()[0]
        self.assertEqual(frame.motion, "static")
        self.assertEqual(frame.color[0], ("red",) * 8 + ("amber",) * 8 + ("green",) * 8)
        payload = page_message(frame.text, 1, MODEL, frame.color, frame.font, frame.alignment)
        for expected in (b"<RED><POS 0 0>", b"<AMB><POS 48 0>", b"<GRN><POS 96 0>"):
            self.assertIn(expected, payload)
        self.assertLessEqual(len(payload), 246)
        self.settings["binary_sensors"] = ["binary_sensor.door"]
        self.states["binary_sensor.door"] = state("on", device_class="door", friendly_name="Front door")
        alert_frame = self.render()[0]
        self.assertEqual(alert_frame.color[0], frame.color[0])
        self.assertEqual(alert_frame.color[-1], self.settings["alert_color"])
        page_message(alert_frame.text, 1, MODEL, alert_frame.color, alert_frame.font, alert_frame.alignment)
        page["fields"][0]["color"] = "blue"
        with self.assertRaises(ValueError):
            validate_pages([page], self.settings, MODEL)

    def test_sonos_metadata_and_idle_visibility(self):
        p = new_page("media", "sonos"); p["entity"] = "media_player.test_speaker"
        self.settings["pages"] = [p]
        self.states[p["entity"]] = state("playing", media_title="Sample tune", media_artist="Sample artist")
        frames = self.render()
        self.assertIn("Sample tune", frames[0].text); self.assertIn("Sample artist", frames[0].text)
        self.states[p["entity"]].state = "idle"
        self.assertEqual(self.render()[0].key, "blank")
        p["hide_idle"] = False
        self.assertEqual(self.render()[0].page_id, "sonos")
        self.states[p["entity"]].state = "unavailable"
        self.assertEqual(self.render()[0].key, "blank")

    def test_conditional_entity_page(self):
        p = new_page("entity", "entity"); p["entity"] = "sensor.temp"
        p["visibility"] = {"mode":"entity_state","entity":"input_select.mode","value":"Work"}
        self.settings["pages"] = [p]
        self.states["sensor.temp"] = state("72", friendly_name="Office", unit_of_measurement="°F")
        self.assertEqual(self.render()[0].key, "blank")
        self.states["input_select.mode"] = state("Work")
        self.assertIn("72°F".replace("72", "72 "), self.render()[0].text)


class SportsTests(unittest.TestCase):
    def setUp(self):
        self.teams = [{"league":"NFL", "id":"6"}]
        self.data = {"events":[{"id":"game", "competitions":[{"status":{"type":{"state":"in", "shortDetail":"Q2 04:32"},"displayClock":"4:32","period":2},"competitors":[{"team":{"id":"6","abbreviation":"DAL","displayName":"Dallas Cowboys"},"homeAway":"home","score":"0"},{"team":{"id":"2","abbreviation":"TB","displayName":"Tampa Bay"},"homeAway":"away","score":"7"}]}]}]}

    def test_missing_stats_blank_zero_scores_real(self):
        f = live_games(self.data,self.teams,"NFL")[0]["fields"]
        self.assertEqual(f["team_score"], "0")
        self.assertEqual(f["team_total_yards"], "")
        self.assertEqual(f["match_score"], "DAL 0 - TB 7")
        self.assertEqual(f["home_abbr"], "DAL")

    def test_game_stats_not_season_averages(self):
        summary = {"game":{"boxscore":{"teams":[{"team":{"id":"6"},"statistics":[{"name":"yardsPerGame","displayValue":"340"},{"name":"totalYards","displayValue":"0"}]}]}}}
        f = live_games(self.data,self.teams,"NFL",summary)[0]["fields"]
        self.assertEqual(f["team_total_yards"], "0")
        summary["game"]["boxscore"]["teams"][0]["statistics"].pop()
        self.assertEqual(live_games(self.data,self.teams,"NFL",summary)[0]["fields"]["team_total_yards"], "")

    def test_pregame_final_and_missing_scores_hidden(self):
        competition = self.data["events"][0]["competitions"][0]
        for value in ("pre", "post"):
            competition["status"]["type"]["state"] = value
            self.assertEqual(live_games(self.data,self.teams,"NFL"), [])
        competition["status"]["type"]["state"] = "in"
        competition["competitors"][0]["score"] = None
        self.assertEqual(live_games(self.data,self.teams,"NFL"), [])

    def test_possession_color_follows_selected_team_even_away(self):
        competition = self.data['events'][0]['competitions'][0]
        competition['competitors'][0]['homeAway'] = 'away'
        competition['competitors'][1]['homeAway'] = 'home'
        settings = {**deepcopy(DEFAULTS), 'pages': [new_page('football', 'football')]}
        for possession, expected in [('6', 'green'), ('2', 'red'), ('', 'amber')]:
            competition['situation'] = {'possession': possession, 'downDistanceText': '2nd & 7', 'possessionText': 'DAL 35'}
            games = live_games(self.data, self.teams, 'NFL')
            frames = compose(settings, MODEL, lambda _: None, NOW, games)
            self.assertIn('2nd & 7 @ DAL 35', frames[0].text)
            colors = frames[0].color
            self.assertTrue(all(c == expected for c in colors[1]) if isinstance(colors, tuple) else colors == expected)
            page_message(frames[0].text, 1, MODEL, colors, frames[0].font, frames[0].alignment)


if __name__ == "__main__":
    unittest.main()
