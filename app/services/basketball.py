import json
import hashlib
import mimetypes
import os
import tempfile
from datetime import datetime, timedelta, timezone as datetime_timezone
from urllib.parse import quote, urlencode, urlparse

import httpx

from app.config import settings
from app.services import bar_widget


COMPETITIONS_CACHE_KEY = "__leagues__"
BAR_RESULT_TARGET = 2
BAR_FIXTURE_TARGET = 2
MATCH_CACHE_VERSION = "v2"
BADGE_MAX_BYTES = 1024 * 1024
THESPORTSDB_FREE_KEY = "123"
THESPORTSDB_BASE_URL = "https://www.thesportsdb.com/api/v1/json"
API_SPORTS_BASE_URL = "https://v1.basketball.api-sports.io"
BADGE_HOSTS = ("media.api-sports.io", "www.thesportsdb.com", "thesportsdb.com", "r2.thesportsdb.com")
FINISHED_STATUSES = ("FT", "AOT", "AWD")
LIVE_STATUSES = ("Q1", "Q2", "Q3", "Q4", "OT", "BT", "HT", "LIVE")
SCHEDULED_STATUSES = ("NS", "")
SKIPPED_STATUSES = ("PST", "CANC", "SUSP", "ABD", "POST", "CANCELLED", "SUSPENDED", "ABANDONED")


COMMON_THESPORTSDB_COMPETITIONS = [
    {"code": "4387", "label": "United States - NBA", "source": "thesportsdb-fallback"},
    {"code": "5506", "label": "United States - NBA Cup", "source": "thesportsdb-fallback"},
    {"code": "4433", "label": "Italy - Italian Lega Basket", "source": "thesportsdb-fallback"},
    {"code": "4408", "label": "Spain - Spanish Liga ACB", "source": "thesportsdb-fallback"},
    {"code": "4548", "label": "Europe - Basketball Champions League", "source": "thesportsdb-fallback"},
    {"code": "4547", "label": "Europe - EuroCup Basketball", "source": "thesportsdb-fallback"},
    {"code": "4477", "label": "Europe - Adriatic ABA League", "source": "thesportsdb-fallback"},
    {"code": "4434", "label": "Australia - Australian NBL", "source": "thesportsdb-fallback"},
    {"code": "4475", "label": "Turkey - Basketbol Super Ligi", "source": "thesportsdb-fallback"},
]


def provider_name():
    value = str(settings.basketball_provider or "").strip().lower()
    if value in ("the-sports-db", "thesportsdb", "sportsdb", "the sports db"):
        return "thesportsdb"
    if value in ("api-sports", "apisports"):
        return "api-sports"
    return "thesportsdb"


def default_season():
    configured = str(settings.basketball_default_season or "").strip()
    if configured:
        return configured[:16]
    current = bar_widget.now()
    if current.month >= 8:
        return str(current.year) + "-" + str(current.year + 1)
    return str(current.year - 1) + "-" + str(current.year)


def normalize_competition(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:32]


def normalize_season(value):
    text = str(value or "").strip()
    if not text:
        return default_season()
    return text[:16]


def competition_label(code, season=None):
    normalized = normalize_competition(code)
    if not normalized:
        return "Basket"

    for choice in COMMON_THESPORTSDB_COMPETITIONS:
        if choice["code"] == normalized:
            return choice["label"]

    cached = read_cache(COMPETITIONS_CACHE_KEY)
    choices = cached.get("payload") if cached else None
    if isinstance(choices, list):
        for choice in choices:
            if str(choice.get("code") or "") == normalized:
                return str(choice.get("label") or normalized)

    if season:
        return "League " + normalized + " (" + normalize_season(season) + ")"
    return "League " + normalized


