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


@contextmanager
def patched_soccer_settings(cache_path, ttl_ms=600000):
    with patch.object(soccer.settings, "soccer_provider", "football-data"), patch.object(
        soccer.settings, "soccer_api_token", "test-token"
    ), patch.object(soccer.settings, "soccer_cache_path", cache_path), patch.object(
        soccer.settings, "soccer_cache_ttl_ms", ttl_ms
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


class SoccerCacheTests(unittest.TestCase):
    def test_cached_live_payload_forces_refresh_inside_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "soccer-cache.json"
            with patched_soccer_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = soccer.match_cache_key("SA")
                soccer.write_cache(cache_key, cached_soccer_payload(fixed, live=True))

                fetched = empty_soccer_payload(fixed)
                fetch_mock = AsyncMock(return_value=fetched)
                with patch("app.services.soccer.fetch_compact", fetch_mock):
                    result = asyncio.run(soccer.load_compact("SA"))

        fetch_mock.assert_awaited_once_with("SA")
        self.assertEqual(result, fetched)

    def test_cached_fixture_near_kickoff_forces_refresh_inside_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "soccer-cache.json"
            with patched_soccer_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = soccer.match_cache_key("SA")
                soccer.write_cache(cache_key, cached_soccer_payload(fixed, fixture_offset=timedelta(minutes=10)))

                fetched = empty_soccer_payload(fixed)
                fetch_mock = AsyncMock(return_value=fetched)
                with patch("app.services.soccer.fetch_compact", fetch_mock):
                    result = asyncio.run(soccer.load_compact("SA"))

        fetch_mock.assert_awaited_once_with("SA")
        self.assertEqual(result, fetched)

    def test_cached_fixture_after_kickoff_forces_refresh_inside_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "soccer-cache.json"
            with patched_soccer_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = soccer.match_cache_key("SA")
                soccer.write_cache(cache_key, cached_soccer_payload(fixed, fixture_offset=-timedelta(hours=3, minutes=30)))

                fetched = empty_soccer_payload(fixed)
                fetch_mock = AsyncMock(return_value=fetched)
                with patch("app.services.soccer.fetch_compact", fetch_mock):
                    result = asyncio.run(soccer.load_compact("SA"))

        fetch_mock.assert_awaited_once_with("SA")
        self.assertEqual(result, fetched)

    def test_cached_distant_fixture_can_still_use_cache_inside_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "soccer-cache.json"
            with patched_soccer_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = soccer.match_cache_key("SA")
                cached = cached_soccer_payload(fixed, fixture_offset=timedelta(days=2))
                soccer.write_cache(cache_key, cached)

                fetch_mock = AsyncMock(return_value=empty_soccer_payload(fixed))
                with patch("app.services.soccer.fetch_compact", fetch_mock):
                    result = asyncio.run(soccer.load_compact("SA"))

        fetch_mock.assert_not_awaited()
        self.assertEqual(result, cached)

    def test_cached_live_item_without_fixtures_forces_refresh_inside_ttl(self):
        fixed = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "soccer-cache.json"
            with patched_soccer_settings(cache_path), patch("app.services.bar_widget.now", return_value=fixed):
                cache_key = soccer.match_cache_key("SA")
                payload = empty_soccer_payload(fixed)
                payload["items"] = [cached_soccer_fixture(fixed, live=True)]
                soccer.write_cache(cache_key, payload)

                fetched = empty_soccer_payload(fixed)
                fetch_mock = AsyncMock(return_value=fetched)
                with patch("app.services.soccer.fetch_compact", fetch_mock):
                    result = asyncio.run(soccer.load_compact("SA"))

        fetch_mock.assert_awaited_once_with("SA")
        self.assertEqual(result, fetched)


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

    def test_live_match_keeps_slot_but_displays_after_results(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-5), "FINISHED"),
                (timedelta(days=-4), "FINISHED"),
                (timedelta(days=-3), "FINISHED"),
                (timedelta(days=-2), "FINISHED"),
                (timedelta(days=-1), "FINISHED"),
                (timedelta(minutes=-20), "IN_PLAY"),
                (timedelta(days=1), "SCHEDULED"),
            ],
        )

        self.assertEqual(len(payload["items"]), 4)
        self.assertEqual(len(payload["results"]), 2)
        self.assertEqual(len(payload["fixtures"]), 2)
        self.assertEqual(soccer_item_types(payload), ["result", "result", "live", "fixture"])
        self.assertEqual([item["displayDate"] for item in payload["results"]], ["02/06", "03/06"])

    def test_just_finished_match_is_selected_before_older_results(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-5), "FINISHED"),
                (timedelta(days=-4), "FINISHED"),
                (timedelta(days=-3), "FINISHED"),
                (timedelta(days=-2), "FINISHED"),
                (timedelta(minutes=-10), "FINISHED"),
                (timedelta(days=1), "SCHEDULED"),
                (timedelta(days=2), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["result", "result", "fixture", "fixture"])
        self.assertEqual([item["displayDate"] for item in payload["results"]], ["02/06", "04/06"])

    def test_one_live_fills_missing_past_with_next_matches(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-1), "FINISHED"),
                (timedelta(minutes=-20), "IN_PLAY"),
                (timedelta(days=1), "SCHEDULED"),
                (timedelta(days=2), "SCHEDULED"),
                (timedelta(days=3), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["result", "live", "fixture", "fixture"])

    def test_two_live_matches_keep_one_past_and_one_next(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-3), "FINISHED"),
                (timedelta(days=-2), "FINISHED"),
                (timedelta(minutes=-30), "IN_PLAY"),
                (timedelta(minutes=-10), "LIVE"),
                (timedelta(days=1), "SCHEDULED"),
                (timedelta(days=2), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["result", "live", "live", "fixture"])

    def test_two_live_matches_fill_missing_next_with_past(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-3), "FINISHED"),
                (timedelta(days=-2), "FINISHED"),
                (timedelta(days=-1), "FINISHED"),
                (timedelta(minutes=-30), "IN_PLAY"),
                (timedelta(minutes=-10), "LIVE"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["result", "result", "live", "live"])

    def test_three_live_matches_complete_with_past_before_next(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-2), "FINISHED"),
                (timedelta(minutes=-45), "IN_PLAY"),
                (timedelta(minutes=-30), "LIVE"),
                (timedelta(minutes=-15), "PAUSED"),
                (timedelta(days=1), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["result", "live", "live", "live"])

    def test_three_live_matches_complete_with_next_when_past_missing(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(minutes=-45), "IN_PLAY"),
                (timedelta(minutes=-30), "LIVE"),
                (timedelta(minutes=-15), "PAUSED"),
                (timedelta(days=1), "SCHEDULED"),
                (timedelta(days=2), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["live", "live", "live", "fixture"])

    def test_four_live_matches_use_all_slots(self):
        current = bar_widget.parse_datetime("2026-06-04T20:00:00+02:00")
        payload = soccer_payload(
            current,
            [
                (timedelta(days=-1), "FINISHED"),
                (timedelta(minutes=-50), "IN_PLAY"),
                (timedelta(minutes=-40), "LIVE"),
                (timedelta(minutes=-30), "PAUSED"),
                (timedelta(minutes=-20), "IN_PLAY"),
                (timedelta(minutes=-10), "LIVE"),
                (timedelta(days=1), "SCHEDULED"),
            ],
        )

        self.assertEqual(soccer_item_types(payload), ["live", "live", "live", "live"])


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


