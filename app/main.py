import re
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.services import bar_widget, basketball, calendar, mycollege, photos, pizza, soccer


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="Torrescalla Bacheca Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    photos.start_worker()


@app.on_event("shutdown")
def shutdown():
    photos.stop_worker()


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/menu")
async def api_menu(data: str = Query(...)):
    if not DATE_RE.match(data):
        raise HTTPException(status_code=400, detail="Invalid data parameter. Expected YYYY-MM-DD.")
    try:
        return await mycollege.load_menu(data)
    except httpx.HTTPError as error:
        return JSONResponse(status_code=502, content={"error": "Menu not available", "detail": str(error)})


@app.get("/api/pasti")
async def api_pasti():
    try:
        return await mycollege.load_pasti()
    except httpx.HTTPError as error:
        return JSONResponse(status_code=502, content={"error": "Pasti not available", "detail": str(error)})


@app.get("/api/calendar")
async def api_calendar():
    try:
        return await calendar.load_calendar()
    except Exception as error:
        return JSONResponse(status_code=502, content={"error": "Calendar not available", "detail": str(error)})


@app.get("/api/pizza-index")
async def api_pizza_index():
    try:
        return JSONResponse(
            content=await pizza.load_pizza_index(),
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except httpx.HTTPError as error:
        return JSONResponse(
            status_code=502,
            content={"error": "Pizza index not available", "detail": str(error)},
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )


@app.get("/api/random-photo")
def api_random_photo(data: str = Query(None)):
    if data and not DATE_RE.match(data):
        raise HTTPException(status_code=400, detail="Invalid data parameter. Expected YYYY-MM-DD.")
    ready = photos.random_ready_photos(data, limit=2)
    if not ready:
        return {"available": False}
    return {
        "available": True,
        "id": ready[0]["id"],
        "imagePath": ready[0]["imagePath"],
        "fileName": ready[0]["fileName"],
        "photos": ready,
    }


@app.get("/api/random-photo/image/{photo_id}")
def api_random_photo_image(photo_id: str):
    thumbnail = photos.thumbnail_for_id(photo_id)
    if not thumbnail:
        raise HTTPException(status_code=404, detail="Photo not found")
    return FileResponse(str(thumbnail), media_type="image/jpeg")


@app.get("/api/bar-widget")
async def api_bar_widget():
    return await bar_widget.public_state()


@app.get("/api/soccer/badge")
async def api_soccer_badge(src: str = Query(...)):
    try:
        path, media_type = await soccer.badge_file(src)
    except Exception:
        path, media_type = None, ""
    if not path:
        raise HTTPException(status_code=404, detail="Badge not available")
    return FileResponse(str(path), media_type=media_type)


@app.get("/api/basketball/badge")
async def api_basketball_badge(src: str = Query(...)):
    try:
        path, media_type = await basketball.badge_file(src)
    except Exception:
        path, media_type = None, ""
    if not path:
        raise HTTPException(status_code=404, detail="Badge not available")
    return FileResponse(str(path), media_type=media_type)


@app.get("/")
@app.get("/index.html")
def index():
    index_path = settings.static_root / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard index not found")
    return FileResponse(str(index_path), media_type="text/html")


@app.get("/assets/js/config.js")
def frontend_config():
    config_path = settings.static_root / "assets" / "js" / "config.js"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Frontend config not found")
    return FileResponse(
        str(config_path),
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


assets_path = settings.static_root / "assets"
if assets_path.exists():
    app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")

data_path = settings.static_root / "data"
if data_path.exists():
    app.mount("/data", StaticFiles(directory=str(data_path)), name="data")