async def load_competition_choices(season=None):
    provider = provider_name()
    selected_season = normalize_season(season)
    cache_key = provider + ":" + COMPETITIONS_CACHE_KEY + ":" + selected_season
    cached = read_cache(cache_key)
    legacy_cached = read_cache(COMPETITIONS_CACHE_KEY)
    fallback_cached = cached or legacy_cached

    if cached and cache_is_fresh(cached):
        choices = cached.get("payload")
        if isinstance(choices, list) and choices:
            return choices

    if provider == "api-sports" and not settings.basketball_api_token:
        if fallback_cached and isinstance(fallback_cached.get("payload"), list):
            return fallback_cached["payload"]
        return []

    try:
        choices = await fetch_competition_choices(provider, selected_season)
    except Exception:
        if fallback_cached and isinstance(fallback_cached.get("payload"), list):
            return fallback_cached["payload"]
        if provider == "thesportsdb":
            return common_tsd_choices(selected_season)
        return []

    if choices:
        write_cache(cache_key, choices)
        write_cache(COMPETITIONS_CACHE_KEY, choices)
    return choices


async def load_compact(competition, season=None):
    provider = provider_name()
    code = normalize_competition(competition)
    selected_season = normalize_season(season)
    cache_key = provider + ":" + match_cache_key(code, selected_season)
    cached = read_cache(cache_key)

    if not code:
        return unavailable(code, selected_season, "Basket competition missing", cached)

    if provider not in ("thesportsdb", "api-sports"):
        return unavailable(code, selected_season, "Basketball provider not supported", cached)

    if provider == "api-sports" and not settings.basketball_api_token:
        return unavailable(code, selected_season, "Basketball API token missing", cached)

    if cached and cache_is_fresh(cached):
        return cached["payload"]

    try:
        payload = await fetch_compact(provider, code, selected_season)
    except Exception as error:
        return unavailable(code, selected_season, str(error) or "Basketball unavailable", cached)

    write_cache(cache_key, payload)
    return payload


def match_cache_key(code, season):
    return (
        normalize_competition(code)
        + ":"
        + normalize_season(season)
        + ":"
        + MATCH_CACHE_VERSION
        + ":bar:w"
        + str(settings.basketball_lookback_days)
        + ":"
        + str(settings.basketball_lookahead_days)
        + ":t"
        + str(settings.basketball_max_items)
        + ":r"
        + str(BAR_RESULT_TARGET)
        + ":f"
        + str(BAR_FIXTURE_TARGET)
    )


async def fetch_compact(provider, code, season):
    if provider == "api-sports":
        return await fetch_api_sports_compact(code, season)
    return await fetch_tsd_compact(code, season)


async def fetch_competition_choices(provider, season):
    if provider == "api-sports":
        return await fetch_api_sports_competition_choices(season)
    return await fetch_tsd_competition_choices(season)


async def fetch_tsd_compact(code, season):
    params = {"id": code}
    base_url = tsd_base_url()
    key = tsd_api_key()
    urls = [
        base_url + "/" + key + "/eventspastleague.php?" + urlencode(params),
        base_url + "/" + key + "/eventsnextleague.php?" + urlencode(params),
    ]
    events = []

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        for url in urls:
            response = await client.get(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Torrescalla-Bacheca/2.0",
                },
            )
            response.raise_for_status()
            body = response.json()
            events.extend(array_from_body(body, "events"))

    return normalize_tsd_events(code, season, events)


async def fetch_tsd_competition_choices(season):
    url = tsd_base_url() + "/" + tsd_api_key() + "/search_all_leagues.php?" + urlencode({"s": "Basketball"})

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        body = response.json()

    return merge_choices(normalize_tsd_competition_choices(body, season), common_tsd_choices(season))


def normalize_tsd_competition_choices(body, season):
    leagues = array_from_body(body, "countries")
    choices = []
    for item in leagues:
        if not isinstance(item, dict):
            continue
        code = normalize_competition(item.get("idLeague"))
        if not code:
            continue
        label = tsd_league_label(item)
        choices.append(
            {
                "code": code,
                "label": label[:48],
                "season": normalize_season(item.get("strCurrentSeason") or season),
                "source": "thesportsdb",
            }
        )
    choices.sort(key=lambda choice: choice["label"])
    return choices


def common_tsd_choices(season):
    selected_season = normalize_season(season)
    choices = []
    for item in COMMON_THESPORTSDB_COMPETITIONS:
        choice = dict(item)
        choice["season"] = selected_season
        choices.append(choice)
    return choices


