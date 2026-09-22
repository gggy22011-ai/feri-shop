"""
Уведомления владельцам бота (@Clulk, @No7777oN).
"""
from __future__ import annotations

import config
from aiogram import Bot
from utils.logger import get_logger

logger = get_logger("notify")

# username -> telegram user_id (кэшируется после первого обращения).
_owner_ids: dict[str, int] = {}
_owner_ids_loaded = False


async def resolve_owner_ids(bot: Bot) -> list[int]:
    """Возвращает list telegram-id владельцев (по возможности)."""
    global _owner_ids_loaded
    ids = list(config.ADMIN_IDS)
    if not _owner_ids_loaded:
        for uname in config.OWNER_USERNAMES:
            if uname in _owner_ids:
                continue
            try:
                chat = await bot.get_chat(f"@{uname}")
                if chat.id:
                    _owner_ids[uname] = chat.id
            except Exception:  # noqa: BLE001
                logger.warning("Не удалось резолвить владельца @%s", uname)
        _owner_ids_loaded = True
    ids.extend(_owner_ids.values())
    return list(dict.fromkeys(ids))


async def notify_owners(bot: Bot, text: str) -> None:
    """Отправляет сообщение всем владельцам (best-effort)."""
    for owner_id in await resolve_owner_ids(bot):
        try:
            await bot.send_message(owner_id, text)
        except Exception:  # noqa: BLE001
            logger.warning("Не удалось уведомить владельца %s", owner_id)


def clear_owner_cache() -> None:
    """Сброс кэша (полезно, если username владельца изменился)."""
    global _owner_ids_loaded
    _owner_ids_loaded = False
    _owner_ids.clear()