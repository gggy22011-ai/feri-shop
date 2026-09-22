"""
Анти-флуд и анти-DDoS (по юзеру) для бота.

1. Общий лимит: между действиями юзера — config.FLOOD_RATE_LIMIT сек.
2. Бурст-детект (аналог «бана IP», т.к. у бота нет IP — работаем по
   telegram user_id): если один юзер шлёт больше
   config.BURST_MAX_ACTIONS событий за config.BURST_WINDOW_SECONDS —
   он временно (config.BURST_BAN_SECONDS, по умолчанию 5 минут) банится.
   Все его события на время бана игнорируются, владельцам идёт уведомление.

Хранилище в памяти: после перезапуска счётчики обнуляются.
"""
from __future__ import annotations

import time
from collections import deque

import config
from aiogram import BaseMiddleware
from utils.logger import get_logger

logger = get_logger("throttle")

# user_id -> последний обработанный вызов (общий флуд-лимит)
_last_seen: dict[int, float] = {}
# user_id -> окно последних событий (для бурст-детекта)
_burst_log: dict[int, deque[float]] = {}
# user_id -> время окончания временного бана
_temp_bans: dict[int, float] = {}
# user_id, по которому уже уведомили владельцев (чтобы не спамить повторно)
_notified: set[int] = set()


def _prune(now: float) -> None:
    for uid, dq in list(_burst_log.items()):
        while dq and dq[0] < now - config.BURST_WINDOW_SECONDS:
            dq.popleft()
        if not dq:
            _burst_log.pop(uid, None)
    for uid in list(_temp_bans):
        if _temp_bans[uid] <= now:
            _temp_bans.pop(uid, None)
            _notified.discard(uid)
    # старые метки общего флуд-лимита не нужны
    for uid in list(_last_seen):
        if now - _last_seen[uid] > 3600:
            _last_seen.pop(uid, None)


def temp_ban_remaining(uid: int, now: float | None = None) -> int:
    """Сколько секунд осталось у временного бана (0 — бан не действует)."""
    now = now or time.monotonic()
    return max(0, int(_temp_bans.get(uid, 0.0) - now))


class ThrottlingMiddlewware(BaseMiddleware):
    def __init__(self, limit: float = config.FLOOD_RATE_LIMIT):
        super().__init__()
        self.limit = limit

    async def __call__(self, handler, event, data) -> None:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        # Админов и владельцев флуд-контроль не трогает.
        if config.is_owner(user.id, user.username):
            return await handler(event, data)

        now = time.monotonic()

        # Временный бан (анти-DDoS) действует — события игнорируем.
        if _temp_bans.get(user.id, 0.0) > now:
            return None

        # Анти-DDoS: считаем ВСЕ события юзера в окне.
        dq = _burst_log.setdefault(user.id, deque())
        dq.append(now)
        _prune(now)
        if len(dq) > config.BURST_MAX_ACTIONS:
            _temp_bans[user.id] = now + config.BURST_BAN_SECONDS
            _burst_log.pop(user.id, None)
            logger.warning("Анти-DDoS: авто-бан юзера %s на %s сек",
                           user.id, config.BURST_BAN_SECONDS)
            await self._notify_ban(event, user)
            return None

        # Общий флуд-лимит: не чаще 1 действия за FLOOD_RATE_LIMIT сек.
        last = _last_seen.get(user.id, 0.0)
        if now - last < self.limit:
            return None
        _last_seen[user.id] = now
        return await handler(event, data)

    @staticmethod
    async def _notify_ban(event, user) -> None:
        if user.id in _notified:
            return
        _notified.add(user.id)
        try:
            from utils.notify import notify_owners

            name = user.full_name or user.username or str(user.id)
            await notify_owners(
                event.bot,
                "⚠️ Анти-DDoS (бот): авто-бан на "
                f"{config.BURST_BAN_SECONDS // 60} мин.\n"
                f"Юзер: {name} (@{user.username or '-'})\n"
                f"ID: {user.id}\n"
                f"Причина: >{config.BURST_MAX_ACTIONS} действий за "
                f"{int(config.BURST_WINDOW_SECONDS)} сек.",
            )
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка уведомления об авто-бане")