def merge_choices(primary, fallback):
    choices = []
    seen = set()
    for group in (primary or [], fallback or []):
        for item in group:
            code = normalize_competition(item.get("code"))
            if not code or code in seen:
                continue
            choice = dict(item)
            choice["code"] = code
            choices.append(choice)
            seen.add(code)
    choices.sort(key=lambda choice: str(choice.get("label") or choice.get("code") or ""))
    return choices


def tsd_league_label(item):
    name = str(item.get("strLeague") or item.get("idLeague") or "").strip()
    country = str(item.get("strCountry") or "").strip()
    if country and country.lower() not in name.lower():
        return country + " - " + name
    return name


def normalize_tsd_events(code, season, events):
    current = bar_widget.now()
    start = current - timedelta(days=settings.basketball_lookback_days)
    end = current + timedelta(days=settings.basketball_lookahead_days)
    results = []
    fixtures = []

    for event in events or []:
        item = normalize_tsd_event(event, current, start, end, season)
        if not item:
            continue
        if item["kind"] == "result":
            results.append(item)
        elif item["kind"] == "fixture":
            fixtures.append(item)

    results.sort(key=lambda item: item["sortAt"])
    fixtures.sort(key=lambda item: (0 if item.get("live") else 1, item["sortAt"]))

    results, fixtures = select_balanced_games(results, fixtures)
    items = live_games(fixtures) + results + non_live_games(fixtures)

    for item in results + fixtures + items:
        item.pop("sortAt", None)

    return {
        "enabled": True,
        "available": True,
        "competition": normalize_competition(code),
        "season": normalize_season(season),
        "label": tsd_event_competition_label(code, season, events),
        "results": results,
        "fixtures": fixtures,
        "items": items,
        "updatedAt": bar_widget.isoformat(current),
    }


def normalize_tsd_event(event, current, start, end, season):
    if not isinstance(event, dict):
        return None

    match_time = parse_tsd_event_time(event)
    if not match_time:
        return None
    if match_time < start or match_time > end:
        return None

    event_season = str(event.get("strSeason") or "").strip()
    selected_season = normalize_season(season)
    if event_season and selected_season and event_season != selected_season:
        return None

    status = normalize_status(event.get("strStatus"))
    postponed = str(event.get("strPostponed") or "").strip().lower() == "yes"
    if status in SKIPPED_STATUSES or (postponed and status not in FINISHED_STATUSES):
        return None

    home = normalize_tsd_team(event, "home")
    away = normalize_tsd_team(event, "away")
    if not home or not away:
        return None

    home_score = normalize_number(event.get("intHomeScore"))
    away_score = normalize_number(event.get("intAwayScore"))
    live = status in LIVE_STATUSES

    if status in FINISHED_STATUSES:
        if home_score is None or away_score is None:
            return None
        return match_payload("result", match_time, status, "", False, home, away, home_score, away_score, tsd_stage_label(event))

    if status in SCHEDULED_STATUSES or live:
        if not live and match_time < current - timedelta(hours=4):
            return None
        return match_payload("fixture", match_time, status or "NS", status if live else "", live, home, away, home_score, away_score, tsd_stage_label(event))

    return None


def normalize_tsd_team(event, side):
    prefix = "Home" if side == "home" else "Away"
    name = str(event.get("str" + prefix + "Team") or "").strip()
    if not name:
        return None
    abbr = name.replace(" ", "")[:3].upper()
    badge_source = safe_badge_source(event.get("str" + prefix + "TeamBadge"))
    return {
        "name": name,
        "shortName": name,
        "abbr": abbr,
        "badgeUrl": badge_proxy_url(badge_source) if badge_source else "",
    }


