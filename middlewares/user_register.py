"""
Авторегистрация юзера и обновление last_active.
Срабатывает на каждое сообщение/колбэк. При первой регистрации кладёт
в data флаг db_is_new=True (для приветствия и уведомления владельцам).
"""
from __future__ import annotations

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from database import queries
from utils.logger import get_logger

logger = get_logger("register")


class UserRegisterMiddlewware(BaseMiddleware):
    def __init__(self) -> None:
        super().__init__()

    async def __call__(self, handler, event, data) -> None:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        try:
            _, is_new = await queries.get_or_create_user(
                tg_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            data["db_is_new"] = is_new
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось регистрацию юзера %s: %s", user.id, exc)
            data["db_is_new"] = False

        return await handler(event, data)