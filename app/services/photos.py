import hashlib
import json
import random
import sqlite3
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from app.config import settings


_stop_event = threading.Event()
_worker = None
_db_lock = threading.Lock()

PHOTO_COLUMNS = {
    "id",
    "asset_id",
    "file_name",
    "thumb_path",
    "status",
    "updated_at",
}


def _now():
    return int(time.time())


def _connect():
    settings.photo_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(settings.photo_db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def _photo_columns(connection):
    table = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='photos'"
    ).fetchone()
    if not table:
        return set()
    rows = connection.execute("PRAGMA table_info(photos)").fetchall()
    return {row["name"] for row in rows}


def init_db():
    with _db_lock:
        connection = _connect()
        try:
            columns = _photo_columns(connection)
            if columns and not PHOTO_COLUMNS.issubset(columns):
                connection.execute("DROP TABLE photos")
                connection.commit()

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT NOT NULL UNIQUE,
                    file_name TEXT NOT NULL,
                    thumb_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_photos_status ON photos(status)")
            connection.commit()
        finally:
            connection.close()


def _photo_id(asset_id):
    text = "|".join(
        [
            "immich",
            str(asset_id),
            str(settings.photo_thumbnail_width),
            str(settings.photo_thumbnail_height),
            str(settings.photo_thumbnail_quality),
        ]
    )
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _thumbnail_path(photo_id):
    return settings.photo_cache_dir / (photo_id + ".jpg")


def _years_for_date(date_text=None):
    if date_text and len(date_text) >= 4 and date_text[:4].isdigit():
        year = int(date_text[:4])
    else:
        year = datetime.now().year
    years = [year]
    for offset in range(1, max(1, settings.photo_years_back) + 1):
        years.append(year - offset)
    return years


def _normal_search_payload_for_years(years):
    start_year = min(years)
    end_year = max(years)
    return {
        "type": "IMAGE",
        "takenAfter": f"{start_year:04d}-01-01T00:00:00.000Z",
        "takenBefore": f"{end_year:04d}-12-31T23:59:59.999Z",
    }


def normal_search_payload(date_text=None):
    return _normal_search_payload_for_years(_years_for_date(date_text))


def birthday_search_payload(person_ids):
    return {
        "type": "IMAGE",
        "personIds": list(person_ids),
    }


def _immich_base_url():
    base = settings.immich_url.strip().rstrip("/")
    if not base:
        raise RuntimeError("Missing BACHECA_IMMICH_URL")
    if not base.endswith("/api"):
        base += "/api"
    return base


def _immich_url(path):
    return _immich_base_url() + "/" + path.lstrip("/")


def _immich_headers():
    if not settings.immich_api_key:
        raise RuntimeError("Missing BACHECA_IMMICH_API_KEY")
    return {
        "Accept": "application/json",
        "x-api-key": settings.immich_api_key,
    }


def _immich_client():
    return httpx.Client(timeout=settings.immich_timeout, headers=_immich_headers())


def _search_size(limit):
    return max(1, min(1000, max(limit * 50, settings.photo_preload_batch)))


def _extract_assets(search_data):
    assets = []

    if isinstance(search_data, dict):
        if isinstance(search_data.get("assets"), dict):
            assets = search_data["assets"].get("items") or []
        elif isinstance(search_data.get("items"), list):
            assets = search_data["items"]
        elif isinstance(search_data.get("assets"), list):
            assets = search_data["assets"]
    elif isinstance(search_data, list):
        assets = search_data

    return [asset for asset in assets if isinstance(asset, dict) and asset.get("id")]


def search_assets(client, payload, limit):
    body = dict(payload)
    body.setdefault("type", "IMAGE")
    body.setdefault("page", 1)
    body.setdefault("size", _search_size(limit))

    response = client.post(_immich_url("search/metadata"), json=body)
    response.raise_for_status()
    return _extract_assets(response.json())


def _load_people(client):
    response = client.get(_immich_url("people"))
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        people = data.get("people") or []
    elif isinstance(data, list):
        people = data
    else:
        people = []
    return [person for person in people if isinstance(person, dict) and person.get("id")]


