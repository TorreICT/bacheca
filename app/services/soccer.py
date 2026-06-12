import json
import hashlib
import mimetypes
import os
import tempfile
from datetime import timedelta
from urllib.parse import quote, urlencode, urlparse

import httpx

from app.config import settings
from app.services import bar_widget


COMPETITIONS = {
    "WC": "FIFA World Cup",
    "EC": "European Championship",
    "SA": "Serie A",
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL": "Champions League",
    "EL": "Europa League",
}
COMPETITIONS_CACHE_KEY = "__competitions__"
BAR_MATCH_WINDOW_DAYS = 30
BAR_MATCH_TOTAL_LIMIT = 4
BAR_RESULT_TARGET = 2
BAR_FIXTURE_TARGET = 2
LIVE_REFRESH_LOOKBACK = timedelta(hours=4)
LIVE_REFRESH_LOOKAHEAD = timedelta(minutes=15)
MATCH_CACHE_VERSION = "v6"
BADGE_HOST = "crests.football-data.org"
BADGE_MAX_BYTES = 1024 * 1024


def competition_label(code):
    normalized = normalize_competition(code)
    return COMPETITIONS.get(normalized, normalized)


def competition_choices():
    return [{"code": code, "label": label, "source": "fallback"} for code, label in sorted(COMPETITIONS.items(), key=lambda item: item[1])]


async def load_competition_choices():
    cached = read_cache(COMPETITIONS_CACHE_KEY)
    if cached and cache_is_fresh(cached):
        choices = cached.get("payload")
        if isinstance(choices, list) and choices:
            return choices

    if settings.soccer_provider.strip().lower() != "football-data" or not settings.soccer_api_token:
        return competition_choices()

    try:
        choices = await fetch_competition_choices()
    except Exception:
        if cached and isinstance(cached.get("payload"), list) and cached["payload"]:
            return cached["payload"]
        return competition_choices()

    if choices:
        write_cache(COMPETITIONS_CACHE_KEY, choices)
        return choices
    return competition_choices()


def normalize_competition(code):
    value = str(code or "SA").strip().upper()
    if not value:
        return "SA"
    return value[:16]


async def load_compact(competition):
    code = normalize_competition(competition)
    cache_key = match_cache_key(code)
    cached = read_cache(cache_key)
    legacy_cached = read_cache(code)
    fallback_cached = cached or legacy_cached

    if settings.soccer_provider.strip().lower() != "football-data":
        return unavailable(code, "Soccer provider not supported", fallback_cached)

    if not settings.soccer_api_token:
        return unavailable(code, "Soccer API token missing", fallback_cached)

    if cached and cache_is_fresh(cached):
        return cached["payload"]

    try:
        payload = await fetch_compact(code)
    except Exception as error:
        return unavailable(code, str(error) or "Soccer unavailable", fallback_cached)

    write_cache(cache_key, payload)
    return payload


def match_cache_key(code):
    return (
        normalize_competition(code)
        + ":"
        + MATCH_CACHE_VERSION
        + ":bar:w"
        + str(BAR_MATCH_WINDOW_DAYS)
        + ":t"
        + str(BAR_MATCH_TOTAL_LIMIT)
        + ":r"
        + str(BAR_RESULT_TARGET)
        + ":f"
        + str(BAR_FIXTURE_TARGET)
    )


async def fetch_compact(code):
    start = bar_widget.now().date() - timedelta(days=BAR_MATCH_WINDOW_DAYS)
    end = bar_widget.now().date() + timedelta(days=BAR_MATCH_WINDOW_DAYS)
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


async def fetch_competition_choices():
    base_url = settings.soccer_base_url.rstrip("/")
    url = base_url + "/competitions"

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

    return normalize_competition_choices(body)


def normalize_competition_choices(body):
    competitions = body.get("competitions") if isinstance(body, dict) else []
    choices = []
    seen = set()

    for item in competitions or []:
        if not isinstance(item, dict):
            continue
        raw_code = str(item.get("code") or "").strip().upper()
        if not raw_code:
            continue
        code = normalize_competition(raw_code)
        if not code or code in seen:
            continue
        name = str(item.get("name") or COMPETITIONS.get(code) or code).strip()
        area = item.get("area") if isinstance(item.get("area"), dict) else {}
        area_name = str(area.get("name") or "").strip()
        label = name
        if area_name and area_name.lower() not in name.lower():
            label = area_name + " - " + name
        choices.append(
            {
                "code": code,
                "label": label[:48],
                "source": "football-data",
            }
        )
        seen.add(code)

    choices.sort(key=lambda choice: choice["label"])

    fallback = competition_choices()
    for choice in fallback:
        if choice["code"] not in seen:
            choices.append(choice)
            seen.add(choice["code"])

    return choices