def match_payload(kind, match_time, status, period, live, home, away, home_score, away_score, stage_label=""):
    score = normalize_score(home_score, away_score)
    return {
        "kind": kind,
        "dateLabel": format_game_date(match_time, include_time=(kind != "result")),
        "displayDate": format_game_date(match_time, include_time=False),
        "displayTime": format_game_time(match_time),
        "time": bar_widget.isoformat(match_time),
        "status": status,
        "statusLabel": status,
        "stageLabel": stage_label,
        "period": period,
        "live": bool(live),
        "home": home,
        "away": away,
        "score": score,
        "text": match_text(kind, match_time, home, away, score),
        "sortAt": match_time,
    }


def match_text(kind, match_time, home, away, score):
    if kind == "result" and score:
        return format_game_date(match_time, include_time=False) + " " + home["abbr"] + " " + str(score["home"]) + "-" + str(score["away"]) + " " + away["abbr"]
    return format_game_date(match_time, include_time=True) + " " + home["abbr"] + " vs " + away["abbr"]


def live_games(fixtures):
    return [item for item in fixtures if item.get("live")]


def non_live_games(fixtures):
    return [item for item in fixtures if not item.get("live")]


def tsd_stage_label(event):
    for key in ("strRound", "strStage", "strGroup"):
        label = clean_label(event.get(key))
        if label:
            return label
    return ""


def tsd_event_competition_label(code, season, events):
    for event in events or []:
        if not isinstance(event, dict):
            continue
        name = str(event.get("strLeague") or "").strip()
        if name:
            return name[:48]
    return competition_label(code, season)


def parse_tsd_event_time(event):
    timestamp = str(event.get("strTimestamp") or "").strip()
    if timestamp:
        try:
            parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=datetime_timezone.utc)
            return parsed.astimezone(bar_widget.timezone()).replace(microsecond=0)
        except Exception:
            pass

    date_text = str(event.get("dateEventLocal") or event.get("dateEvent") or "").strip()
    time_text = str(event.get("strTimeLocal") or event.get("strTime") or "00:00:00").strip() or "00:00:00"
    try:
        return bar_widget.parse_datetime(date_text + "T" + time_text)
    except Exception:
        return None


async def fetch_api_sports_compact(code, season):
    params = urlencode(
        {
            "league": code,
            "season": season,
            "timezone": settings.timezone,
        }
    )
    url = api_sports_base_url() + "/games?" + params

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
                "x-apisports-key": settings.basketball_api_token,
            },
        )
        response.raise_for_status()
        body = response.json()

    return normalize_api_sports_games(code, season, body)


async def fetch_api_sports_competition_choices(season):
    params = urlencode({"season": season}) if season else ""
    url = api_sports_base_url() + "/leagues" + ("?" + params if params else "")

    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
                "x-apisports-key": settings.basketball_api_token,
            },
        )
        response.raise_for_status()
        body = response.json()

    return normalize_api_sports_competition_choices(body, season)


def normalize_api_sports_competition_choices(body, season):
    leagues = array_from_body(body, "response")
    choices = []
    seen = set()

    for item in leagues:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        if raw_id is None:
            continue
        code = normalize_competition(raw_id)
        if not code or code in seen:
            continue
        name = str(item.get("name") or code).strip()
        country = item.get("country") if isinstance(item.get("country"), dict) else {}
        country_name = str(country.get("name") or "").strip()
        label = name
        if country_name and country_name.lower() not in name.lower():
            label = country_name + " - " + name
        choices.append(
            {
                "code": code,
                "label": label[:48],
                "season": normalize_season(season),
                "source": "api-sports",
            }
        )
        seen.add(code)

    choices.sort(key=lambda choice: choice["label"])
    return choices


def normalize_api_sports_games(code, season, body):
    games = array_from_body(body, "response")
    current = bar_widget.now()
    results = []
    fixtures = []
    start = current - timedelta(days=settings.basketball_lookback_days)
    end = current + timedelta(days=settings.basketball_lookahead_days)

    for game in games:
        item = normalize_api_sports_game(game, current, start, end)
        if not item:
            continue
        if item["kind"] == "result":
            results.append(item)
        elif item["kind"] == "fixture":
            fixtures.append(item)

    results.sort(key=lambda item: item["sortAt"])
    fixtures.sort(key=lambda item: (0 if item.get("live") else 1, item["sortAt"]))

    results, fixtures = select_balanced_games(results, fixtures)
    items = live_games(fixtures) + results + non_live_games(fixtures)

    for item in results + fixtures + items:
        item.pop("sortAt", None)

    return {
        "enabled": True,
        "available": True,
        "competition": normalize_competition(code),
        "season": normalize_season(season),
        "label": api_sports_competition_label(code, season, games),
        "results": results,
        "fixtures": fixtures,
        "items": items,
        "updatedAt": bar_widget.isoformat(current),
    }


