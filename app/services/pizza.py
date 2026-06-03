from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx

from app.config import settings
from app.services import bar_widget


async def load_pizza_index():
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            cache_busting_url(settings.pizza_index_url),
            headers={
                "Accept": "application/json",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
                "User-Agent": "Torrescalla-Bacheca/2.0",
            },
        )
        response.raise_for_status()
        return response.json()


def cache_busting_url(url):
    parts = urlsplit(str(url))
    query = parts.query
    stamp = str(int(bar_widget.now().timestamp()))
    extra = urlencode({"_": stamp})
    query = query + "&" + extra if query else extra
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
