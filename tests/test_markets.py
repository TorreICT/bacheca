import asyncio
import json
import tempfile
import sys
import types
import unittest
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app.services import bar_widget, markets

if find_spec("telegram") is None:
    telegram_module = types.ModuleType("telegram")
    telegram_ext_module = types.ModuleType("telegram.ext")

    class DummyTelegramType:
        def __init__(self, *args, **kwargs):
            pass

    class DummyApplication:
        @classmethod
        def builder(cls):
            return cls()

        def token(self, *args, **kwargs):
            return self

        def build(self):
            return self

        def add_handler(self, *args, **kwargs):
            pass

    telegram_module.InlineKeyboardButton = DummyTelegramType
    telegram_module.InlineKeyboardMarkup = DummyTelegramType
    telegram_module.Update = DummyTelegramType
    telegram_ext_module.Application = DummyApplication
    telegram_ext_module.CallbackQueryHandler = DummyTelegramType
    telegram_ext_module.CommandHandler = DummyTelegramType
    telegram_ext_module.ContextTypes = DummyTelegramType
    telegram_ext_module.MessageHandler = DummyTelegramType
    telegram_ext_module.filters = DummyTelegramType()
    sys.modules["telegram"] = telegram_module
    sys.modules["telegram.ext"] = telegram_ext_module

from telegram_bot import bot


YAHOO_CHART = {
    "chart": {
        "result": [
            {
                "meta": {
                    "symbol": "^GSPC",
                    "regularMarketPrice": 7440.4,
                    "previousClose": 7383.74,
                    "regularMarketTime": 1780937326,
                    "exchangeTimezoneName": "America/New_York",
                }
            }
        ],
        "error": None,
    }
}


class MarketQuoteTests(unittest.TestCase):
    def test_normalize_yahoo_quote_computes_change_from_previous_close(self):
        quote = markets.normalize_yahoo_quote("^SPX", "S&P 500", YAHOO_CHART, "^GSPC")

        self.assertEqual(quote["symbol"], "^SPX")
        self.assertEqual(quote["providerSymbol"], "^GSPC")
        self.assertEqual(quote["label"], "S&P 500")
        self.assertEqual(quote["value"], 7440.4)
        self.assertEqual(quote["previous"], 7383.74)
        self.assertEqual(quote["change"], 56.66)
        self.assertEqual(quote["changePercent"], 0.77)
        self.assertEqual(quote["direction"], "up")
        self.assertEqual(quote["date"], "2026-06-08")
        self.assertTrue(quote["available"])

    def test_yahoo_symbol_for_maps_legacy_common_indexes(self):
        self.assertEqual(markets.yahoo_symbol_for("^SPX"), "^GSPC")
        self.assertEqual(markets.yahoo_symbol_for("^NDQ"), "^NDX")
        self.assertEqual(markets.yahoo_symbol_for("^DAX"), "^GDAXI")