def api_sports_competition_label(code, season, games):
    for game in games or []:
        if not isinstance(game, dict):
            continue
        league = game.get("league") if isinstance(game.get("league"), dict) else {}
        name = str(league.get("name") or "").strip()
        if name:
            country = game.get("country") if isinstance(game.get("country"), dict) else {}
            country_name = str(country.get("name") or "").strip()
            if country_name and country_name.lower() not in name.lower():
                return (country_name + " - " + name)[:48]
            return name[:48]
    return competition_label(code, season)


def select_balanced_games(results, fixtures):
    total_limit = max(1, settings.basketball_max_items)
    result_limit = min(BAR_RESULT_TARGET, len(results))
    fixture_limit = min(BAR_FIXTURE_TARGET, len(fixtures))

    while result_limit + fixture_limit < total_limit:
        if result_limit < BAR_RESULT_TARGET and fixture_limit < len(fixtures):
            fixture_limit += 1
        elif fixture_limit < BAR_FIXTURE_TARGET and result_limit < len(results):
            result_limit += 1
        elif fixture_limit < len(fixtures):
            fixture_limit += 1
        elif result_limit < len(results):
            result_limit += 1
        else:
            break

    return results[:result_limit], fixtures[:fixture_limit]


def normalize_api_sports_game(game, current, start, end):
    if not isinstance(game, dict):
        return None

    match_time = parse_api_sports_game_time(game.get("date"))
    if not match_time:
        return None
    if match_time < start or match_time > end:
        return None

    status = normalize_status(game.get("status"))
    if status in SKIPPED_STATUSES:
        return None

    home = normalize_api_sports_team(api_sports_team_side(game, "home"))
    away = normalize_api_sports_team(api_sports_team_side(game, "away"))
    if not home or not away:
        return None

    scores = game.get("scores") if isinstance(game.get("scores"), dict) else {}
    home_score = api_sports_team_score(scores, "home")
    away_score = api_sports_team_score(scores, "away")
    live = status in LIVE_STATUSES

    if status in FINISHED_STATUSES:
        if home_score is None or away_score is None:
            return None
        return match_payload("result", match_time, status, "", False, home, away, home_score, away_score, api_sports_stage_label(game))

    if status in SCHEDULED_STATUSES or live:
        if not live and match_time < current - timedelta(hours=4):
            return None
        return match_payload("fixture", match_time, status or "NS", status if live else "", live, home, away, home_score, away_score, api_sports_stage_label(game))

    return None


def api_sports_team_side(game, side):
    teams = game.get("teams") if isinstance(game.get("teams"), dict) else {}
    team = teams.get(side)
    return team if isinstance(team, dict) else {}


def api_sports_team_score(scores, side):
    score = scores.get(side)
    if isinstance(score, dict):
        return normalize_number(score.get("total") if score.get("total") is not None else score.get("points"))
    return normalize_number(score)


def api_sports_stage_label(game):
    league = game.get("league") if isinstance(game.get("league"), dict) else {}
    for source in (game, league):
        for key in ("round", "stage", "group"):
            label = clean_label(source.get(key))
            if label:
                return label
    return ""


def clean_label(value):
    text = str(value or "").replace("_", " ").strip()
    if not text:
        return ""
    return " ".join(part.capitalize() for part in text.split())[:40]


def normalize_status(value):
    if isinstance(value, dict):
        raw = value.get("short") or value.get("long") or ""
    else:
        raw = value
    return str(raw or "").strip().upper()


