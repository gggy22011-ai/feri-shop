"""
Анти-DDoS для сайта: считает HTTP-запросы по IP.

Если с одного IP приходит больше config.DDOS_MAX_REQUESTS_PER_MIN запросов
за окно config.DDOS_WINDOW_SECONDS — этот IP блокируется на
config.DDOS_BAN_SECONDS (по умолчанию 5 минут) и получает 429
с заголовком Retry-After.

Хранилище — in-memory (словари timestamps + время окончания бана).
После перезапуска сайта счётчики обнуляются — приемлемо для небольшого магазина.

Прокси-заголовки: X-Forwarded-For / X-Real-IP (если сайт стоит за nginx/CDN).
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock

import config
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_EXEMPT_PREFIXES = ("/healthz", "/static", "/favicon")

# ip -> очередь меток времени запросов
_REQUEST_LOG: dict[str, deque[float]] = {}
# ip -> время, до которого действует бан
_BANS: dict[str, float] = {}

_lock = Lock()


def client_ip(request: Request) -> str:
    """Определяет реальный IP клиента (с учётом прокси)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    x_rip = request.headers.get("x-real-ip")
    if x_rip:
        return x_rip.strip()
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    """Ленивая уборка устаревших окон и истёкших банов."""
    for ip in list(_REQUEST_LOG):
        dq = _REQUEST_LOG[ip]
        while dq and dq[0] < now - config.DDOS_WINDOW_SECONDS:
            dq.popleft()
        if not dq:
            _REQUEST_LOG.pop(ip, None)
    for ip in list(_BANS):
        if _BANS[ip] <= now:
            _BANS.pop(ip, None)


def ban_remaining(ip: str, now: float) -> int:
    """Сколько секунд ещё действует бан (0 — не забанен)."""
    until = _BANS.get(ip, 0.0)
    return max(0, int(until - now))


def register_hit(ip: str, now: float) -> bool:
    """Учитывает запрос от IP. Возвращает True, если IP пора забанить."""
    with _lock:
        _prune(now)
        dq = _REQUEST_LOG.setdefault(ip, deque())
        dq.append(now)
        if len(dq) > config.DDOS_MAX_REQUESTS_PER_MIN:
            _BANS[ip] = now + config.DDOS_BAN_SECONDS
            _REQUEST_LOG.pop(ip, None)
            return True
    return False


def _too_many(ip: str, now: float):
    remaining = ban_remaining(ip, now) or config.DDOS_BAN_SECONDS
    return JSONResponse(
        {
            "detail": "Слишком много запросов с вашего IP. "
                      f"Доступ временно заблокирован. Повторите через {remaining} сек.",
        },
        status_code=429,
        headers={"Retry-After": str(remaining)},
    )


class DDOSMiddlewware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        ip = client_ip(request)
        now = time.time()

        if ban_remaining(ip, now) > 0:
            return _too_many(ip, now)

        if register_hit(ip, now):
            return _too_many(ip, now)

        return await call_next(request)