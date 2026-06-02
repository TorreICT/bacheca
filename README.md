# Bacheca App

FastAPI app for the Torrescalla dashboard. This repo is now the production
runtime: it serves the static frontend from `bacheca-frontend/` and all
dashboard data from same-origin `/api/...` endpoints on one port.

The old Node static server and Node proxy are retired. Port `8081` is not used.

## Setup

```bash
cd bacheca-backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.EXAMPLE .env
```

Edit `bacheca-backend/.env`. This is the only runtime env file used by the
backend. The frontend copy in `bacheca-frontend/` is static-only and does not
have its own env, package, or startup scripts.

## Run

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
http://127.0.0.1:8080/
http://127.0.0.1:8080/assets/js/config.js
http://127.0.0.1:8080/api/pasti
http://127.0.0.1:8080/api/menu?data=2026-05-29
http://127.0.0.1:8080/api/calendar
http://127.0.0.1:8080/api/pizza-index
http://127.0.0.1:8080/api/random-photo?data=2026-05-29
```

## Configuration

Main settings in `.env`:

```env
BACHECA_DASHBOARD_HOST=0.0.0.0
BACHECA_DASHBOARD_PORT=8080
BACHECA_STATIC_ROOT=bacheca-frontend
MYCOLLEGE_MENU_URL=https://mycollegeapp.rui.it/jsonapi
MYCOLLEGE_PASTI_URL=https://mycollegeapp.rui.it/jsonapi
MYCOLLEGE_RESIDENCE=dG9ycmVzY2FsbGE-
GOOGLE_CALENDAR_ID=eventi.torrescalla@fondazionerui.it
```

`GOOGLE_PRIVATE_KEY` should stay in `bacheca-backend/.env`, either as one line
with escaped `\n` characters or as quoted PEM text.

## Photos

Mount the FOTO share on the VM, usually at `/mnt/foto`, and make it readable by
the systemd user.

Example CIFS mount flow:

```bash
sudo apt install cifs-utils
sudo mkdir -p /mnt/foto
sudo mount -t cifs //SERVER_IP/FOTO /mnt/foto -o ro,guest,iocharset=utf8
```

The backend scans year folders under `BACHECA_PHOTO_ROOT`, stores metadata in
SQLite, and preloads small JPEG thumbnails with Pillow. The browser only
receives thumbnail URLs; original photos are never sent to the Raspberry.

Important photo settings:

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

If `/api/random-photo` returns `{ "available": false }`, the preloader may still
be generating thumbnails. Check service logs and `.cache/`.

## Systemd

Example service:

```ini
[Unit]
Description=Torrescalla Bacheca
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

After changing `.env`:

```bash
sudo systemctl restart bacheca
```

If an existing VM unit still calls `bacheca/scripts/start-services.sh` or
`node bacheca/scripts/start-services.js`, those standalone frontend paths remain
compatibility launchers and delegate to this backend.
