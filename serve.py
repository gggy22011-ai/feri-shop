"""
Точка входа для Render/Koyeb: бот и сайт живут в одном процессе
на одном HTTP-порту ($PORT), чтобы бесплатный инстанс не засыпал:
  * FastAPI-сайт (website/app.py) слушает $PORT и отдаёт /healthz;
  * aiogram-поллинг бота крутится в том же event loop.
Локально бот запускается как раньше: python bot.py (aiohttp + /healthz).
"""
from __future__ import annotations

import asyncio
import os

# Не даём боту поднимать собственный aiohttp-сервер на том же порту —
# на хостинге с одним PORT ему не место (порт занимает сайт).
os.environ.setdefault("WEB_DISABLE", "1")

import uvicorn  # noqa: E402
from website.app import app as site_app  # noqa: E402


async def _serve_site() -> None:
    port = int(os.getenv("PORT") or "8080")
    config = uvicorn.Config(
        site_app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    from bot import main as bot_main

    await asyncio.gather(_serve_site(), bot_main())


if __name__ == "__main__":
    asyncio.run(main())
