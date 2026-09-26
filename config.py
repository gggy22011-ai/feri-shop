"""
Центральные настройки магазина Feris Shop.
Все секреты и бизнес-параметры — из .env, в коде ничего не хардкодим.
"""
from __future__ import annotations

import logging
import os
import pathlib
from pathlib import Path

from dotenv import load_dotenv

# Папка проекта (там, где лежит config.py) — якорь для относительных путей.
PROJECT_DIR: Path = pathlib.Path(__file__).resolve().parent

# Загружаем .env именно из папки проекта. Намеренно НЕ вызываем load_dotenv()
# без аргумента: он ищет .env от CWD и может подхватить чужой/старый файл
# (например, токен из .env родительской папки), который перекроет правильный.
load_dotenv(PROJECT_DIR / ".env")


def _resolve_db_url(raw: str) -> str:
    """Приводит относительный sqlite-путь к абсолютному внутри папки проекта.

    Иначе при запуске bot.py из другой директории создаётся вторая БД
    непонятно где, и продажи «пропадают».
    """
    prefix = "sqlite+aiosqlite:///"
    if raw.startswith(prefix):
        rel = raw[len(prefix):]
        if rel and not os.path.isabs(rel):
            return prefix + str(PROJECT_DIR / rel)
    return raw


def _parse_int_list(raw: str) -> list[int]:
    """Строка '1,2,3' -> [1,2,3]. Мусор отбрасываем."""
    result = []
    for part in (raw or "").replace(" ", "").split(","):
        if part.isdigit():
            result.append(int(part))
    return result


def _parse_str_list(raw: str) -> list[str]:
    """Строка '@a,@b' -> ['a', 'b'] (без @, в нижнем регистре)."""
    result = []
    for part in (raw or "").replace(" ", "").split(","):
        part = part.strip().lstrip("@").lower()
        if part:
            result.append(part)
    return result


def _as_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _as_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _as_bool(key: str, default: bool = False) -> bool:
    raw = str(os.getenv(key, "1" if default else "0")).strip().lower()
    return raw in ("1", "true", "yes", "on", "да")


def _parse_kv_map(raw: str) -> dict[str, str]:
    """'Россия=0;Казахстан=4' -> {'россия': '0', 'казахстан': '4'} (ключи в нижнем регистре)."""
    out: dict[str, str] = {}
    for chunk in (raw or "").replace("\n", ";").split(";"):
        if "=" not in chunk:
            continue
        k, v = chunk.split("=", 1)
        k = k.strip().lower()
        v = v.strip()
        if k and v:
            out[k] = v
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Основные
# ─────────────────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "Shootingferi_bot")
SHOP_NAME: str = "Feris Shop"
SIGNATURE: str = (
    "С уважением, Feris Shop 🤝\n"
    f"Канал: {os.getenv('CHANNEL_1', '@feris_shop')} | "
    f"Поддержка: {os.getenv('SUPPORT_USERNAME', '@No7777oN')}"
)

# ─────────────────────────────────────────────────────────────────────────────
# Владельцы / админка
# ─────────────────────────────────────────────────────────────────────────────
# Владельцы — полные права без пароля. Указываются @username из .env OWNERS.
OWNER_USERNAMES: list[str] = _parse_str_list(
    os.getenv("OWNERS", "@Clulk,@No7777oN")
)
# Числовые fallback-админы (telegram user_id) на случай, если нет @username.
ADMIN_IDS: list[int] = _parse_int_list(os.getenv("ADMIN_IDS", ""))
# Пароль доступа к админке для всех, кроме владельцев.
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

MAX_PASSWORD_ATTEMPTS: int = 3
PASSWORD_BLOCK_SECONDS: int = 5 * 60      # блок после 3 неверных паролей
ADMIN_SESSION_TTL_SECONDS: int = 30 * 60  # срок жизни сессии без активности

# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────
# Поддержка / канал
# ─────────────────────────────────────────────────────────────────────
SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "@No7777oN")
CHANNEL_USERNAME: str = os.getenv("CHANNEL_1", "@feris_shop")
CHANNEL_URL: str = os.getenv("CHANNEL_1_URL", "https://t.me/feris_shop")
# Кто принимает оплату (по ТЗ — @Clulk).
PAYMENT_USERNAME: str = os.getenv("PAYMENT_USERNAME", "@Clulk")
# Кто принимает оплату РЕАЛЬНЫМИ звёздами — по ТЗ второй владелец (@No7777oN).
# Принимается через STAR_OWNER в .env, по умолчанию — второй владелец из OWNERS.
STAR_OWNER_USERNAME: str = os.getenv(
    "STAR_OWNER",
    f"@{OWNER_USERNAMES[1]}" if len(OWNER_USERNAMES) > 1 else PAYMENT_USERNAME,
)
STAR_OWNER: str = STAR_OWNER_USERNAME.lstrip("@")
# Краткий бейдж владельцев для текстов.
OWNER_BADGE: str = ", ".join(OWNER_USERNAMES) or "Feris Shop"

# ─────────────────────────────────────────────────────────────────────────────
# Финансы
# ─────────────────────────────────────────────────────────────────────────────
# Курс по ТЗ: 1 ₽ = STARS_PER_RUBLE ⭐ (для звёзд). Т.е. 269 ₽ = 390 ⭐.
STARS_PER_RUBLE: float = _as_float("STARS_PER_RUBLE", 1.45)
# Обратный курс для отображения: 1 ⭐ ≈ RUBLES_PER_STAR ₽.
RUBLES_PER_STAR: float = round(1.0 / STARS_PER_RUBLE, 4) if STARS_PER_RUBLE else 1.0
# Алиас (исторический): 1 ⭐ = STARS_TO_RUBLE ₽
STARS_TO_RUBLE: float = RUBLES_PER_STAR

# Ссылка/реквизиты для пополнения рублями (если задана в .env).
# Если пусто — юзеру показываются контакты поддержки.
RUBLE_CARD: str = os.getenv("RUBLE_CARD", "")

# Фото для оплаты (его @Clulk скидывает покупателю — реквизиты/QR).
# Показывается сразу при нажатии «Пополнить баланс» и отправляется @Clulk.
DEPOSIT_PHOTO_FILE: str = os.getenv(
    "DEPOSIT_PHOTO_FILE", os.path.join("assets", "deposit.png")
)

DB_URL: str = _resolve_db_url(
    os.getenv("DB_URL", "sqlite+aiosqlite:///bot.db")
)

# ─────────────────────────────────────────────────────────────────────────────
# Автовыдача реальных номеров (сервисы приёма SMS)
# ─────────────────────────────────────────────────────────────────────────────
# Провайдер: "sms-activate" | "5sim" | "test" | "" (выключено — ручной режим).
SMS_PROVIDER: str = os.getenv("SMS_PROVIDER", "").strip().lower()
SMS_ACTIVATE_KEY: str = os.getenv("SMS_ACTIVATE_KEY", "").strip()
FIVESIM_KEY: str = os.getenv("FIVESIM_KEY", "").strip()
# Ключ нужного провайдера подставляется сюда автоматически (см. sms_api.py).
SMS_API_KEY: str = SMS_ACTIVATE_KEY if SMS_PROVIDER == "sms-activate" else FIVESIM_KEY

# Автоматически закупать реальный номер сразу после оплаты.
SMS_AUTO_ISSUE: bool = _as_bool("SMS_AUTO_ISSUE", True)
# Код сервиса у провайдера: tg = Telegram.
SMS_SERVICE: str = os.getenv("SMS_SERVICE", "tg").strip() or "tg"
# Наценка на закупочную цену номера (1.3 = +30% к цене сервиса).
SMS_PRICE_MARKUP: float = _as_float("SMS_PRICE_MARKUP", 1.3)
# Как часто опрашивать сервис ради кодов (сек).
SMS_POLL_SECONDS: int = _as_int("SMS_POLL_SECONDS", 20)
# Сколько ждём SMS до истечения активации (мин).
SMS_WAIT_MINUTES: int = _as_int("SMS_WAIT_MINUTES", 20)
# Мапа «страна из витрины -> код страны у провайдера»:
# "Россия=0;Казахстан=4;Украина=1".
SMS_COUNTRY_MAP: dict[str, str] = _parse_kv_map(os.getenv("SMS_COUNTRY_MAP", ""))
# Страна по умолчанию, если для неё нет мапы.
SMS_COUNTRY_DEFAULT: str = os.getenv("SMS_COUNTRY_DEFAULT", "0").strip() or "0"
# Таймаут HTTP-запроса к сервису (сек).
SMS_HTTP_TIMEOUT: int = _as_int("SMS_HTTP_TIMEOUT", 30)


def sms_provider_ready() -> bool:
    """Готова ли автовыдача: провайдер выбран и ключ задан."""
    if not SMS_PROVIDER or SMS_PROVIDER == "test":
        return SMS_PROVIDER == "test"
    return bool(SMS_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Прочее
# ─────────────────────────────────────────────────────────────────────────────
FLOOD_RATE_LIMIT: float = 0.7             # анти-флуд: мин. интервал (сек)
RESERVATION_TTL_SECONDS: int = 15 * 60    # автосброс «забронированных» номеров
LOGS_DIR: str = os.getenv("LOGS_DIR", "logs")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ─────────────────────────────────────────────────────────────────────────────
# Анти-DDoS: сайт (по IP) и бот (по юзеру)
# ─────────────────────────────────────────────────────────────────────────────
# Сайт: больше DDOS_MAX_REQUESTS_PER_MIN запросов с одного IP за окно
# DDOS_WINDOW_SECONDS → IP банится на DDOS_BAN_SECONDS (по умолчанию 5 минут).
DDOS_WINDOW_SECONDS: int = _as_int("DDOS_WINDOW_SECONDS", 60)
DDOS_MAX_REQUESTS_PER_MIN: int = _as_int("DDOS_MAX_REQUESTS_PER_MIN", 120)
DDOS_BAN_SECONDS: int = _as_int("DDOS_BAN_SECONDS", 5 * 60)

# Бот: если один юзер шлёт больше BURST_MAX_ACTIONS действий за
# BURST_WINDOW_SECONDS (в дополнение к общему флуд-лимиту) — временный бан
# на BURST_BAN_SECONDS (по умолчанию 5 минут) с уведомлением владельцев.
BURST_WINDOW_SECONDS: float = _as_int("BURST_WINDOW_SECONDS", 10) * 1.0
BURST_MAX_ACTIONS: int = _as_int("BURST_MAX_ACTIONS", 25)
BURST_BAN_SECONDS: int = _as_int("BURST_BAN_SECONDS", 5 * 60)


def log_level_int() -> int:
    return getattr(logging, LOG_LEVEL.upper(), logging.INFO)


def is_owner(user_id: int = 0, username: str | None = "") -> bool:
    """Владелец ли пользователь (id из ADMIN_IDS или @username из OWNERS)."""
    if user_id and user_id in ADMIN_IDS:
        return True
    if username:
        return username.lower().strip().lstrip("@") in OWNER_USERNAMES
    return False