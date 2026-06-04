import asyncio
import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services import bar_widget, basketball, soccer


@contextmanager
def patched_basketball_settings(cache_path, ttl_ms=1800000):
    with patch.object(basketball.settings, "basketball_provider", "api-sports"), patch.object(
        basketball.settings, "basketball_api_token", "test-token"
    ), patch.object(basketball.settings, "basketball_base_url", "https://v1.basketball.api-sports.io"), patch.object(
        basketball.settings, "basketball_cache_path", cache_path
    ), patch.object(
        basketball.settings, "basketball_cache_ttl_ms", ttl_ms
    ), patch.object(
        basketball.settings, "basketball_lookback_days", 30
    ), patch.object(
        basketball.settings, "basketball_lookahead_days", 30
    ), patch.object(
        basketball.settings, "basketball_max_items", 4
    ):
        yield


def write_cache_entry(path, key, fetched_at, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump({key: {"fetchedAt": fetched_at.isoformat(), "payload": payload}}, handle)


class BasketballNormalizationTests(unittest.TestCase):
    def test_api_sports_live_status_normalizes_as_live_fixture(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        game = api_sports_game(status_short="Q2", status_long="Quarter 2")

        item = basketball.normalize_api_sports_game(
            game,
            current,
            current - timedelta(days=1),
            current + timedelta(days=1),
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["kind"], "fixture")
        self.assertTrue(item["live"])
        self.assertEqual(item["period"], "Q2")
        self.assertEqual(item["score"], {"home": 48, "away": 44})

    def test_api_sports_stage_label_prefers_stage_then_week(self):
        stage_game = api_sports_game(stage="semi_finals", week="week_2")
        week_game = api_sports_game(stage=None, week="quarter_finals")

        self.assertEqual(basketball.api_sports_stage_label(stage_game), "Semi Finals")
        self.assertEqual(basketball.api_sports_stage_label(week_game), "Quarter Finals")


class BasketballCacheTests(unittest.TestCase):
    def test_cached_live_payload_is_fresh_for_full_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "basketball-cache.json"
            with patched_basketball_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = "api-sports:" + basketball.match_cache_key("12", "2025-2026")
                basketball.write_cache(cache_key, cached_basketball_payload(fixed, live=True))

                fetch_mock = AsyncMock(return_value={})
                with patch("app.services.basketball.fetch_compact", fetch_mock):
                    result = asyncio.run(basketball.load_compact("12", "2025-2026"))

        fetch_mock.assert_not_awaited()
        self.assertTrue(result["fixtures"][0]["live"])
        self.assertFalse(result.get("stale", False))

    def test_stale_cached_failure_is_throttled(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "basketball-cache.json"
            with patched_basketball_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = "api-sports:" + basketball.match_cache_key("12", "2025-2026")
                write_cache_entry(
                    cache_path,
                    cache_key,
                    fixed - timedelta(hours=1),
                    cached_basketball_payload(fixed, live=False),
                )

                fetch_mock = AsyncMock(side_effect=RuntimeError("provider down"))
                with patch("app.services.basketball.fetch_compact", fetch_mock):
                    first = asyncio.run(basketball.load_compact("12", "2025-2026"))
                    second = asyncio.run(basketball.load_compact("12", "2025-2026"))

        self.assertEqual(fetch_mock.await_count, 1)
        self.assertTrue(first["stale"])
        self.assertTrue(second["stale"])
        self.assertEqual(second["message"], "provider down")

    def test_uncached_failure_is_cached_as_unavailable(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "basketball-cache.json"
            with patched_basketball_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                fetch_mock = AsyncMock(side_effect=RuntimeError("quota pause"))
                with patch("app.services.basketball.fetch_compact", fetch_mock):
                    first = asyncio.run(basketball.load_compact("12", "2025-2026"))
                    second = asyncio.run(basketball.load_compact("12", "2025-2026"))

        self.assertEqual(fetch_mock.await_count, 1)
        self.assertFalse(first["available"])
        self.assertFalse(second["available"])
        self.assertEqual(second["message"], "quota pause")


class SoccerLiveNormalizationTests(unittest.TestCase):
    def test_live_match_survives_old_kickoff_cutoff(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        match = soccer_match((current - timedelta(hours=6)).isoformat(), "IN_PLAY")

        item = soccer.normalize_match(match, current)

        self.assertIsNotNone(item)
        self.assertEqual(item["kind"], "fixture")
        self.assertTrue(item["live"])

    def test_old_scheduled_match_still_gets_discarded(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        match = soccer_match((current - timedelta(hours=6)).isoformat(), "SCHEDULED")

        self.assertIsNone(soccer.normalize_match(match, current))


def api_sports_game(status_short="NS", status_long="Not Started", stage=None, week=None):
    return {
        "id": 123,
        "date": "2026-06-04T20:05:00+02:00",
        "stage": stage,
        "week": week,
        "status": {
            "short": status_short,
            "long": status_long,
            "timer": None,
        },
        "league": {
            "id": 12,
            "name": "NBA",
            "season": "2025-2026",
        },
        "country": {
            "name": "USA",
        },
        "teams": {
            "home": {
                "id": 1,
                "name": "Milano",
                "code": "MIL",
                "logo": "https://media.api-sports.io/basketball/teams/1.png",
            },
            "away": {
                "id": 2,
                "name": "Roma",
                "code": "ROM",
                "logo": "https://media.api-sports.io/basketball/teams/2.png",
            },
        },
        "scores": {
            "home": {"total": 48},
            "away": {"total": 44},
        },
    }


def cached_basketball_payload(fixed, live):
    return {
        "enabled": True,
        "available": True,
        "competition": "12",
        "season": "2025-2026",
        "label": "NBA",
        "results": [],
        "fixtures": [
            {
                "kind": "fixture",
                "time": fixed.isoformat(),
                "live": live,
                "home": {"name": "Milano", "abbr": "MIL"},
                "away": {"name": "Roma", "abbr": "ROM"},
            }
        ],
        "items": [],
        "updatedAt": fixed.isoformat(),
    }


def soccer_match(utc_date, status):
    return {
        "utcDate": utc_date,
        "status": status,
        "minute": 55,
        "injuryTime": None,
        "stage": "REGULAR_SEASON",
        "matchday": 8,
        "homeTeam": {
            "id": 1,
            "name": "Home FC",
            "shortName": "Home",
            "tla": "HOM",
        },
        "awayTeam": {
            "id": 2,
            "name": "Away FC",
            "shortName": "Away",
            "tla": "AWY",
        },
        "score": {
            "fullTime": {
                "home": 1,
                "away": 1,
            },
            "penalties": {},
        },
    }


if __name__ == "__main__":
    unittest.main()
