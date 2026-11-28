"""Unit tests for dashboard.py — all mocked, no live API calls."""

import unittest
from unittest.mock import patch


class DashboardParseTests(unittest.TestCase):
    def _make_hour(self, epoch_offset=3600, **kwargs):
        defaults = {
            "time_epoch": 1735729200 + epoch_offset,
            "time": "2025-01-01 15:00",
            "condition": {"text": "Partly cloudy"},
            "chance_of_rain": 10,
            "precip_mm": 0.0,
            "gust_kph": 15.0,
            "temp_c": 18.0,
            "feelslike_c": 16.0,
            "pressure_mb": 1013.0,
            "wind_kph": 10.0,
            "humidity": 60,
            "will_it_thunder": 0,
            "chance_of_thunder": 0,
            "will_it_rain": 0,
            "vis_km": 10.0,
            "uv": 1.0,
            "dewpoint_c": 8.0,
        }
        defaults.update(kwargs)
        return defaults

    def _make_raw(self, hours=None):
        if hours is None:
            hours = [self._make_hour(3600 * i) for i in range(1, 13)]
        return {
            "location": {
                "name": "Lahore", "region": "Punjab", "country": "Pakistan",
                "lat": 31.558, "lon": 74.351, "tz_id": "Asia/Karachi",
                "localtime": "2025-01-01 14:00", "localtime_epoch": 1735729200,
            },
            "current": {
                "temp_c": 18.0, "feelslike_c": 16.5,
                "condition": {"text": "Partly cloudy", "icon": "//cdn.icon.png"},
                "wind_kph": 12.0, "wind_dir": "N", "gust_kph": 20.0,
                "humidity": 60, "pressure_mb": 1013.0, "precip_mm": 0.0,
                "uv": 2.0, "vis_km": 10.0, "last_updated": "2025-01-01 13:45",
            },
            "forecast": {"forecastday": [{"hour": hours}]},
            "alerts": {"alert": []},
        }

    def test_parse_basic_fields(self):
        from dashboard import _parse_weather
        w = _parse_weather(self._make_raw())
        self.assertIn("Lahore", w["city"])
        self.assertIn("Pakistan", w["city"])
        self.assertEqual(w["temp_c"], 18.0)
        self.assertEqual(w["condition"], "Partly cloudy")

    def test_no_alerts_returns_empty_list(self):
        from dashboard import _parse_weather
        w = _parse_weather(self._make_raw())
        self.assertEqual(w["alerts"], [])

    def test_storm_thunder_hours_counted(self):
        from dashboard import _parse_weather
        hours = [self._make_hour(3600 * i, will_it_thunder=(1 if i <= 3 else 0)) for i in range(1, 13)]
        w = _parse_weather(self._make_raw(hours))
        self.assertEqual(w["storm_thunder_hour_count"], 3)

    def test_city_label_formatting(self):
        from dashboard import _city_label
        label = _city_label({"name": "Lahore", "region": "Punjab", "country": "Pakistan"})
        self.assertEqual(label, "Lahore, Punjab, Pakistan")

    def test_city_label_no_region(self):
        from dashboard import _city_label
        label = _city_label({"name": "London", "region": "", "country": "UK"})
        self.assertEqual(label, "London, UK")

    def test_na_helper(self):
        from dashboard import _na
        self.assertEqual(_na(None), "N/A")
        self.assertEqual(_na(""), "N/A")
        self.assertEqual(_na(18.5), "18.5")

    def test_search_cities_returns_empty_on_error(self):
        from dashboard import _search_cities
        with patch("dashboard.requests.get", side_effect=Exception("network error")):
            result = _search_cities("Lahore", "bad-key")
        self.assertEqual(result, [])

    def test_storm_analysis_peak_gust(self):
        from dashboard import _storm_analysis
        hours = [
            {"time": "15:00", "gust_kph": 20.0, "precip_mm": 0, "pressure_mb": 1013,
             "humidity": 60, "will_it_thunder": 0, "chance_of_thunder": 0},
            {"time": "16:00", "gust_kph": 55.0, "precip_mm": 0, "pressure_mb": 1012,
             "humidity": 65, "will_it_thunder": 0, "chance_of_thunder": 0},
        ]
        result = _storm_analysis(hours)
        self.assertEqual(result["peak_gust_kph"], 55.0)

    def test_storm_analysis_total_precip(self):
        from dashboard import _storm_analysis
        hours = [
            {"time": "15:00", "gust_kph": 10, "precip_mm": 1.5, "pressure_mb": 1013,
             "humidity": 70, "will_it_thunder": 0, "chance_of_thunder": 0},
            {"time": "16:00", "gust_kph": 10, "precip_mm": 3.0, "pressure_mb": 1012,
             "humidity": 75, "will_it_thunder": 0, "chance_of_thunder": 0},
        ]
        result = _storm_analysis(hours)
        self.assertAlmostEqual(result["total_precip_mm"], 4.5)


if __name__ == "__main__":
    unittest.main()
