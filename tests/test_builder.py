"""Behavioral tests for persistent layouts, rotation, alerts and live metadata."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
import json
from types import SimpleNamespace
import unittest

from custom_components.viewmarq.builder import (Frame, Player, compose, effective_pages,
    field, new_page, render_pages, validate_pages, live_game_preview, sample_frames)
from custom_components.viewmarq.const import DEFAULTS
from custom_components.viewmarq.sports_data import live_games
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


if __name__ == "__main__":
    unittest.main()
