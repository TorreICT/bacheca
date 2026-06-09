import asyncio
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx

from app.services import bar_widget
from app.services import weather


class WeatherServiceTests(unittest.TestCase):
    def test_build_forecast_url_targets_configured_provider(self):
        with patch.object(weather.settings, "weather_forecast_url", "https://example.test/forecast"):
            url = weather.build_forecast_url(
                45.4766567,
                9.2350757,
                "Europe/Rome",
                "2026-06-04",
                "2026-06-08",
                "temperature_2m,weather_code,wind_speed_10m",
                "weather_code,temperature_2m_max,temperature_2m_min",
            )

        parts = urlsplit(url)
        params = parse_qs(parts.query)

        self.assertEqual(parts.scheme, "https")
        self.assertEqual(parts.netloc, "example.test")
        self.assertEqual(parts.path, "/forecast")
        self.assertEqual(params["latitude"], ["45.4766567"])
        self.assertEqual(params["longitude"], ["9.2350757"])
        self.assertEqual(params["timezone"], ["Europe/Rome"])
        self.assertEqual(params["start_date"], ["2026-06-04"])
        self.assertEqual(params["end_date"], ["2026-06-08"])
        self.assertEqual(params["current"], ["temperature_2m,weather_code,wind_speed_10m"])
        self.assertEqual(params["daily"], ["weather_code,temperature_2m_max,temperature_2m_min"])

    def test_invalid_weather_field_is_rejected(self):
        with self.assertRaises(weather.WeatherRequestError):
            weather.build_forecast_url(
                45.4766567,
                9.2350757,
                "Europe/Rome",
                "2026-06-04",
                "2026-06-08",
                "temperature_2m,not_a_weather_field",
                "weather_code",
            )

    def test_current_uv_index_field_is_accepted(self):
        with patch.object(weather.settings, "weather_forecast_url", "https://example.test/forecast"):
            url = weather.build_forecast_url(
                45.4766567,
                9.2350757,
                "Europe/Rome",
                "2026-06-04",
                "2026-06-08",
                "temperature_2m,uv_index",
                "weather_code,uv_index_max",
            )

        params = parse_qs(urlsplit(url).query)

        self.assertEqual(params["current"], ["temperature_2m,uv_index"])
        self.assertEqual(params["daily"], ["weather_code,uv_index_max"])

    def test_forecast_range_is_limited(self):
        with self.assertRaises(weather.WeatherRequestError):
            weather.build_forecast_url(
                45.4766567,
                9.2350757,
                "Europe/Rome",
                "2026-06-04",
                "2026-06-25",
                "temperature_2m",
                "weather_code",
            )

    def test_load_forecast_uses_stale_cache_when_upstream_fails(self):
        fixed = bar_widget.parse_datetime("2026-06-04T14:00:00+02:00")
        payload = {"current": {"temperature_2m": 24}, "daily": {"time": ["2026-06-04"]}}

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "weather-cache.json"
            with patch.object(weather.settings, "weather_cache_path", cache_path), patch.object(
                weather.settings, "weather_cache_ttl_ms", 1
            ), patch("app.services.weather.bar_widget.now", return_value=fixed):
                key = weather.build_forecast_url(
                    45.4766567,
                    9.2350757,
                    "Europe/Rome",
                    "2026-06-04",
                    "2026-06-08",
                    "temperature_2m",
                    "weather_code",
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps(
                        {
                            key: {
                                "fetchedAt": bar_widget.isoformat(fixed - timedelta(minutes=5)),
                                "payload": payload,
                            }
                        }
                    ),
                    encoding="utf-8",
                )

                fetch_mock = AsyncMock(side_effect=httpx.ConnectError("boom"))
                with patch("app.services.weather.fetch_forecast", fetch_mock):
                    result = asyncio.run(
                        weather.load_forecast(
                            45.4766567,
                            9.2350757,
                            "Europe/Rome",
                            "2026-06-04",
                            "2026-06-08",
                            "temperature_2m",
                            "weather_code",
                        )
                    )

        fetch_mock.assert_awaited_once()
        self.assertEqual(result["current"], payload["current"])
        self.assertTrue(result["stale"])

    def test_load_forecast_adds_location_to_fresh_payload(self):
        payload = {"current": {"temperature_2m": 24}, "daily": {"time": ["2026-06-04"]}}

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "weather-cache.json"
            with patch.object(weather.settings, "weather_cache_path", cache_path):
                fetch_mock = AsyncMock(return_value=payload)
                location_mock = AsyncMock(return_value="Lambrate, Milano")
                with patch("app.services.weather.fetch_forecast", fetch_mock), patch(
                    "app.services.weather.fetch_location_name", location_mock
                ):
                    result = asyncio.run(
                        weather.load_forecast(
                            45.4766567,
                            9.2350757,
                            "Europe/Rome",
                            "2026-06-04",
                            "2026-06-08",
                            "temperature_2m",
                            "weather_code",
                        )
                    )

        self.assertEqual(result["location"], "Lambrate, Milano")

    def test_load_forecast_adds_location_to_older_fresh_cache(self):
        fixed = bar_widget.parse_datetime("2026-06-04T14:00:00+02:00")
        payload = {"current": {"temperature_2m": 24}, "daily": {"time": ["2026-06-04"]}}

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "weather-cache.json"
            with patch.object(weather.settings, "weather_cache_path", cache_path), patch.object(
                weather.settings, "weather_cache_ttl_ms", 600000
            ), patch("app.services.weather.bar_widget.now", return_value=fixed):
                key = weather.build_forecast_url(
                    45.4766567,
                    9.2350757,
                    "Europe/Rome",
                    "2026-06-04",
                    "2026-06-08",
                    "temperature_2m",
                    "weather_code",
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({key: {"fetchedAt": bar_widget.isoformat(fixed), "payload": payload}}),
                    encoding="utf-8",
                )

                fetch_mock = AsyncMock(return_value={})
                location_mock = AsyncMock(return_value="Lambrate, Milano")
                with patch("app.services.weather.fetch_forecast", fetch_mock), patch(
                    "app.services.weather.fetch_location_name", location_mock
                ):
                    result = asyncio.run(
                        weather.load_forecast(
                            45.4766567,
                            9.2350757,
                            "Europe/Rome",
                            "2026-06-04",
                            "2026-06-08",
                            "temperature_2m",
                            "weather_code",
                        )
                    )

        fetch_mock.assert_not_awaited()
        self.assertEqual(result["location"], "Lambrate, Milano")

    def test_location_name_prefers_area_and_city(self):
        body = {
            "address": {
                "neighbourhood": "Citt\u00e0 Studi",
                "suburb": "Municipio 3",
                "city": "Milano",
                "state": "Lombardia",
            }
        }

        self.assertEqual(weather.location_name_from_geocode(body), "Citt\u00e0 Studi, Milano")

    def test_location_name_falls_back_to_city_and_state(self):
        body = {"address": {"city": "Milano", "state": "Lombardia"}}

        self.assertEqual(weather.location_name_from_geocode(body), "Milano, Lombardia")

    def test_location_name_prefers_quarter_over_municipio_suburb(self):
        body = {"address": {"quarter": "Citt\u00e0 Studi", "suburb": "Municipio 3", "city": "Milano"}}

        self.assertEqual(weather.location_name_from_geocode(body), "Citt\u00e0 Studi, Milano")
