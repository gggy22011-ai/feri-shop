"""
Блокировка заблокированных юзеров.
Заблокированный не может пользоваться ботом (кроме /start — чтобы увидеть
причину и написать в поддержку, если оператор разблокирует).
"""
from __future__ import annotations

import config
from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from utils.logger import get_logger
from utils.texts import BANNED_TEXT

logger = get_logger("ban")

ALLOW_FOR_BANNED = {"/start", "/help", "/admin"}


class BanCheckMiddlewware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(self, handler, event, data) -> None:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        # Админов и владельцев бан не трогает
        if config.is_owner(user.id, user.username):
            return await handler(event, data)

        from database import queries  # ленивый импорт

        db_user = await queries.get_user(user.id)
        if db_user and db_user.is_blocked:
            if isinstance(event, Message):
                if event.text and event.text in ALLOW_FOR_BANNED:
                    return await handler(event, data)
                await event.answer(BANNED_TEXT)
            elif isinstance(event, CallbackQuery):
                await event.answer("🚫 Вы заблокированы", show_alert=True)
            return None

        return await handler(event, data)