def normalize_matches(code, body):
    matches = body.get("matches") if isinstance(body, dict) else []
    current = bar_widget.now()
    results = []
    fixtures = []

    for match in matches or []:
        item = normalize_match(match, current)
        if not item:
            continue
        if item["kind"] == "result":
            results.append(item)
        elif item["kind"] == "fixture":
            fixtures.append(item)

    results.sort(key=lambda item: item["sortAt"], reverse=True)
    fixtures.sort(key=lambda item: (0 if item.get("live") else 1, item["sortAt"]))

    results, fixtures = select_balanced_matches(results, fixtures)
    results.sort(key=lambda item: item["sortAt"])
    items = results + live_matches(fixtures) + non_live_matches(fixtures)

    for item in results + fixtures + items:
        item.pop("sortAt", None)

    return {
        "enabled": True,
        "available": True,
        "competition": code,
        "label": competition_label(code),
        "results": results,
        "fixtures": fixtures,
        "items": items,
        "updatedAt": bar_widget.isoformat(current),
    }


def select_balanced_matches(results, fixtures):
    live = live_matches(fixtures)
    upcoming = non_live_matches(fixtures)
    selected_live = live[:BAR_MATCH_TOTAL_LIMIT]
    remaining = BAR_MATCH_TOTAL_LIMIT - len(selected_live)

    if remaining <= 0:
        return [], selected_live

    result_target, upcoming_target = completion_targets(len(selected_live))
    result_limit = min(result_target, len(results))
    upcoming_limit = min(upcoming_target, len(upcoming))

    while result_limit + upcoming_limit < remaining:
        if result_limit < result_target and upcoming_limit < len(upcoming):
            upcoming_limit += 1
        elif upcoming_limit < upcoming_target and result_limit < len(results):
            result_limit += 1
        elif result_limit < len(results):
            result_limit += 1
        elif upcoming_limit < len(upcoming):
            upcoming_limit += 1
        else:
            break

    return results[:result_limit], selected_live + upcoming[:upcoming_limit]


def completion_targets(live_count):
    if live_count >= 3:
        return 1, 0
    if live_count == 2:
        return 1, 1
    if live_count == 1:
        return 2, 1
    return BAR_RESULT_TARGET, BAR_FIXTURE_TARGET


def live_matches(fixtures):
    return [item for item in fixtures if item.get("live")]


def non_live_matches(fixtures):
    return [item for item in fixtures if not item.get("live")]


def normalize_match(match, current):
    if not isinstance(match, dict):
        return None
    match_time = parse_match_time(match.get("utcDate"))
    if not match_time:
        return None

    home = normalize_team(match.get("homeTeam"))
    away = normalize_team(match.get("awayTeam"))
    if not home or not away:
        return None

    status = str(match.get("status") or "").upper()
    live = status in ("IN_PLAY", "PAUSED", "LIVE")
    minute = normalize_match_number(match.get("minute"))
    injury_time = normalize_match_number(match.get("injuryTime"))
    score = match.get("score") if isinstance(match.get("score"), dict) else {}
    full_time = score.get("fullTime") if isinstance(score.get("fullTime"), dict) else {}
    penalties = score.get("penalties") if isinstance(score.get("penalties"), dict) else {}
    stage_label = soccer_stage_label(match)

    if status in ("FINISHED", "AWARDED"):
        home_score = full_time.get("home")
        away_score = full_time.get("away")
        if home_score is None or away_score is None:
            return None
        return {
            "kind": "result",
            "dateLabel": format_match_date(match_time, include_time=False),
            "displayDate": format_match_date(match_time, include_time=False),
            "displayTime": format_match_time(match_time),
            "time": bar_widget.isoformat(match_time),
            "status": status,
            "stageLabel": stage_label,
            "minute": minute,
            "injuryTime": injury_time,
            "live": False,
            "home": home,
            "away": away,
            "score": {
                "home": home_score,
                "away": away_score,
            },
            "penalties": normalize_penalties(penalties),
            "text": format_match_date(match_time, include_time=False) + " " + home["abbr"] + " " + str(home_score) + "-" + str(away_score) + " " + away["abbr"],
            "sortAt": match_time,
        }

    if status in ("SCHEDULED", "TIMED", "IN_PLAY", "PAUSED", "LIVE"):
        if not live and match_time < current - timedelta(hours=4):
            return None
        return {
            "kind": "fixture",
            "dateLabel": format_match_date(match_time, include_time=True),
            "displayDate": format_match_date(match_time, include_time=False),
            "displayTime": format_match_time(match_time),
            "time": bar_widget.isoformat(match_time),
            "status": status,
            "stageLabel": stage_label,
            "minute": minute,
            "injuryTime": injury_time,
            "live": live,
            "home": home,
            "away": away,
            "score": normalize_score(full_time),
            "text": format_match_date(match_time, include_time=True) + " " + home["abbr"] + " vs " + away["abbr"],
            "sortAt": match_time,
        }

    return None


def parse_match_time(value):
    try:
        return bar_widget.parse_datetime(value)
    except Exception:
        return None


