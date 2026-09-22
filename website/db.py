"""Чтение данных магазина из bot.db для веб-сайта Feris Shop (новая схема)."""
from __future__ import annotations

import os
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402

STARS_TO_RUBLE = config.STARS_TO_RUBLE or 1.7


def db_path() -> str:
    url = config.DB_URL or f"sqlite+aiosqlite:///{os.path.join(PROJECT_ROOT, 'bot.db')}"
    return url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _has_table() -> bool:
    try:
        with _conn() as c:
            c.execute("select 1 from numbers limit 1")
        return True
    except sqlite3.Error:
        return False


def get_settings() -> dict[str, str]:
    if not _has_table():
        return {}
    try:
        with _conn() as c:
            rows = c.execute("select key, value from settings").fetchall()
        return {r["key"]: r["value"] for r in rows}
    except sqlite3.Error:
        return {}


def money(amount: float | int) -> str:
    return f"{amount:g} ₽"


def mask_phone(phone: str) -> str:
    if len(phone) > 4:
        return "*" * (len(phone) - 4) + phone[-2:]
    return phone


def _country_rows() -> list[dict]:
    """Страны из базы доступных номеров."""
    if not _has_table():
        return []
    with _conn() as c:
        rows = c.execute(
            """
            select country, country_flag, count(*) as avail,
                   min(price_rubles) as min_price,
                   min(phone_number) as sample_phone
            from numbers
            where status = 'available'
            group by country, country_flag
            order by country
            """
        ).fetchall()
    result = []
    for idx, r in enumerate(rows, 1):
        price_rub = round(r["min_price"] or 0, 2)
        result.append({
            "id": idx,
            "name": r["country"],
            "flag": r["country_flag"] or "🌐",
            "prefix": "+" + r["sample_phone"].lstrip("+")[:3] if r["sample_phone"] else "",
            "price": price_rub,
            "sort_order": idx,
            "available": r["avail"],
        })
    return result


def get_countries() -> list[dict]:
    return _country_rows()


def get_country(country_id: int) -> dict | None:
    countries = _country_rows()
    for c in countries:
        if c["id"] == country_id:
            return c
    return None


def get_available_numbers(country_id: int, limit: int = 30) -> list[dict]:
    ctry = get_country(country_id)
    if not ctry:
        return []
    with _conn() as c:
        rows = c.execute(
            """
            select id, phone_number from numbers
            where country = ? and status = 'available'
            order by id limit ?
            """,
            (ctry["name"], limit),
        ).fetchall()
    return [{"id": r["id"], "phone": r["phone_number"]} for r in rows]


def get_stats() -> dict:
    if not _has_table():
        return {"countries": 0, "available": 0, "sold": 0, "users": 0, "orders": 0}
    with _conn() as c:
        countries = c.execute(
            "select count(distinct country) from numbers where status = 'available'"
        ).fetchone()[0]
        available = c.execute(
            "select count(*) from numbers where status = 'available'"
        ).fetchone()[0]
        sold = c.execute("select count(*) from numbers where status = 'sold'").fetchone()[0]
        users = c.execute("select count(*) from users").fetchone()[0]
    return {
        "countries": countries,
        "available": available,
        "sold": sold,
        "users": users,
        "orders": sold,
    }


def find_orders_by_user(tg_id: int) -> list[dict]:
    """Купленные номера юзера в виде, совместимом со старыми шаблонами."""
    if not _has_table():
        return []
    with _conn() as c:
        rows = c.execute(
            """
            select id, phone_number, country, country_flag,
                   price_rubles, sold_at
            from numbers
            where owner_id = ? and status = 'sold'
            order by sold_at desc, id desc limit 50
            """,
            (tg_id,),
        ).fetchall()
    result = []
    for idx, r in enumerate(rows, 1):
        result.append({
            "id": idx,
            "phone": r["phone_number"].lstrip("+") if r["phone_number"] else "",
            "country": r["country"],
            "flag": r["country_flag"] or "",
            "amount": round(r["price_rubles"] or 0, 2),
            "created_at": (r["sold_at"] or "")[:19],
            "status": "success",
        })
    return result


if __name__ == "__main__":
    import json

    print(json.dumps({"stats": get_stats()}, ensure_ascii=False, indent=2))
    print("countries:", len(get_countries()))