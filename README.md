# Bacheca Backend

FastAPI backend for the Torrescalla Bacheca dashboard.

This service replaces the old Node static server/proxy. It serves the existing `../bacheca` frontend and all `/api/...` endpoints from one port.

Photo thumbnails are generated with Pillow inside Python. ImageMagick is not required for this backend.

## Setup

```bash
cd bacheca-backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.EXAMPLE .env
```

Edit `.env` and keep the same Google/MyCollege/FOTO settings used by the old dashboard.

## Run Locally

```bash
./start-service.sh
```

Open:

```text
http://127.0.0.1:8080
```

Useful checks:

```text
http://127.0.0.1:8080/health
http://127.0.0.1:8080/api/pasti
http://127.0.0.1:8080/api/menu?data=2026-05-29
http://127.0.0.1:8080/api/calendar
http://127.0.0.1:8080/api/pizza-index
http://127.0.0.1:8080/api/random-photo?data=2026-05-29
```

## Photos

The backend scans `BACHECA_PHOTO_ROOT`, usually `/mnt/foto`, for folders whose names start with the current year or previous year. It stores metadata in SQLite and preloads small JPEG thumbnails in the background.

The browser only receives thumbnail URLs. Original photos are never sent to the frontend.

Important settings:

```env
BACHECA_PHOTO_ROOT=/mnt/foto
BACHECA_PHOTO_CACHE_DIR=.cache/photo-thumbs
BACHECA_PHOTO_DB_PATH=.cache/photos.sqlite
BACHECA_PHOTO_THUMBNAIL_WIDTH=900
BACHECA_PHOTO_THUMBNAIL_HEIGHT=520
BACHECA_PHOTO_THUMBNAIL_QUALITY=82
BACHECA_PHOTO_SCAN_INTERVAL_MS=900000
BACHECA_PHOTO_YEARS_BACK=1
BACHECA_PHOTO_PRELOAD_BATCH=40
```

If `/api/random-photo` returns `{ "available": false }`, the preloader may still be generating thumbnails. Check logs and the cache folder.

## Systemd

Example service:

```ini
[Unit]
Description=Torrescalla Bacheca Backend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=admin-bacheca
WorkingDirectory=/home/admin-bacheca/bacheca-backend
ExecStart=/home/admin-bacheca/bacheca-backend/start-service.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

After changing `.env`, restart:

```bash
sudo systemctl restart bacheca
```

If the existing VM service still points to `bacheca/scripts/start-services.sh` or `bacheca/scripts/start-services.js`, those paths are compatibility launchers that start this backend.