class MarketCacheTests(unittest.TestCase):
    def test_load_index_uses_fresh_cache(self):
        payload = markets.normalize_yahoo_quote("^SPX", "S&P 500", YAHOO_CHART, "^GSPC")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "market-cache.json"
            cache_path.write_text(
                json.dumps({"^SPX": {"fetchedAt": markets.now_iso(), "payload": payload}}),
                encoding="utf-8",
            )
            with patch.object(markets.settings, "market_cache_path", cache_path):
                fetch_mock = AsyncMock(return_value={})
                with patch("app.services.markets.fetch_index", fetch_mock):
                    result = asyncio.run(markets.load_index({"symbol": "^SPX", "label": "S&P 500"}))

        fetch_mock.assert_not_awaited()
        self.assertEqual(result["value"], 7440.4)

    def test_load_index_ignores_legacy_cache_without_current_source(self):
        payload = markets.normalize_yahoo_quote("^SPX", "S&P 500", YAHOO_CHART, "^GSPC")
        legacy_payload = dict(payload)
        legacy_payload.pop("source", None)

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "market-cache.json"
            cache_path.write_text(
                json.dumps({"^SPX": {"fetchedAt": markets.now_iso(), "payload": legacy_payload}}),
                encoding="utf-8",
            )
            with patch.object(markets.settings, "market_cache_path", cache_path):
                fetch_mock = AsyncMock(return_value=payload)
                with patch("app.services.markets.fetch_index", fetch_mock):
                    result = asyncio.run(markets.load_index({"symbol": "^SPX", "label": "S&P 500"}))

        fetch_mock.assert_awaited_once()
        self.assertEqual(result["source"], "yahoo")

    def test_load_index_uses_stale_cache_when_provider_fails(self):
        payload = markets.normalize_yahoo_quote("^SPX", "S&P 500", YAHOO_CHART, "^GSPC")

        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "market-cache.json"
            cache_path.write_text(
                json.dumps({"^SPX": {"fetchedAt": "2020-01-01T00:00:00+00:00", "payload": payload}}),
                encoding="utf-8",
            )
            with patch.object(markets.settings, "market_cache_path", cache_path), patch.object(
                markets.settings, "market_cache_ttl_ms", 1
            ):
                fetch_mock = AsyncMock(side_effect=httpx.ConnectError("boom"))
                with patch("app.services.markets.fetch_index", fetch_mock):
                    result = asyncio.run(markets.load_index({"symbol": "^SPX", "label": "S&P 500"}))

        fetch_mock.assert_awaited_once()
        self.assertEqual(result["value"], 7440.4)
        self.assertTrue(result["stale"])

    def test_load_index_returns_unavailable_without_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "market-cache.json"
            with patch.object(markets.settings, "market_cache_path", cache_path):
                fetch_mock = AsyncMock(side_effect=httpx.ConnectError("boom"))
                with patch("app.services.markets.fetch_index", fetch_mock):
                    result = asyncio.run(markets.load_index({"symbol": "^SPX", "label": "S&P 500"}))

        self.assertFalse(result["available"])
        self.assertEqual(result["symbol"], "^SPX")


class MarketStateTests(unittest.TestCase):
    def test_missing_markets_state_gets_default_disabled_selection(self):
        state = bar_widget.normalize_state({})

        self.assertFalse(state["markets"]["enabled"])
        self.assertEqual([item["symbol"] for item in state["markets"]["symbols"]], ["^SPX", "^DJI", "^NDQ", "^DAX"])

    def test_markets_state_filters_duplicates_invalid_symbols_and_max_items(self):
        raw = {
            "markets": {
                "enabled": True,
                "symbols": [
                    {"symbol": "^spx", "label": "S&P 500"},
                    {"symbol": "^spx", "label": "Duplicate"},
                    {"symbol": "bad symbol", "label": "Bad"},
                    {"symbol": "^dji", "label": "Dow"},
                    {"symbol": "^ndq", "label": "Nasdaq"},
                ],
            }
        }

        with patch.object(markets.settings, "market_max_items", 2):
            state = bar_widget.normalize_state(raw)

        self.assertTrue(state["markets"]["enabled"])
        self.assertEqual(state["markets"]["symbols"], [{"symbol": "^SPX", "label": "S&P 500"}, {"symbol": "^DJI", "label": "Dow"}])

    def test_toggle_market_symbol_removes_and_adds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "bar-widget-state.json"
            state_path.write_text(
                json.dumps({"markets": {"enabled": True, "symbols": []}}),
                encoding="utf-8",
            )
            with patch.object(bar_widget.settings, "bar_widget_state_path", state_path), patch.object(
                markets.settings, "market_max_items", 4
            ):
                selected = bar_widget.toggle_market_symbol("^UKX", "FTSE 100")
                state = bar_widget.load_state()
                removed = bar_widget.toggle_market_symbol("^UKX", "FTSE 100")
                state_after_remove = bar_widget.load_state()

        self.assertTrue(selected)
        self.assertIn({"symbol": "^UKX", "label": "FTSE 100"}, state["markets"]["symbols"])
        self.assertFalse(removed)
        self.assertNotIn({"symbol": "^UKX", "label": "FTSE 100"}, state_after_remove["markets"]["symbols"])


class MarketTelegramTests(unittest.TestCase):
    def test_parse_market_symbol_text_accepts_custom_label(self):
        self.assertEqual(bot.parse_market_symbol_text("^spx | S&P 500"), {"symbol": "^SPX", "label": "S&P 500"})

    def test_parse_market_symbol_text_rejects_invalid_symbol(self):
        with self.assertRaises(ValueError):
            bot.parse_market_symbol_text("bad symbol | Bad")
