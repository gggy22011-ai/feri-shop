"""
Мини-веб-сервер для бесплатного хостинга (Render/Koyeb и т.п.).

Бесплатные инстансы засыпают без входящих HTTP-запросов (~15 минут).
Этот эндпоинт `/healthz` даёт UptimeRobot (или `keepalive.py`) точку для
пинга раз в 5 минут — инстанс не спит, бот поллингует 24/7.

Запускается из bot.py автоматически, если задан PORT (Render) или WEB_ENABLED.
"""
from __future__ import annotations

import os
import time

import config
from aiohttp import web
from utils.logger import get_logger

logger = get_logger("web")

_START_TS = time.time()


def _port() -> int:
    raw = os.getenv("PORT") or os.getenv("WEB_PORT") or "8080"
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 8080


def _enabled() -> bool:
    """Включаем веб-сервер на хостинге (PORT задан) или по WEB_ENABLED=1."""
    if os.getenv("PORT"):
        return True
    return os.getenv("WEB_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


async def _healthz(request: web.Request) -> web.Response:
    return web.Response(text="ok", content_type="text/plain")


async def _root(request: web.Request) -> web.Response:
    uptime = int(time.time() - _START_TS)
    return web.Response(
        text=f"{config.SHOP_NAME} bot v3 up {uptime}s",
        content_type="text/plain",
    )


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", _root)
    app.router.add_get("/healthz", _healthz)
    app.router.add_get("/ping", _healthz)
    return app


async def start_web_server() -> None:
    """Запускает HTTP-сервер в текущем event loop (не блокирует поллинг)."""
    port = _port()
    app = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("WEB-сервер стартовал на 0.0.0.0:%s (keepalive /healthz)", port)


if __name__ == "__main__":
    import asyncio

    asyncio.run(start_web_server())
    logger.info("Запущено вручную: аварийного выхода по Ctrl+C.")
    loop = asyncio.get_event_loop()
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass