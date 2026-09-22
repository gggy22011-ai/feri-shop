"""
Универсальные хелперы Feris Shop.
"""
from __future__ import annotations

from datetime import datetime

import config


# ─────────────────────────────────────────────────────────────────────────────
# Форматирование
# ─────────────────────────────────────────────────────────────────────────────
def rub(amount: float | int) -> str:
    """Форматирует сумму как '<N> ₽' (без дробей, если целая)."""
    f = float(amount)
    if f == int(f):
        return f"{int(f)} ₽"
    return f"{f:.2f} ₽".replace(".", ",")


def stars_to_rubles(stars: int | float) -> float:
    return round(float(stars) * config.STARS_TO_RUBLE, 2)


def dt_format(dt: datetime | None) -> str:
    """datetime -> 'DD.MM.YYYY HH:MM'"""
    return dt.strftime("%d.%m.%Y %H:%M") if dt else "—"


def date_format(dt: datetime | None) -> str:
    return dt.strftime("%d.%m.%Y") if dt else "—"


# ─────────────────────────────────────────────────────────────────────────────
# Валидация ввода админа / суммы
# ─────────────────────────────────────────────────────────────────────────────
def parse_user_input(raw: str) -> int:
    """Число из строки (user_id, сумма). Кидает ValueError."""
    raw = raw.strip()
    if not raw.isdigit():
        raise ValueError(raw)
    return int(raw)


def parse_money_input(raw: str) -> float:
    """Сумма денег (целое или с копейками). Кидает ValueError."""
    raw = raw.strip().replace(",", ".")
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(raw) from exc
    if value <= 0:
        raise ValueError(raw)
    return round(value, 2)