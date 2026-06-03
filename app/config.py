import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = BASE_DIR / "bacheca-frontend"

load_dotenv(BASE_DIR / ".env")


def get_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def get_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def resolve_path(value, default, base=BASE_DIR):
    path = Path(os.getenv(value, default))
    if not path.is_absolute():
        path = base / path
    return path.resolve()


class Settings:
    dashboard_host = os.getenv("BACHECA_DASHBOARD_HOST", "0.0.0.0")
    dashboard_port = get_int("BACHECA_DASHBOARD_PORT", 8080)

    static_root = resolve_path("BACHECA_STATIC_ROOT", str(FRONTEND_DIR))

    request_timeout = get_int("BACHECA_MENU_TIMEOUT_MS", 10000) / 1000.0

    mycollege_menu_url = os.getenv("MYCOLLEGE_MENU_URL", "https://mycollegeapp.rui.it/jsonapi")
    mycollege_pasti_url = os.getenv("MYCOLLEGE_PASTI_URL", os.getenv("PASTI_URL", "https://mycollegeapp.rui.it/jsonapi"))
    mycollege_residence = os.getenv("MYCOLLEGE_RESIDENCE", "dG9ycmVzY2FsbGE-")
    mycollege_menu_enabled = os.getenv("MYCOLLEGE_MENU_ENABLED", "1")
    mycollege_turno_singolo = get_bool("MYCOLLEGE_TURNO_SINGOLO", get_bool("TURNO_SINGOLO", False))

    pizza_index_url = os.getenv("PIZZA_INDEX_URL", "https://www.pizzint.watch/api/dashboard-data")

    google_client_email = os.getenv("GOOGLE_CLIENT_EMAIL", "")
    google_private_key = os.getenv("GOOGLE_PRIVATE_KEY", "")
    google_project_number = os.getenv("GOOGLE_PROJECT_NUMBER", "")
    google_calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "eventi.torrescalla@fondazionerui.it")
    google_calendar_max_results = get_int("GOOGLE_CALENDAR_MAX_RESULTS", 50)

    photo_root = resolve_path("BACHECA_PHOTO_ROOT", "/mnt/foto")
    photo_cache_dir = resolve_path("BACHECA_PHOTO_CACHE_DIR", ".cache/photo-thumbs")
    photo_db_path = resolve_path("BACHECA_PHOTO_DB_PATH", ".cache/photos.sqlite")
    photo_extensions = tuple(
        part.strip().lower() if part.strip().startswith(".") else "." + part.strip().lower()
        for part in os.getenv("BACHECA_PHOTO_EXTENSIONS", ".jpg,.jpeg,.png,.gif,.webp").split(",")
        if part.strip()
    )
    photo_thumbnail_width = get_int("BACHECA_PHOTO_THUMBNAIL_WIDTH", 900)
    photo_thumbnail_height = get_int("BACHECA_PHOTO_THUMBNAIL_HEIGHT", 520)
    photo_thumbnail_quality = get_int("BACHECA_PHOTO_THUMBNAIL_QUALITY", 82)
    photo_scan_interval_ms = get_int("BACHECA_PHOTO_SCAN_INTERVAL_MS", 900000)
    photo_years_back = get_int("BACHECA_PHOTO_YEARS_BACK", 1)
    photo_preload_batch = get_int("BACHECA_PHOTO_PRELOAD_BATCH", 40)

    timezone = os.getenv("BACHECA_TIMEZONE", "Europe/Rome")
    bar_widget_state_path = resolve_path("BACHECA_BAR_WIDGET_STATE_PATH", ".cache/bar-widget-state.json")

    soccer_provider = os.getenv("BACHECA_SOCCER_PROVIDER", "football-data")
    soccer_api_token = os.getenv("BACHECA_SOCCER_API_TOKEN", "")
    soccer_base_url = os.getenv("BACHECA_SOCCER_BASE_URL", "https://api.football-data.org/v4")
    soccer_cache_path = resolve_path("BACHECA_SOCCER_CACHE_PATH", ".cache/soccer-cache.json")
    soccer_badge_cache_dir = resolve_path("BACHECA_SOCCER_BADGE_CACHE_DIR", ".cache/soccer-badges")
    soccer_cache_ttl_ms = get_int("BACHECA_SOCCER_CACHE_TTL_MS", 600000)
    soccer_lookback_days = get_int("BACHECA_SOCCER_LOOKBACK_DAYS", 7)
    soccer_lookahead_days = get_int("BACHECA_SOCCER_LOOKAHEAD_DAYS", 7)
    soccer_max_items = get_int("BACHECA_SOCCER_MAX_ITEMS", 4)

    basketball_provider = os.getenv("BACHECA_BASKETBALL_PROVIDER", "thesportsdb")
    basketball_api_token = os.getenv("BACHECA_BASKETBALL_API_TOKEN", "")
    basketball_base_url = os.getenv("BACHECA_BASKETBALL_BASE_URL", "")
    basketball_cache_path = resolve_path("BACHECA_BASKETBALL_CACHE_PATH", ".cache/basketball-cache.json")
    basketball_badge_cache_dir = resolve_path("BACHECA_BASKETBALL_BADGE_CACHE_DIR", ".cache/basketball-badges")
    basketball_cache_ttl_ms = get_int("BACHECA_BASKETBALL_CACHE_TTL_MS", 1800000)
    basketball_lookback_days = get_int("BACHECA_BASKETBALL_LOOKBACK_DAYS", 30)
    basketball_lookahead_days = get_int("BACHECA_BASKETBALL_LOOKAHEAD_DAYS", 30)
    basketball_max_items = get_int("BACHECA_BASKETBALL_MAX_ITEMS", 4)
    basketball_default_season = os.getenv("BACHECA_BASKETBALL_DEFAULT_SEASON", "")


settings = Settings()