def normalize_team(team):
    if not isinstance(team, dict):
        return None
    name = ""
    for key in ("shortName", "tla", "name"):
        value = str(team.get(key) or "").strip()
        if value:
            name = value
            break
    if not name:
        return None
    full_name = str(team.get("name") or name).strip()
    short_name = str(team.get("shortName") or name).strip()
    abbr = str(team.get("tla") or "").strip().upper()
    if not abbr:
        abbr = short_name.replace(" ", "")[:3].upper()
    badge_source = safe_badge_source(team.get("crest") or team.get("flag"))
    return {
        "name": full_name,
        "shortName": short_name,
        "abbr": abbr,
        "badgeUrl": badge_proxy_url(badge_source) if badge_source else "",
    }


def format_match_date(match_time, include_time):
    local = match_time.astimezone(bar_widget.timezone())
    if include_time:
        return local.strftime("%d/%m %H:%M")
    return local.strftime("%d/%m")


def format_match_time(match_time):
    return match_time.astimezone(bar_widget.timezone()).strftime("%H:%M")


def normalize_match_number(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def normalize_score(score):
    if not isinstance(score, dict):
        return None
    home = score.get("home")
    away = score.get("away")
    if home is None or away is None:
        return None
    return {
        "home": home,
        "away": away,
    }


def normalize_penalties(penalties):
    if not isinstance(penalties, dict):
        return None
    home = penalties.get("homeTeam")
    away = penalties.get("awayTeam")
    if home is None or away is None:
        return None
    return {
        "home": home,
        "away": away,
    }


def soccer_stage_label(match):
    parts = []
    stage = clean_label(match.get("stage"))
    group = clean_label(match.get("group"))
    matchday = normalize_match_number(match.get("matchday"))
    if stage:
        parts.append(stage)
    if group:
        parts.append(group)
    if matchday is not None:
        parts.append("Giornata " + str(matchday))
    return " - ".join(parts)[:40]


def clean_label(value):
    text = str(value or "").replace("_", " ").strip()
    if not text:
        return ""
    return " ".join(part.capitalize() for part in text.split())[:40]


def unavailable(code, message, cached=None):
    if cached and cached.get("payload"):
        payload = dict(cached["payload"])
        payload.setdefault("results", [])
        payload.setdefault("fixtures", [])
        payload.setdefault("items", [])
        payload["stale"] = True
        payload["message"] = message
        return payload
    return {
        "enabled": True,
        "available": False,
        "competition": code,
        "label": competition_label(code),
        "results": [],
        "fixtures": [],
        "items": [],
        "message": message,
    }


def safe_badge_source(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or parsed.netloc.lower() != BADGE_HOST:
        return ""
    if not parsed.path or parsed.path.endswith("/"):
        return ""
    return text


def badge_proxy_url(source):
    return "/api/soccer/badge?src=" + quote(source, safe="")


def badge_cache_path(source):
    safe_source = safe_badge_source(source)
    if not safe_source:
        return None
    parsed = urlparse(safe_source)
    extension = os.path.splitext(parsed.path)[1].lower()
    if extension not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        extension = ".img"
    name = hashlib.sha1(safe_source.encode("utf-8")).hexdigest() + extension
    return settings.soccer_badge_cache_dir / name


def badge_media_type(path):
    media_type, _ = mimetypes.guess_type(str(path))
    return media_type or "application/octet-stream"


async def badge_file(source):
    safe_source = safe_badge_source(source)
    if not safe_source:
        return None, ""
    path = badge_cache_path(safe_source)
    if not path:
        return None, ""
    if path.exists():
        return path, badge_media_type(path)

    settings.soccer_badge_cache_dir.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            safe_source,
            headers={
                "Accept": "image/*",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        body = response.content
    if len(body) > BADGE_MAX_BYTES:
        return None, ""

    fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return path, badge_media_type(path)


def cache_is_fresh(entry):
    try:
        fetched_at = bar_widget.parse_datetime(entry.get("fetchedAt"))
    except Exception:
        return False
    if payload_needs_live_refresh(entry.get("payload")):
        return False
    ttl = max(0, settings.soccer_cache_ttl_ms) / 1000.0
    return bar_widget.now() - fetched_at <= timedelta(seconds=ttl)


def payload_needs_live_refresh(payload):
    current = bar_widget.now()
    if not isinstance(payload, dict):
        return False
    for item in cached_fixture_items(payload):
        if item.get("live"):
            return True
        try:
            match_time = bar_widget.parse_datetime(item.get("time"))
        except Exception:
            continue
        if current - LIVE_REFRESH_LOOKBACK <= match_time <= current + LIVE_REFRESH_LOOKAHEAD:
            return True
    return False


def cached_fixture_items(payload):
    fixtures = []
    for key in ("fixtures", "items"):
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("kind") != "result":
                fixtures.append(item)
    return fixtures


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
