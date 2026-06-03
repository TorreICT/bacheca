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
http://127.0.0.1:8080/api/bar-widget
```

## Configuration

Main settings in `.env`:

```env
BACHECA_DASHBOARD_HOST=0.0.0.0
BACHECA_DASHBOARD_PORT=8080
BACHECA_STATIC_ROOT=bacheca-frontend
BACHECA_TIMEZONE=Europe/Rome
BACHECA_BAR_WIDGET_STATE_PATH=.cache/bar-widget-state.json
MYCOLLEGE_MENU_URL=https://mycollegeapp.rui.it/jsonapi
MYCOLLEGE_PASTI_URL=https://mycollegeapp.rui.it/jsonapi
MYCOLLEGE_RESIDENCE=dG9ycmVzY2FsbGE-
GOOGLE_CALENDAR_ID=eventi.torrescalla@fondazionerui.it
```

`GOOGLE_PRIVATE_KEY` should stay in `bacheca-backend/.env`, either as one line
with escaped `\n` characters or as quoted PEM text.

## Telegram bar widget

The horizontal bar between weather forecast and menu is owned by the backend at
`/api/bar-widget`. The browser only polls this same-origin endpoint every 12
seconds; it never talks to Telegram or soccer APIs. State is stored as JSON in
`.cache/bar-widget-state.json` by default, and overlapping announcements use the
deterministic policy `newest wins`.

Run the controller bot as a separate process:

```bash
python -m telegram_bot.bot
```

Required bot settings:

```env
TELEGRAM_BOT_TOKEN=123456:replace-with-your-token
TELEGRAM_ALLOWED_CHAT_IDS=123456789,-1001234567890
```

`TELEGRAM_ALLOWED_CHAT_IDS` is a comma-separated allowlist. If it is empty, the
bot refuses to start; chats not in the list cannot modify state.

Use `/start` for an introduction and `/panel` for the main inline-button panel.
Buttons cover show/hide, announcement creation, countdowns, color
presets/custom colors, soccer enable/disable, competition selection, and
confirmation for destructive actions. `/my_id` shows the current chat ID and is
the only command available to unauthorized chats. `/cancel` stops a guided flow
and `/help` shows shortcuts.

Raw command shortcuts:

```text
/show
/hide
/my_id
/announce Text | 2026-06-03T22:00:00+02:00
/countdown Label | 2026-06-03T20:00:00+02:00
/color blue
/color #1565C0
/soccer SA
/soccer_on
/soccer_off
```

Every announcement must have an end time. One-shot announcements use ISO
datetimes for start/end. Periodic announcements are created through the guided
flow: daily runs every day, weekly asks for days as `0=Mon ... 6=Sun`, then an
occurrence start time such as `19:30`, a duration in minutes, and an ISO
recurrence end datetime. Expired or inactive occurrences are not displayed.

Safe colors are stored only as final hex values. Accepted inputs are `#RRGGBB`
or presets: `blue`, `green`, `red`, `orange`, `purple`, `teal`, `gray`, `dark`.

## Soccer

Soccer is optional and uses football-data.org v4 by default. Configure:

```env
BACHECA_SOCCER_PROVIDER=football-data
BACHECA_SOCCER_API_TOKEN=your-football-data-token
BACHECA_SOCCER_BASE_URL=https://api.football-data.org/v4
BACHECA_SOCCER_CACHE_PATH=.cache/soccer-cache.json
BACHECA_SOCCER_BADGE_CACHE_DIR=.cache/soccer-badges
BACHECA_SOCCER_CACHE_TTL_MS=600000
BACHECA_SOCCER_LOOKBACK_DAYS=30
BACHECA_SOCCER_LOOKAHEAD_DAYS=30
BACHECA_SOCCER_MAX_ITEMS=4
```

If the token is missing or the provider fails, announcements and countdowns keep
working. Soccer returns an unavailable message, or stale cached data when a
previous successful response exists.

The bot competition picker queries `GET /v4/competitions` when the
football-data token is configured, then caches the available list in
`.cache/soccer-cache.json`. If discovery is unavailable, it falls back to a
local list that includes club competitions plus national-team competitions such
as `WC` for FIFA World Cup and `EC` for European Championship.

The bar soccer view uses a fixed 30-day window and shows up to 4 matches:
ideally 2 recent results and 2 upcoming fixtures. If one side has fewer than 2,
the other side fills the remaining slots; if no matches are available, the bar
shows a short empty message. Team crests or flags are served through the
same-origin `/api/soccer/badge` proxy and cached under `.cache/soccer-badges/`;
the browser does not call football-data image URLs directly.

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

Example separate Telegram bot service:

```ini
[Unit]
Description=Torrescalla Bacheca Telegram Bot
After=network-online.target bacheca.service
Wants=network-online.target

[Service]
Type=simple
User=admin-bacheca
WorkingDirectory=/home/admin-bacheca/bacheca-backend
ExecStart=/home/admin-bacheca/bacheca-backend/.venv/bin/python -m telegram_bot.bot
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Restart both services after changing `.env`:

```bash
sudo systemctl restart bacheca
sudo systemctl restart bacheca-telegram-bot
```

If an existing VM unit still calls `bacheca/scripts/start-services.sh` or
`node bacheca/scripts/start-services.js`, those standalone frontend paths remain
compatibility launchers and delegate to this backend.

## Frontend compatibility

The frontend is plain static JavaScript for old Chromium. Keep using XHR and
callbacks; do not add `fetch`, `async`/`await`, arrow functions, `let`/`const`,
optional chaining, ES modules, frameworks, or build tooling.
