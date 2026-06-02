from urllib.parse import urlencode

import httpx

from app.config import settings


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _apply_turno_singolo(body):
    if not settings.mycollege_turno_singolo:
        return body
    try:
        pranzo = body["totali"]["Pranzo"]
    except (TypeError, KeyError):
        return body

    pranzo["Presente"] = str(_to_int(pranzo.get("Turno 1")) + _to_int(pranzo.get("Turno 2")))
    return body


async def load_menu(date_text):
    params = {
        "residenza": settings.mycollege_residence,
        "menu": settings.mycollege_menu_enabled,
        "data": date_text,
    }
    url = settings.mycollege_menu_url + "?" + urlencode(params)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(url, headers={"Accept": "application/json", "User-Agent": "Torrescalla-Bacheca/2.0"})
        response.raise_for_status()
        return response.json()


async def load_pasti():
    params = {"residenza": settings.mycollege_residence}
    url = settings.mycollege_pasti_url + "?" + urlencode(params)
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(url, headers={"Accept": "application/json", "User-Agent": "Torrescalla-Bacheca/2.0"})
        response.raise_for_status()
        return _apply_turno_singolo(response.json())