def parse_api_sports_game_time(value):
    raw = value
    if isinstance(value, dict):
        raw = value.get("date") or value.get("timestamp")
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(raw, tz=bar_widget.timezone())
        except Exception:
            return None
    try:
        return bar_widget.parse_datetime(raw)
    except Exception:
        return None


def normalize_api_sports_team(team):
    if not isinstance(team, dict):
        return None
    name = ""
    for key in ("code", "shortName", "name"):
        value = str(team.get(key) or "").strip()
        if value:
            name = value
            break
    if not name:
        return None
    full_name = str(team.get("name") or name).strip()
    short_name = str(team.get("shortName") or name).strip()
    abbr = str(team.get("code") or team.get("tla") or "").strip().upper()
    if not abbr:
        abbr = short_name.replace(" ", "")[:3].upper()
    badge_source = safe_badge_source(team.get("logo") or team.get("flag"))
    return {
        "name": full_name,
        "shortName": short_name,
        "abbr": abbr[:3],
        "badgeUrl": badge_proxy_url(badge_source) if badge_source else "",
    }


def normalize_number(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_score(home, away):
    if home is None or away is None:
        return None
    return {
        "home": home,
        "away": away,
    }


def format_game_date(match_time, include_time):
    local = match_time.astimezone(bar_widget.timezone())
    if include_time:
        return local.strftime("%d/%m %H:%M")
    return local.strftime("%d/%m")


def format_game_time(match_time):
    return match_time.astimezone(bar_widget.timezone()).strftime("%H:%M")


def unavailable(code, season, message, cached=None):
    normalized = normalize_competition(code)
    selected_season = normalize_season(season)
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
        "competition": normalized,
        "season": selected_season,
        "label": competition_label(normalized, selected_season),
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
    if parsed.scheme != "https" or parsed.netloc.lower() not in BADGE_HOSTS:
        return ""
    if not parsed.path or parsed.path.endswith("/"):
        return ""
    return text


def badge_proxy_url(source):
    return "/api/basketball/badge?src=" + quote(source, safe="")


def badge_cache_path(source):
    safe_source = safe_badge_source(source)
    if not safe_source:
        return None
    parsed = urlparse(safe_source)
    extension = os.path.splitext(parsed.path)[1].lower()
    if extension not in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
        extension = ".img"
    name = hashlib.sha1(safe_source.encode("utf-8")).hexdigest() + extension
    return settings.basketball_badge_cache_dir / name


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

    settings.basketball_badge_cache_dir.mkdir(parents=True, exist_ok=True)
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


def tsd_base_url():
    text = str(settings.basketball_base_url or "").strip().rstrip("/")
    if text and "api-sports" not in text:
        return text
    return THESPORTSDB_BASE_URL


def tsd_api_key():
    return quote(str(settings.basketball_api_token or "").strip() or THESPORTSDB_FREE_KEY, safe="")


def api_sports_base_url():
    text = str(settings.basketball_base_url or "").strip().rstrip("/")
    if text and "thesportsdb" not in text:
        return text
    return API_SPORTS_BASE_URL


def array_from_body(body, key):
    if not isinstance(body, dict):
        return []
    value = body.get(key)
    if isinstance(value, list):
        return value
    return []


def cache_is_fresh(entry):
    try:
        fetched_at = bar_widget.parse_datetime(entry.get("fetchedAt"))
    except Exception:
        return False
    if payload_needs_live_refresh(entry.get("payload")):
        return False
    ttl = max(0, settings.basketball_cache_ttl_ms) / 1000.0
    return bar_widget.now() - fetched_at <= timedelta(seconds=ttl)


def payload_needs_live_refresh(payload):
    current = bar_widget.now()
    if not isinstance(payload, dict):
        return False
    for item in payload.get("fixtures") or []:
        if not isinstance(item, dict):
            continue
        if item.get("live"):
            return True
        try:
            match_time = bar_widget.parse_datetime(item.get("time"))
        except Exception:
            continue
        if current - timedelta(hours=1) <= match_time <= current + timedelta(minutes=15):
            return True
    return False


def read_cache(code):
    path = settings.basketball_cache_path
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
    path = settings.basketball_cache_path
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
