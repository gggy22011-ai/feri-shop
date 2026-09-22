"""
Точка входа для хостинга: бот + сайт в одном процессе и на одном PORT.

Render (free) даёт один контейнер и один внешний порт ($PORT). Чтобы сайт
(каталог из той же БД bot.db) и бот жили вместе и держались 24/7:
  * uvicorn отдаёт FastAPI-сайт (website.app) на $PORT — у него уже есть
    /healthz для Render health check;
  * aiogram-поллинг крутится в этом же event loop;
  * aiohttp-keepalive из bot.py отключается (WEB_DISABLE=1), порт занят сайтом.

Запуск (локально):  python serve.py        # порт: PORT или 8080
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("WEB_DISABLE", "1")

import config  # noqa: E402
import uvicorn  # noqa: E402
from website.app import app as site_app  # noqa: E402


def _port() -> int:
    raw = os.getenv("PORT") or os.getenv("WEB_PORT") or "8080"
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 8080


async def _serve_site() -> None:
    uvicorn_config = uvicorn.Config(
        site_app,
        host="0.0.0.0",
        port=_port(),
        log_level="warning",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(uvicorn_config)
    await server.serve()


async def main() -> None:
    from bot import main as bot_main

    await asyncio.gather(_serve_site(), bot_main())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass