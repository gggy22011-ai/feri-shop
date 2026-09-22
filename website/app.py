"""
Сайт магазина Feri shop (каталог + документы + проверка покупок).

Запуск:  python -m uvicorn website.app:app --host 127.0.0.1 --port 8000
или скриптом start_web.bat
"""
from __future__ import annotations

import os
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import website.db as wdb
from website.ddos import DDOSMiddlewware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Feri shop", docs_url=None, redoc_url=None)
app.add_middleware(DDOSMiddlewware)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

BOT_LINK = "https://t.me/Shootingferi_bot"
BOT_SHOP = f"{BOT_LINK}?start=shop"
SUPPORT_USER = "No7777oN"
SUPPORT_LINK = f"https://t.me/{SUPPORT_USER}"
CHANNEL_LINK = "https://t.me/feris_shop"

templates.env.globals.update(
    {
        "bot_link": BOT_LINK,
        "bot_shop": BOT_SHOP,
        "support_link": SUPPORT_LINK,
        "support_user": SUPPORT_USER,
        "channel_link": CHANNEL_LINK,
        "now": datetime.now().year,
    }
)


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    countries = wdb.get_countries()
    stats = wdb.get_stats()
    top = countries[:6]
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "title": "Feri shop — виртуальные номера",
            "page": "index",
            "settings": wdb.get_settings(),
            "stats": stats,
            "top": top,
            "mone": wdb.money,
            "bot_link": BOT_LINK,
            "bot_shop": BOT_SHOP,
            "support_link": SUPPORT_LINK,
            "support_user": SUPPORT_USER,
            "channel_link": CHANNEL_LINK,
        },
    )


@app.get("/catalog", response_class=HTMLResponse)
async def catalog(request: Request):
    countries = wdb.get_countries()
    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "title": "Каталог",
            "page": "catalog",
            "settings": wdb.get_settings(),
            "countries": countries,
            "mone": wdb.money,
            "bot_shop": BOT_SHOP,
        },
    )


@app.get("/country/{country_id}", response_class=HTMLResponse)
async def country(request: Request, country_id: int):
    ctry = wdb.get_country(country_id)
    if not ctry:
        return templates.TemplateResponse(
            request,
            "notfound.html",
            {"title": "404", "page": "catalog", "settings": wdb.get_settings()},
            status_code=404,
        )
    nums = wdb.get_available_numbers(country_id, limit=30)
    return templates.TemplateResponse(
        request,
        "country.html",
        {
            "title": f"{ctry['flag']} {ctry['name']}",
            "page": "catalog",
            "settings": wdb.get_settings(),
            "c": ctry,
            "nums": nums,
            "mone": wdb.money,
            "mask": wdb.mask_phone,
            "bot_shop": BOT_SHOP,
            "support_link": SUPPORT_LINK,
        },
    )


@app.get("/howto", response_class=HTMLResponse)
async def howto(request: Request):
    return templates.TemplateResponse(
        request,
        "howto.html",
        {
            "title": "Как купить",
            "page": "howto",
            "settings": wdb.get_settings(),
            "bot_shop": BOT_SHOP,
            "support_link": SUPPORT_LINK,
        },
    )


@app.get("/faq", response_class=HTMLResponse)
async def faq(request: Request):
    return templates.TemplateResponse(
        request,
        "faq.html",
        {
            "title": "FAQ",
            "page": "faq",
            "settings": wdb.get_settings(),
            "support_link": SUPPORT_LINK,
        },
    )


@app.get("/support", response_class=HTMLResponse)
async def support(request: Request):
    return templates.TemplateResponse(
        request,
        "support.html",
        {
            "title": "Поддержка",
            "page": "support",
            "settings": wdb.get_settings(),
            "bot_shop": BOT_SHOP,
            "support_link": SUPPORT_LINK,
            "support_user": SUPPORT_USER,
            "channel_link": CHANNEL_LINK,
        },
    )


@app.get("/agreement", response_class=HTMLResponse)
async def agreement(request: Request):
    return templates.TemplateResponse(
        request,
        "agreement.html",
        {
            "title": "Пользовательское соглашение",
            "page": "docs",
            "settings": wdb.get_settings(),
        },
    )


@app.get("/privacy", response_class=HTMLResponse)
async def privacy(request: Request):
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "title": "Политика конфиденциальности",
            "page": "docs",
            "settings": wdb.get_settings(),
        },
    )


@app.get("/my", response_class=HTMLResponse)
async def my_orders(request: Request):
    tg_id = request.query_params.get("tg_id", "").strip()
    orders = []
    error = None
    if tg_id:
        if tg_id.isdigit() and int(tg_id) > 0:
            orders = wdb.find_orders_by_user(int(tg_id))
            if not orders:
                error = "Заказов с таким Telegram ID не найдено. Проверь ID."
        else:
            error = "Telegram ID — это число. Узнать его: бот → Профиль."
    return templates.TemplateResponse(
        request,
        "my.html",
        {
            "title": "Мои покупки",
            "page": "my",
            "settings": wdb.get_settings(),
            "tg_id": tg_id,
            "orders": orders,
            "error": error,
            "mone": wdb.money,
        },
    )