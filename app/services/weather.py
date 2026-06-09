import json
import os
import tempfile
from datetime import date, timedelta
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.services import bar_widget


CURRENT_FIELDS = frozenset(
    (
        "temperature_2m",
        "relative_humidity_2m",
        "apparent_temperature",
        "precipitation",
        "rain",
        "showers",
        "snowfall",
        "weather_code",
        "cloud_cover",
        "pressure_msl",
        "surface_pressure",
        "uv_index",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
    )
)

DAILY_FIELDS = frozenset(
    (
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "apparent_temperature_min",
        "sunrise",
        "sunset",
        "daylight_duration",
        "sunshine_duration",
        "uv_index_max",
        "uv_index_clear_sky_max",
        "precipitation_sum",
        "rain_sum",
        "showers_sum",
        "snowfall_sum",
        "precipitation_hours",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "wind_direction_10m_dominant",
    )
)

MAX_FORECAST_DAYS = 16
MAX_TIMEZONE_LENGTH = 80


class WeatherRequestError(Exception):
    pass


def build_forecast_url(latitude, longitude, timezone, start_date, end_date, current, daily):
    start, end = validate_dates(start_date, end_date)
    params = {
        "latitude": normalize_coordinate("latitude", latitude, -90, 90),
        "longitude": normalize_coordinate("longitude", longitude, -180, 180),
        "timezone": normalize_timezone(timezone),
        "start_date": start,
        "end_date": end,
        "current": normalize_fields("current", current, CURRENT_FIELDS),
        "daily": normalize_fields("daily", daily, DAILY_FIELDS),
    }
    return settings.weather_forecast_url + "?" + urlencode(params)


async def load_forecast(latitude, longitude, timezone, start_date, end_date, current, daily):
    url = build_forecast_url(latitude, longitude, timezone, start_date, end_date, current, daily)
    cached = read_cache(url)
    if cached and cache_is_fresh(cached):
        payload = cached_payload(cached)
        if payload and payload.get("location"):
            return payload
        if payload:
            payload = with_location(payload, await load_location(latitude, longitude, cached))
            write_cache(url, payload)
            return payload

    try:
        payload = await fetch_forecast(url)
    except (httpx.HTTPError, ValueError):
        fallback = cached_payload(cached, stale=True)
        if fallback:
            return fallback
        raise

    payload = with_location(payload, await load_location(latitude, longitude, cached))
    write_cache(url, payload)
    return payload


async def fetch_forecast(url):
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        return response.json()


async def load_location(latitude, longitude, cached):
    cached_location = None
    if isinstance(cached, dict) and isinstance(cached.get("payload"), dict):
        cached_location = cached["payload"].get("location")

    try:
        location = await fetch_location_name(latitude, longitude)
    except httpx.HTTPError:
        location = cached_location

    return location or fallback_location_name(latitude, longitude)


async def fetch_location_name(latitude, longitude):
    params = urlencode(
        {
            "format": "jsonv2",
            "lat": normalize_coordinate("latitude", latitude, -90, 90),
            "lon": normalize_coordinate("longitude", longitude, -180, 180),
            "zoom": "14",
            "addressdetails": "1",
            "accept-language": "it",
        }
    )
    url = settings.weather_reverse_geocode_url + "?" + params
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        return location_name_from_geocode(response.json())


def location_name_from_geocode(body):
    address = body.get("address") if isinstance(body, dict) else None
    if not isinstance(address, dict):
        return ""

    area = first_text(
        address,
        (
            "neighbourhood",
            "quarter",
            "suburb",
            "city_district",
            "borough",
            "municipality",
        ),
    )
    city = first_text(address, ("city", "town", "village", "hamlet", "county"))
    state = first_text(address, ("state", "region"))

    parts = []
    for value in (area, city, state):
        cleaned = compact_text(value)
        if cleaned and cleaned not in parts:
            parts.append(cleaned)

    return ", ".join(parts[:2])


def first_text(source, keys):
    for key in keys:
        value = source.get(key)
        if value:
            return value
    return ""


def compact_text(value):
    text = " ".join(str(value or "").split())
    return text[:80]


def fallback_location_name(latitude, longitude):
    return "%s, %s" % (
        normalize_coordinate("latitude", latitude, -90, 90),
        normalize_coordinate("longitude", longitude, -180, 180),
    )


def with_location(payload, location):
    if not isinstance(payload, dict):
        return payload
    copy = dict(payload)
    if location:
        copy["location"] = location
    return copy


def validate_dates(start_date, end_date):
    start = parse_date("start_date", start_date)
    end = parse_date("end_date", end_date)
    if end < start:
        raise WeatherRequestError("end_date must be on or after start_date")
    if (end - start).days + 1 > MAX_FORECAST_DAYS:
        raise WeatherRequestError("Forecast range cannot exceed %d days" % MAX_FORECAST_DAYS)
    return start.isoformat(), end.isoformat()


def parse_date(name, value):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        raise WeatherRequestError("%s must use YYYY-MM-DD" % name)


def normalize_coordinate(name, value, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise WeatherRequestError("%s must be numeric" % name)
    if number < minimum or number > maximum:
        raise WeatherRequestError("%s is out of range" % name)
    return ("%0.7f" % number).rstrip("0").rstrip(".")


def normalize_timezone(value):
    text = str(value or "").strip()
    if not text or len(text) > MAX_TIMEZONE_LENGTH or any(part.isspace() for part in text):
        raise WeatherRequestError("timezone is invalid")
    return text


def normalize_fields(name, value, allowed):
    fields = [part.strip() for part in str(value or "").split(",") if part.strip()]
    if not fields:
        raise WeatherRequestError("%s is required" % name)

    invalid = sorted(set(field for field in fields if field not in allowed))
    if invalid:
        raise WeatherRequestError("Invalid %s field: %s" % (name, ", ".join(invalid)))

    return ",".join(fields)


def cache_is_fresh(entry):
    try:
        fetched_at = bar_widget.parse_datetime(entry.get("fetchedAt"))
    except Exception:
        return False
    ttl = max(0, settings.weather_cache_ttl_ms) / 1000.0
    return bar_widget.now() - fetched_at <= timedelta(seconds=ttl)


def cached_payload(entry, stale=False):
    if not isinstance(entry, dict) or not isinstance(entry.get("payload"), dict):
        return None
    payload = dict(entry["payload"])
    if stale:
        payload["stale"] = True
    return payload


def read_cache(key):
    path = settings.weather_cache_path
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            cache = json.load(handle)
    except Exception:
        return None
    entry = cache.get(key) if isinstance(cache, dict) else None
    return entry if isinstance(entry, dict) else None


def write_cache(key, payload):
    path = settings.weather_cache_path
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
    cache[key] = {
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
