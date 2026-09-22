"""
Точка входа магазина Feris Shop.

Запуск:  python bot.py
"""
from __future__ import annotations

import asyncio

import config
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database import init_db
from database import queries
from database.seed import seed_all
from web_server import _enabled, start_web_server
from handlers import (
    admin,
    deposit,
    donate,
    faq,
    get_code,
    my_numbers,
    orders,
    payments,
    profile,
    shop,
    start,
    support,
)
from keyboards.user_kb import main_menu_kb
from middlewares.ban_check import BanCheckMiddlewware
from middlewares.throttling import ThrottlingMiddlewware
from middlewares.user_register import UserRegisterMiddlewware
from utils.logger import setup_logger

logger = setup_logger().getChild("app")

bot: Bot | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Фоновые задачи (APScheduler)
# ─────────────────────────────────────────────────────────────────────────────
async def _job_release_reservations() -> None:
    """Сбрасывает зависшие брони номеров обратно в сток."""
    count = await queries.release_stale_reservations()
    if count:
        logger.info("Освобождено «зависших» броней: %d", count)


def setup_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _job_release_reservations,
        IntervalTrigger(minutes=5),
        id="release_reservations",
        replace_existing=True,
    )
    return scheduler


# ─────────────────────────────────────────────────────────────────────────────
# Сборка бота
# ─────────────────────────────────────────────────────────────────────────────
def create_dispatcher() -> Dispatcher:
    _bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    global bot
    bot = _bot

    dp = Dispatcher()

    # ── Общедоступный обработчик ошибок: «протухшие» колбэки (нажатие кнопки
    #    после даунтайма, когда query старше ~2 минут) — не критичная ошибка.
    @dp.errors()
    async def on_errors(event: ErrorEvent) -> bool:
        exc = event.exception
        if isinstance(exc, TelegramBadRequest) and "query is too old" in str(exc):
            return True
        if isinstance(exc, TelegramAPIError):
            logger.error("Telegram API: %s", exc)
            return True
        logger.error("Ошибка при обработке апдейта: %s", exc, exc_info=True)
        return True

    # ── Миддлвари (порядок важен: флуд → бан → регистрация)
    dp.message.middleware(ThrottlingMiddlewware())
    dp.callback_query.middleware(ThrottlingMiddlewware())

    dp.message.middleware(BanCheckMiddlewware())
    dp.callback_query.middleware(BanCheckMiddlewware())

    dp.message.middleware(UserRegisterMiddlewware())
    dp.callback_query.middleware(UserRegisterMiddlewware())

    # ── Админ-роутер первый
    dp.include_router(admin.router)

    # ── Платежи и пользовательские роутеры
    dp.include_router(payments.router)
    dp.include_router(start.router)
    dp.include_router(shop.router)
    dp.include_router(my_numbers.router)
    dp.include_router(get_code.router)
    dp.include_router(orders.router)
    dp.include_router(profile.router)
    dp.include_router(deposit.router)
    dp.include_router(donate.router)
    dp.include_router(support.router)
    dp.include_router(faq.router)

    return dp


# ─────────────────────────────────────────────────────────────────────────────
# Запуск
# ─────────────────────────────────────────────────────────────────────────────
async def main() -> None:
    if not config.BOT_TOKEN:
        logger.error("BOT_TOKEN не задан в .env! Заполни .env и перезапусти.")
        return

    # Защита от дублей (эта сборка Python порождает два поллингера,
    # а `Global\`-мьютекс действует во всех сессиях Windows).
    import ctypes  # noqa: PLC0415
    import os  # noqa: PLC0415

    if os.name == "nt":
        h_mutex = ctypes.windll.kernel32.CreateMutexW(
            None, False, "Global\\feris_shop_bot_mutex"
        )
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            logger.warning("Бот уже запущен в другом процессе — дубль выходит.")
            return
        globals()["_H_MUTEX"] = h_mutex  # держим дескриптор, пока жив процесс

    logger.info("Инициализация БД %s …", config.DB_URL)
    await init_db()
    await seed_all()

    dp = create_dispatcher()
    scheduler = setup_scheduler()
    scheduler.start()

    # Keep-alive для бесплатных хостов (Render и т.п.): на PORT (задан хостером)
    # поднимается /healthz, который пингует UptimeRobot/keepalive.py каждые 5 минут,
    # чтобы бесплатный инстанс не «засыпал».
    try:
        if _enabled():
            await start_web_server()
    except Exception:  # noqa: BLE001
        logger.exception("WEB-сервер не запустился, но поллинг продолжится")

    logger.info(
        "🚀 Feris Shop запущен! Юзернейм: %s · Владельцы: %s",
        config.BOT_USERNAME,
        ", ".join(config.OWNER_USERNAMES) or "не заданы!",
    )

    # Уведомление владельцам об успешном старте
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                "✅ Feris Shop запущен и работает.",
                reply_markup=main_menu_kb(),
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановка Feris Shop…")