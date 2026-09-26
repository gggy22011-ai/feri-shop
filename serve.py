"""
Точка входа для Render/Koyeb: бот и сайт живут в одном процессе
на одном HTTP-порту ($PORT), чтобы бесплатный инстанс не засыпал:
  * FastAPI-сайт (website/app.py) слушает $PORT и отдаёт /healthz;
  * aiogram-поллинг бота крутится в том же event loop.

Важно для хостинга: сбой поллинга НЕ должен убивать процесс — иначе Render
помечает деплой как update_failed. Поэтому сайт поднимается первым и всегда,
а бот работает под супервизором с ретраями. Состояние видно на /diag.
"""
from __future__ import annotations

import asyncio
import os
import time
import traceback

# Не даём боту поднимать собственный aiohttp-сервер на том же порту —
# на хостинге с одним PORT ему не место (порт занимает сайт).
os.environ.setdefault("WEB_DISABLE", "1")

import uvicorn  # noqa: E402
from website.app import app as site_app  # noqa: E402

# Диагностика старта для удалённого хостинга: /diag показывает, что происходит.
_state: dict = {"bot": "starting", "last_error": "", "restarts": 0, "started_at": time.time()}


@site_app.get("/diag")
async def _diag() -> dict:
    return dict(_state)


async def _serve_site() -> None:
    port = int(os.getenv("PORT") or "8080")
    config = uvicorn.Config(
        site_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def _run_bot() -> None:
    """Супервизор поллинга: не падает и перезапускается с паузой."""
    from bot import main as bot_main

    while True:
        try:
            _state["bot"] = "polling"
            _state["last_error"] = ""
            await bot_main()
            _state["bot"] = "stopped"
            return
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            _state["bot"] = "error"
            _state["last_error"] = traceback.format_exc()[-1500:]
            _state["restarts"] += 1
            await asyncio.sleep(10)


async def main() -> None:
    # Сайт живёт всегда и поднимается первым — порт открыт, деплой проходит.
    site_task = asyncio.create_task(_serve_site())
    bot_task = asyncio.create_task(_run_bot())
    try:
        await asyncio.gather(site_task, bot_task)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001
        _state["last_error"] = traceback.format_exc()[-1500:]
        # Сайт продолжает работать даже при фатальной ошибке.
        await site_task


if __name__ == "__main__":
    asyncio.run(main())