def _normalize_name(value):
    return " ".join(str(value or "").strip().lower().split())


def _clean_birthday_names(names):
    cleaned = []
    seen = set()
    for name in names or []:
        text = str(name or "").strip()
        key = _normalize_name(text)
        if text and key and key not in seen:
            cleaned.append(text)
            seen.add(key)
    return cleaned


def _immich_person_aliases():
    text = str(settings.immich_person_aliases or "").strip()
    aliases = {}

    if not text:
        return aliases

    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        value = None

    if isinstance(value, dict):
        for source, target in value.items():
            source_key = _normalize_name(source)
            target_text = str(target or "").strip()
            if source_key and target_text:
                aliases[source_key] = target_text
        return aliases

    for part in text.replace("\n", ";").replace("|", ";").split(";"):
        if "=" not in part:
            continue
        source, target = part.split("=", 1)
        source_key = _normalize_name(source)
        target_text = target.strip()
        if source_key and target_text:
            aliases[source_key] = target_text
    return aliases


def _boundary_contains(left, right):
    left = _normalize_name(left)
    right = _normalize_name(right)
    if not left or not right:
        return False
    return (
        left == right
        or left.startswith(right + " ")
        or left.endswith(" " + right)
        or right.startswith(left + " ")
        or right.endswith(" " + left)
    )


def _unique_fuzzy_person(people, target_name):
    matches = []
    for person in people:
        if _boundary_contains(person.get("name"), target_name):
            matches.append(person)
    return matches[0] if len(matches) == 1 else None


def matching_people(people, birthday_names):
    by_name = {}
    aliases = _immich_person_aliases()
    for person in people:
        key = _normalize_name(person.get("name"))
        if key and key not in by_name:
            by_name[key] = person

    matches = []
    for name in _clean_birthday_names(birthday_names):
        candidate_names = [aliases.get(_normalize_name(name)), name]
        person = None
        for candidate_name in candidate_names:
            if not candidate_name:
                continue
            person = by_name.get(_normalize_name(candidate_name))
            if person:
                break
        if not person:
            for candidate_name in candidate_names:
                if candidate_name:
                    person = _unique_fuzzy_person(people, candidate_name)
                    if person:
                        break
        if person:
            matches.append(person)
    return matches


def _asset_file_name(asset):
    name = asset.get("originalFileName") or asset.get("fileName")
    if not name and asset.get("originalPath"):
        name = str(asset["originalPath"]).replace("\\", "/").rstrip("/").split("/")[-1]
    return str(name or asset.get("id") or "immich-photo.jpg")


