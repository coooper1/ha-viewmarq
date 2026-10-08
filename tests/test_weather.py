from datetime import datetime, timezone
from types import SimpleNamespace
from copy import deepcopy
import unittest

from custom_components.viewmarq.weather_data import reading, nws_alerts
from custom_components.viewmarq.builder import compose, new_page, validate_pages
from custom_components.viewmarq.const import DEFAULTS

NOW = datetime(2026, 10, 8, 20, 0, tzinfo=timezone.utc)


def state(value, **attrs):
    return SimpleNamespace(state=value, attributes=attrs)


class WeatherTests(unittest.TestCase):
    def test_readings_units_and_missing_values(self):
        weather = state('sunny', temperature=30, temperature_unit='°C', uv_index=4.2,
                        _viewmarq_forecast={'precipitation_probability': 0})
        self.assertEqual(reading('temperature_f', weather), '86°F')
        self.assertEqual(reading('rain_chance', weather), '0%')
        self.assertEqual(reading('uv_index', weather), '4.2 Moderate')
        self.assertEqual(reading('heat_index', weather), 'Unavailable')
        self.assertEqual(reading('feels_like', weather), 'Unavailable')
        weather.attributes['_viewmarq_forecast'] = {'precipitation': 0}
        self.assertEqual(reading('rain_chance', weather), 'Unavailable')
        self.assertEqual(reading('heat_index', weather, state('91', unit_of_measurement='°F')), '91°F')
        self.assertEqual(reading('uv_index', weather, state('unavailable')), 'Unavailable')
        weather.attributes.update(temperature=32.222222, humidity=70)
        self.assertEqual(reading('heat_index', weather), '106°F est.')
        self.assertEqual(reading('feels_like', weather), '106°F est.')
        weather.attributes.update(temperature=0, wind_speed=10, wind_speed_unit='mph')
        self.assertEqual(reading('feels_like', weather), '24°F est.')
        self.assertEqual(reading('heat_index', weather), 'Unavailable')

    def test_only_actual_unexpired_alerts_override_rotation(self):
        alert = {'Event': 'Tornado Warning', 'Status': 'Actual', 'Expires': '2026-10-08T21:00:00Z'}
        sensors = {'sensor.nws': state('1', Alerts=[alert]), 'weather.test': state('sunny', temperature=86, temperature_unit='°F')}
        settings = {**deepcopy(DEFAULTS), 'nws_alert_entity': 'sensor.nws', 'weather_entity': 'weather.test', 'pages': [new_page('weather_detail', 'weather')]}
        validate_pages(settings['pages'], settings, 'MD4-0224')
        frames = compose(settings, 'MD4-0224', sensors.get, NOW, [])
        self.assertIn('Tornado Warning', frames[0].text)
        self.assertEqual(frames[0].color, 'red')
        for change in ({'Status': 'Test'}, {'Expires': '2026-10-08T19:00:00Z'}, {'Ends': '2026-10-08T19:00:00Z'}, {'MessageType': 'Cancel'}):
            sensors['sensor.nws'].attributes['Alerts'] = [{**alert, **change}]
            frames = compose(settings, 'MD4-0224', sensors.get, NOW, [])
            self.assertTrue(all(f.kind != 'Priority alert' for f in frames))
            self.assertTrue(any('86°F' in f.text for f in frames))
        sensors['sensor.nws'] = state('unavailable')
        frames = compose(settings, 'MD4-0224', sensors.get, NOW, [])
        self.assertTrue(any('unavailable' in f.text for f in frames))
        self.assertIn('unavailable', nws_alerts(None, NOW)[1])

    def test_watch_is_amber_and_tornado_warning_sorts_first(self):
        alerts = [{'Event': name, 'Status': 'Actual', 'Expires': '2026-10-08T21:00:00Z'}
                  for name in ('Flood Warning', 'Tornado Watch', 'Tornado Warning')]
        active, _ = nws_alerts(state('3', Alerts=alerts), NOW)
        self.assertTrue(active[0]['text'].startswith('Tornado Warning'))
        self.assertFalse(active[-1]['warning'])
        settings = {**deepcopy(DEFAULTS), 'nws_alert_entity': 'sensor.nws', 'pages': []}
        frames = compose(settings, 'MD4-0224', lambda _: state('1', Alerts=[alerts[1]]), NOW, [])
        self.assertEqual(frames[0].color, 'amber')
