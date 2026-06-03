import json
import os
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services import bar_widget


COMPETITIONS = {
    "SA": "Serie A",
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL": "Champions League",
    "EL": "Europa League",
}


def competition_label(code):
    normalized = normalize_competition(code)
    return COMPETITIONS.get(normalized, normalized)


def competition_choices():
    return [{"code": code, "label": label} for code, label in sorted(COMPETITIONS.items(), key=lambda item: item[1])]


def normalize_competition(code):
    value = str(code or "SA").strip().upper()
    if not value:
        return "SA"
    return value[:16]


async def load_compact(competition):
    code = normalize_competition(competition)
    cached = read_cache(code)

    if settings.soccer_provider.strip().lower() != "football-data":
        return unavailable(code, "Soccer provider not supported", cached)

    if not settings.soccer_api_token:
        return unavailable(code, "Soccer API token missing", cached)

    if cached and cache_is_fresh(cached):
        return cached["payload"]

    try:
        payload = await fetch_compact(code)
    except Exception as error:
        return unavailable(code, str(error) or "Soccer unavailable", cached)

    write_cache(code, payload)
    return payload


async def fetch_compact(code):
    start = bar_widget.now().date() - timedelta(days=max(0, settings.soccer_lookback_days))
    end = bar_widget.now().date() + timedelta(days=max(0, settings.soccer_lookahead_days))
    params = urlencode({"dateFrom": start.isoformat(), "dateTo": end.isoformat()})
    base_url = settings.soccer_base_url.rstrip("/")
    url = base_url + "/competitions/" + code + "/matches?" + params

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
                "X-Auth-Token": settings.soccer_api_token,
            },
        )
        response.raise_for_status()
        body = response.json()

    return normalize_matches(code, body)


def normalize_matches(code, body):
    matches = body.get("matches") if isinstance(body, dict) else []
    now = bar_widget.now()
    results = []
    fixtures = []
    max_items = max(1, settings.soccer_max_items)

    for match in matches or []:
        item = normalize_match(match, now)
        if not item:
            continue
        if item["kind"] == "result":
            results.append(item)
        else:
            fixtures.append(item)

    results.sort(key=lambda item: item["sortAt"], reverse=True)
    fixtures.sort(key=lambda item: item["sortAt"])

    items = results[:max_items]
    remaining = max_items - len(items)
    if remaining > 0:
        items.extend(fixtures[:remaining])

    for item in items:
        item.pop("sortAt", None)

    return {
        "enabled": True,
        "available": True,
        "competition": code,
        "label": competition_label(code),
        "items": items,
        "updatedAt": bar_widget.isoformat(now),
    }


def normalize_match(match, current):
    if not isinstance(match, dict):
        return None
    match_time = parse_match_time(match.get("utcDate"))
    if not match_time:
        return None

    home = team_name(match.get("homeTeam"))
    away = team_name(match.get("awayTeam"))
    if not home or not away:
        return None

    status = str(match.get("status") or "").upper()
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    full_time = score.get("fullTime") if isinstance(score.get("fullTime"), dict) else {}

    if status in ("FINISHED", "AWARDED"):
        home_score = full_time.get("home")
        away_score = full_time.get("away")
        if home_score is None or away_score is None:
            return None
        return {
            "kind": "result",
            "text": home + " " + str(home_score) + "-" + str(away_score) + " " + away,
            "time": bar_widget.isoformat(match_time),
            "sortAt": match_time,
        }

    if status in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "LIVE") and match_time >= current - timedelta(hours=4):
        return {
            "kind": "fixture",
            "text": fixture_prefix(match_time, current) + " " + home + "-" + away,
            "time": bar_widget.isoformat(match_time),
            "sortAt": match_time,
        }

    return None


def parse_match_time(value):
    try:
        return bar_widget.parse_datetime(value)
    except Exception:
        return None


def team_name(team):
    if not isinstance(team, dict):
        return ""
    for key in ("shortName", "tla", "name"):
        value = str(team.get(key) or "").strip()
        if value:
            return value
    return ""


def fixture_prefix(match_time, current):
    local = match_time.astimezone(bar_widget.timezone())
    today = current.date()
    if local.date() == today:
        return "Oggi " + local.strftime("%H:%M")
    if local.date() == today + timedelta(days=1):
        return "Domani " + local.strftime("%H:%M")
    return local.strftime("%d/%m %H:%M")


def unavailable(code, message, cached=None):
    if cached and cached.get("payload"):
        payload = dict(cached["payload"])
        payload["stale"] = True
        payload["message"] = message
        return payload
    return {
        "enabled": True,
        "available": False,
        "competition": code,
        "label": competition_label(code),
        "items": [],
        "message": message,
    }


def cache_is_fresh(entry):
    try:
        fetched_at = bar_widget.parse_datetime(entry.get("fetchedAt"))
    except Exception:
        return False
    ttl = max(0, settings.soccer_cache_ttl_ms) / 1000.0
    return bar_widget.now() - fetched_at <= timedelta(seconds=ttl)


def read_cache(code):
    path = settings.soccer_cache_path
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except Exception:
        return None
    entry = cache.get(code) if isinstance(cache, dict) else None
    return entry if isinstance(entry, dict) else None


def write_cache(code, payload):
    path = settings.soccer_cache_path
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
    cache[code] = {
        "fetchedAt": bar_widget.isoformat(bar_widget.now()),
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
