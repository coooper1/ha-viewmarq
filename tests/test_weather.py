from datetime import datetime, timezone
from types import SimpleNamespace
from copy import deepcopy
import unittest

from custom_components.viewmarq.weather_data import reading, nws_alerts
from custom_components.viewmarq.builder import compose, new_page, validate_pages, sample_frames, sign_test_frames, field
from custom_components.viewmarq.protocol import page_message
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

    def test_individual_weather_provider_for_rain(self):
        page = new_page('weather_detail', 'detail')
        page['fields'][2]['entity'] = 'weather.nws'
        states = {'weather.main': state('sunny', temperature=86, temperature_unit='°F', uv_index=4.2),
                  'weather.nws': state('sunny', _viewmarq_forecast={'precipitation_probability': 25})}
        settings = {**deepcopy(DEFAULTS), 'weather_entity': 'weather.main', 'pages': [page]}
        frames = compose(settings, 'MD4-0224', states.get, NOW, [])
        self.assertTrue(any('Rain next: 25%' in f.text and 'UV: 4.2 Moderate' in f.text for f in frames))

    def test_compact_weather_and_warning_cycle_share_identical_frame(self):
        page = new_page('weather_compact', 'compact')
        states = {'weather.main': state('sunny', temperature=86, temperature_unit='°F', uv_index=4.2, humidity=41,
                                       _viewmarq_forecast={'precipitation_probability': 100})}
        settings = {**deepcopy(DEFAULTS), 'weather_entity': 'weather.main', 'pages': [page],
                    'nws_alert_entity': 'sensor.nws', 'weather_warning_mode': 'alternate_weather'}
        states['sensor.nws'] = state('0', Alerts=[])
        validate_pages(settings['pages'], settings, 'MD4-0224')
        normal = compose(settings, 'MD4-0224', states.get, NOW, [])
        self.assertEqual(len(normal), 1)
        for text in ('8:00PM', '86°F', 'Sun', 'UV 4.2', 'R 100%', 'H 86°*', 'F 86°*'):
            self.assertIn(text, normal[0].text)
        states['sensor.nws'] = state('1', Alerts=[{'Event': 'Tornado Warning', 'Status': 'Actual', 'Expires': '2026-10-08T21:00:00Z'}])
        active = compose(settings, 'MD4-0224', states.get, NOW, [])
        self.assertEqual([f.kind for f in active], ['Priority alert', 'weather_compact'])
        self.assertEqual(active[1], normal[0])
        settings['binary_sensors'] = ['binary_sensor.smoke']
        states['binary_sensor.smoke'] = state('on', device_class='smoke', friendly_name='Smoke')
        self.assertTrue(all(f.kind == 'Priority alert' for f in compose(settings, 'MD4-0224', states.get, NOW, [])))

    def test_editable_alert_templates_and_explicit_physical_test_marker(self):
        template = new_page('weather_alert', 'custom-alert')
        template.update(color='amber', dwell=7)
        template['fields'][0]['label'] = 'NWS'
        states = {'sensor.nws': state('1', Alerts=[{'Event': 'Flood Warning', 'Status': 'Actual', 'Expires': '2026-10-08T21:00:00Z'}])}
        settings = {**deepcopy(DEFAULTS), 'pages': [template], 'nws_alert_entity': 'sensor.nws'}
        frames = compose(settings, 'MD4-0224', states.get, NOW, [])
        self.assertIn('NWS Flood Warning', frames[0].text)
        self.assertEqual(frames[0].color, 'amber'); self.assertEqual(frames[0].dwell, 7)
        states['sensor.nws'].attributes['Alerts'] = []
        self.assertEqual(compose(settings, 'MD4-0224', states.get, NOW, [])[0].key, 'blank')
        template['fields'] = [field('text', text='Custom notice')]
        tests = sign_test_frames(sample_frames(template, settings, 'MD4-0224', states.get, NOW), 'MD4-0224')
        self.assertTrue(tests[0].text.startswith('TEST '))
        page_message(tests[0].text, 1, 'MD4-0224', tests[0].color, tests[0].font, tests[0].alignment)
