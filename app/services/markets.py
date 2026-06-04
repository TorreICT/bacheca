import csv
import io
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from app.config import settings


DEFAULT_SYMBOLS = [
    {"symbol": "^SPX", "label": "S&P 500"},
    {"symbol": "^DJI", "label": "Dow Jones"},
    {"symbol": "^NDQ", "label": "Nasdaq 100"},
    {"symbol": "^DAX", "label": "DAX"},
]

COMMON_SYMBOLS = DEFAULT_SYMBOLS + [
    {"symbol": "^UKX", "label": "FTSE 100"},
    {"symbol": "^CAC", "label": "CAC 40"},
    {"symbol": "^SMI", "label": "SMI"},
]

SYMBOL_RE = re.compile(r"^[A-Z0-9.\^_\-=]{1,24}$")
STOOQ_FIELDS = "sd2t2ohlcvp"


class MarketSymbolError(ValueError):
    pass


def common_label(symbol):
    normalized = normalize_symbol(symbol)
    for item in COMMON_SYMBOLS:
        if item["symbol"] == normalized:
            return item["label"]
    return normalized


def normalize_symbol(value):
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.match(symbol):
        raise MarketSymbolError("Invalid market symbol")
    return symbol


def normalize_symbol_entry(value):
    if isinstance(value, dict):
        symbol = normalize_symbol(value.get("symbol"))
        label = clean_label(value.get("label") or common_label(symbol))
    else:
        symbol = normalize_symbol(value)
        label = common_label(symbol)
    return {"symbol": symbol, "label": label}


def normalize_symbol_list(value, max_items=None, default_if_empty=True):
    source = value if isinstance(value, list) else DEFAULT_SYMBOLS
    normalized = []
    seen = set()
    try:
        limit = max(1, int(max_items or settings.market_max_items or 4))
    except (TypeError, ValueError):
        limit = 4
    for item in source:
        try:
            entry = normalize_symbol_entry(item)
        except MarketSymbolError:
            continue
        if entry["symbol"] in seen:
            continue
        seen.add(entry["symbol"])
        normalized.append(entry)
        if len(normalized) >= limit:
            break
    if normalized or not default_if_empty:
        return normalized
    return clone_symbols(DEFAULT_SYMBOLS[:limit])


def clone_symbols(symbols):
    return [{"symbol": item["symbol"], "label": item["label"]} for item in symbols]


def clean_label(value):
    label = " ".join(str(value or "").split())
    return (label or "Indice")[:32]


def parse_custom_symbol(value):
    parts = [part.strip() for part in str(value or "").split("|", 1)]
    symbol = normalize_symbol(parts[0] if parts else "")
    label = clean_label(parts[1]) if len(parts) > 1 else common_label(symbol)
    return {"symbol": symbol, "label": label}


async def load_indexes(symbols):
    entries = normalize_symbol_list(symbols, default_if_empty=False)
    items = []
    stale = False
    errors = []
    updated_at = None

    if not entries:
        return {
            "enabled": True,
            "available": False,
            "items": [],
            "message": "Nessun indice selezionato",
            "partial": False,
            "stale": False,
            "updatedAt": now_iso(),
        }

    for entry in entries:
        result = await load_index(entry)
        if result.get("available"):
            items.append(result)
            updated_at = max_text(updated_at, result.get("updatedAt"))
            stale = stale or bool(result.get("stale"))
        else:
            errors.append(result)

    if items:
        return {
            "enabled": True,
            "available": True,
            "items": items,
            "message": "Dati mercato parziali" if errors else "",
            "partial": bool(errors),
            "stale": stale,
            "updatedAt": updated_at or now_iso(),
        }

    return {
        "enabled": True,
        "available": False,
        "items": [],
        "message": "Mercati non disponibili",
        "partial": False,
        "stale": False,
        "updatedAt": now_iso(),
    }


async def load_index(entry):
    symbol = normalize_symbol(entry.get("symbol"))
    label = clean_label(entry.get("label") or common_label(symbol))
    cached = read_cache(symbol)
    if cached and cache_is_fresh(cached):
        return cached_payload(cached, label)

    try:
        payload = await fetch_index(symbol, label)
    except (httpx.HTTPError, ValueError):
        fallback = cached_payload(cached, label, stale=True)
        if fallback:
            return fallback
        return unavailable(symbol, label)

    write_cache(symbol, payload)
    return payload


async def fetch_index(symbol, label):
    params = urlencode({"s": symbol, "f": STOOQ_FIELDS, "h": "", "e": "csv"})
    url = settings.market_base_url + "?" + params
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "text/csv,*/*",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        return normalize_quote(symbol, label, response.text)


def normalize_quote(symbol, label, text):
    rows = list(csv.DictReader(io.StringIO(str(text or ""))))
    if len(rows) != 1:
        raise ValueError("Malformed market response")

    row = rows[0]
    close = parse_number(row.get("Close"))
    previous = parse_number(row.get("Prev"))
    if close is None or previous is None or previous == 0:
        raise ValueError("Market quote unavailable")

    change = close - previous
    percent = (change / previous) * 100
    date_text = clean_text(row.get("Date"))
    time_text = clean_text(row.get("Time"))
    return {
        "symbol": symbol,
        "label": clean_label(label),
        "value": round(close, 2),
        "previous": round(previous, 2),
        "change": round(change, 2),
        "changePercent": round(percent, 2),
        "direction": direction_for(change),
        "date": "" if date_text == "N/D" else date_text,
        "time": "" if time_text == "N/D" else time_text,
        "updatedAt": now_iso(),
        "available": True,
    }


def parse_number(value):
    text = clean_text(value)
    if not text or text == "N/D":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def clean_text(value):
    return str(value or "").strip()


def direction_for(change):
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def unavailable(symbol, label):
    return {
        "symbol": symbol,
        "label": clean_label(label),
        "available": False,
        "message": "Indice non disponibile",
        "updatedAt": now_iso(),
    }


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_timestamp(value):
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def cache_is_fresh(entry):
    try:
        fetched_at = parse_timestamp(entry.get("fetchedAt"))
    except Exception:
        return False
    ttl = max(0, settings.market_cache_ttl_ms) / 1000.0
    return datetime.now(timezone.utc) - fetched_at <= timedelta(seconds=ttl)


def cached_payload(entry, label, stale=False):
    if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict):
        return None
    payload = dict(entry["payload"])
    payload["label"] = clean_label(label)
    if stale:
        payload["stale"] = True
    return payload


def read_cache(symbol):
    path = settings.market_cache_path
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except Exception:
        return None
    entry = cache.get(symbol) if isinstance(cache, dict) else None
    return entry if isinstance(entry, dict) else None


def write_cache(symbol, payload):
    path = settings.market_cache_path
    path.parent.mkdir(parents=True, exist_ok=True)
    cache = {}
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
                if isinstance(loaded, dict):
                    cache = loaded
        except Exception:
            cache = {}
    cache[symbol] = {
        "fetchedAt": now_iso(),
        "payload": payload,
    }
    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def max_text(left, right):
    if not left:
        return right
    if not right:
        return left
    return max(left, right)