def _upsert_asset(asset):
    asset_id = str(asset.get("id") or "")
    if not asset_id:
        return None

    photo_id = _photo_id(asset_id)
    thumb_path = _thumbnail_path(photo_id)
    status = "ready" if thumb_path.exists() else "pending"
    row = {
        "id": photo_id,
        "asset_id": asset_id,
        "file_name": _asset_file_name(asset),
        "thumb_path": str(thumb_path),
        "status": status,
    }

    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                INSERT INTO photos (id, asset_id, file_name, thumb_path, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    id=excluded.id,
                    file_name=excluded.file_name,
                    thumb_path=excluded.thumb_path,
                    status=excluded.status,
                    updated_at=excluded.updated_at
                """,
                (
                    row["id"],
                    row["asset_id"],
                    row["file_name"],
                    row["thumb_path"],
                    row["status"],
                    _now(),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    return row


def _set_status(photo_id, status):
    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                "UPDATE photos SET status=?, updated_at=? WHERE id=?",
                (status, _now(), photo_id),
            )
            connection.commit()
        finally:
            connection.close()


def _make_thumbnail(source_bytes, destination):
    settings.photo_cache_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(BytesIO(source_bytes)) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((settings.photo_thumbnail_width, settings.photo_thumbnail_height), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        image.save(destination, "JPEG", quality=settings.photo_thumbnail_quality, optimize=True, progressive=False)


def download_original(client, asset_id):
    response = client.get(_immich_url(f"assets/{asset_id}/original"))
    response.raise_for_status()
    return response.content


def _photo_response(row):
    return {
        "id": row["id"],
        "imagePath": "/api/random-photo/image/" + row["id"],
        "fileName": row["file_name"],
    }


def _prepare_asset(client, asset):
    row = _upsert_asset(asset)
    if not row:
        return None

    destination = Path(row["thumb_path"])
    if destination.exists():
        _set_status(row["id"], "ready")
        return _photo_response(row)

    try:
        _make_thumbnail(download_original(client, row["asset_id"]), destination)
        _set_status(row["id"], "ready")
        return _photo_response(row)
    except Exception:
        _set_status(row["id"], "failed")
        return None


def _prepare_assets(client, assets, limit):
    photos = []
    for asset in assets:
        photo = _prepare_asset(client, asset)
        if photo:
            photos.append(photo)
        if len(photos) >= limit:
            break
    return photos


def _select_assets(assets, limit):
    selected = list(assets)
    random.shuffle(selected)
    return selected[:limit]


def _normal_assets(client, date_text, limit):
    assets = search_assets(client, normal_search_payload(date_text), limit)
    return _select_assets(assets, limit)


def _birthday_assets(client, birthday_names, limit):
    people = matching_people(_load_people(client), birthday_names)
    if not people:
        return []

    if len(people) == 1:
        assets = search_assets(client, birthday_search_payload([people[0]["id"]]), limit)
        return _select_assets(assets, limit)

    selected = []
    for person in people:
        assets = search_assets(client, birthday_search_payload([person["id"]]), 1)
        if assets:
            selected.extend(_select_assets(assets, 1))
        if len(selected) >= limit:
            break
    return selected


def scan_archive(years=None):
    init_db()
    years = years or _years_for_date()
    with _immich_client() as client:
        assets = search_assets(client, _normal_search_payload_for_years(years), settings.photo_preload_batch)
        random.shuffle(assets)
        for asset in assets[: settings.photo_preload_batch]:
            _upsert_asset(asset)
        return len(assets)


def _next_pending(limit):
    with _db_lock:
        connection = _connect()
        try:
            rows = connection.execute(
                "SELECT * FROM photos WHERE status IN ('pending', 'failed') ORDER BY updated_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            connection.close()


def process_pending(limit=None):
    init_db()
    limit = limit or settings.photo_preload_batch
    processed = 0
    with _immich_client() as client:
        for row in _next_pending(limit):
            destination = Path(row["thumb_path"])
            try:
                if not destination.exists():
                    _make_thumbnail(download_original(client, row["asset_id"]), destination)
                _set_status(row["id"], "ready")
                processed += 1
            except Exception:
                _set_status(row["id"], "failed")
    return processed


def preload_once():
    years = _years_for_date()
    scan_archive(years)
    return process_pending(settings.photo_preload_batch)


def _worker_loop():
    while not _stop_event.is_set():
        try:
            preload_once()
        except Exception:
            pass
        interval = max(60, settings.photo_scan_interval_ms / 1000.0)
        _stop_event.wait(interval)


def start_worker():
    global _worker
    init_db()
    if _worker and _worker.is_alive():
        return
    _stop_event.clear()
    _worker = threading.Thread(target=_worker_loop, name="bacheca-photo-preloader", daemon=True)
    _worker.start()


def stop_worker():
    _stop_event.set()


def random_ready_photos(date_text=None, limit=2, birthday_names=None):
    init_db()
    names = _clean_birthday_names(birthday_names)

    try:
        with _immich_client() as client:
            if names:
                birthday_photos = _prepare_assets(client, _birthday_assets(client, names, limit), limit)
                if birthday_photos:
                    return birthday_photos

            return _prepare_assets(client, _normal_assets(client, date_text, limit), limit)
    except Exception:
        return []


def thumbnail_for_id(photo_id):
    with _db_lock:
        connection = _connect()
        try:
            row = connection.execute(
                "SELECT thumb_path FROM photos WHERE id=? AND status='ready'",
                (photo_id,),
            ).fetchone()
            if not row:
                return None
            path = Path(row["thumb_path"])
            return path if path.exists() else None
        finally:
            connection.close()