def empty_soccer_payload(fixed):
    return {
        "enabled": True,
        "available": True,
        "competition": "SA",
        "label": "Serie A",
        "results": [],
        "fixtures": [],
        "items": [],
        "updatedAt": fixed.isoformat(),
    }


def cached_soccer_payload(fixed, live=False, fixture_offset=timedelta()):
    payload = empty_soccer_payload(fixed)
    fixture = cached_soccer_fixture(fixed + fixture_offset, live=live)
    payload["fixtures"] = [fixture]
    payload["items"] = [fixture]
    return payload


def cached_soccer_fixture(match_time, live=False):
    return {
        "kind": "fixture",
        "time": match_time.isoformat(),
        "live": live,
        "home": {"name": "Home FC", "abbr": "HOM"},
        "away": {"name": "Away FC", "abbr": "AWY"},
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


def soccer_payload(current, specs):
    matches = [soccer_match((current + offset).isoformat(), status) for offset, status in specs]
    with patch("app.services.bar_widget.now", return_value=current):
        return soccer.normalize_matches("SA", {"matches": matches})


def soccer_item_types(payload):
    types = []
    for item in payload["items"]:
        if item.get("live"):
            types.append("live")
        else:
            types.append(item["kind"])
    return types


if __name__ == "__main__":
    unittest.main()
