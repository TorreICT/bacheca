import hashlib
import os
import random
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from app.config import settings


_stop_event = threading.Event()
_worker = None
_db_lock = threading.Lock()


def _now():
    return int(time.time())


def _connect():
    settings.photo_db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(settings.photo_db_path), timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with _db_lock:
        connection = _connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS photos (
                    id TEXT PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    year INTEGER NOT NULL,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    thumb_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_photos_year_status ON photos(year, status)")
            connection.commit()
        finally:
            connection.close()


def _photo_id(path, size, mtime):
    text = "|".join(
        [
            str(path),
            str(size),
            str(mtime),
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


def _year_folders(years):
    if not settings.photo_root.exists():
        return []
    folders = []
    prefixes = tuple(str(year) for year in years)
    try:
        entries = list(settings.photo_root.iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.name.startswith(prefixes) and entry.is_dir() and not entry.is_symlink():
            folders.append(entry)
    random.shuffle(folders)
    return folders


def _file_year(path):
    name = path.name
    if len(name) >= 4 and name[:4].isdigit():
        return int(name[:4])
    for parent in path.parents:
        if parent == settings.photo_root:
            break
        if len(parent.name) >= 4 and parent.name[:4].isdigit():
            return int(parent.name[:4])
    return datetime.now().year


def _iter_photo_files(years):
    folders = _year_folders(years)
    for folder in folders:
        for root, dirs, files in os.walk(str(folder), followlinks=False):
            dirs[:] = [name for name in dirs if not Path(root, name).is_symlink()]
            random.shuffle(files)
            for file_name in files:
                path = Path(root) / file_name
                if path.suffix.lower() in settings.photo_extensions:
                    yield path


def _upsert_photo(connection, path):
    try:
        stat = path.stat()
    except OSError:
        return
    photo_id = _photo_id(path, stat.st_size, stat.st_mtime)
    thumb_path = _thumbnail_path(photo_id)
    status = "ready" if thumb_path.exists() else "pending"
    connection.execute(
        """
        INSERT INTO photos (id, path, year, size, mtime, thumb_path, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            id=excluded.id,
            year=excluded.year,
            size=excluded.size,
            mtime=excluded.mtime,
            thumb_path=excluded.thumb_path,
            status=CASE
                WHEN photos.size=excluded.size AND photos.mtime=excluded.mtime AND photos.status='ready' THEN photos.status
                ELSE excluded.status
            END,
            updated_at=excluded.updated_at
        """,
        (photo_id, str(path), _file_year(path), stat.st_size, stat.st_mtime, str(thumb_path), status, _now()),
    )


def scan_archive(years=None):
    init_db()
    years = years or _years_for_date()
    with _db_lock:
        connection = _connect()
        try:
            for path in _iter_photo_files(years):
                _upsert_photo(connection, path)
            connection.commit()
        finally:
            connection.close()


def _make_thumbnail(source, destination):
    settings.photo_cache_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        image.thumbnail((settings.photo_thumbnail_width, settings.photo_thumbnail_height), Image.Resampling.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        elif image.mode == "L":
            image = image.convert("RGB")
        image.save(destination, "JPEG", quality=settings.photo_thumbnail_quality, optimize=True, progressive=False)


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


def process_pending(limit=None):
    init_db()
    limit = limit or settings.photo_preload_batch
    processed = 0
    for row in _next_pending(limit):
        source = Path(row["path"])
        destination = Path(row["thumb_path"])
        if not source.exists():
            _set_status(row["id"], "missing")
            continue
        try:
            if not destination.exists():
                _make_thumbnail(source, destination)
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


def random_ready_photos(date_text=None, limit=2):
    years = _years_for_date(date_text)
    placeholders = ",".join(["?"] * len(years))
    with _db_lock:
        connection = _connect()
        try:
            rows = connection.execute(
                "SELECT * FROM photos WHERE status='ready' AND year IN (" + placeholders + ") ORDER BY RANDOM() LIMIT ?",
                tuple(years) + (limit,),
            ).fetchall()
            photos = []
            for row in rows:
                thumb_path = Path(row["thumb_path"])
                if thumb_path.exists():
                    photos.append(
                        {
                            "id": row["id"],
                            "imagePath": "/api/random-photo/image/" + row["id"],
                            "fileName": Path(row["path"]).name,
                        }
                    )
            return photos
        finally:
            connection.close()


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
