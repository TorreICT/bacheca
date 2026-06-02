import httpx

from app.config import settings


async def load_pizza_index():
    async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
        response = await client.get(
            settings.pizza_index_url,
            headers={"Accept": "application/json", "User-Agent": "Torrescalla-Bacheca/2.0"},
        )
        response.raise_for_status()
        return response.json()
