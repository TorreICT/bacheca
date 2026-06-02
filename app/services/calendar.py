import asyncio
from datetime import datetime
from urllib.parse import quote, urlencode

import httpx
from google.auth.transport.requests import Request
from google.oauth2 import service_account

from app.config import settings


GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3/calendars/"

_credentials = None


def _private_key():
    return settings.google_private_key.replace("\\n", "\n")


def _require_config():
    missing = []
    if not settings.google_client_email:
        missing.append("GOOGLE_CLIENT_EMAIL")
    if not settings.google_private_key:
        missing.append("GOOGLE_PRIVATE_KEY")
    if not settings.google_project_number:
        missing.append("GOOGLE_PROJECT_NUMBER")
    if not settings.google_calendar_id:
        missing.append("GOOGLE_CALENDAR_ID")
    if missing:
        raise RuntimeError("Missing " + ", ".join(missing))


def _get_credentials():
    global _credentials
    _require_config()
    if _credentials is None:
        info = {
            "type": "service_account",
            "project_id": settings.google_project_number,
            "private_key_id": "bacheca",
            "private_key": _private_key(),
            "client_email": settings.google_client_email,
            "client_id": settings.google_project_number,
            "token_uri": "https://oauth2.googleapis.com/token",
        }
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=[GOOGLE_SCOPE])
    if not _credentials.valid:
        _credentials.refresh(Request())
    return _credentials


async def load_calendar():
    credentials = await asyncio.to_thread(_get_credentials)
    start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).astimezone().isoformat()
    params = {
        "timeMin": start,
        "maxResults": settings.google_calendar_max_results,
        "singleEvents": "true",
        "orderBy": "startTime",
    }
    url = GOOGLE_CALENDAR_BASE_URL + quote(settings.google_calendar_id, safe="") + "/events?" + urlencode(params)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(url, headers={"Authorization": "Bearer " + credentials.token})
        response.raise_for_status()
        body = response.json()
        return {"events": body.get("items") or []}
