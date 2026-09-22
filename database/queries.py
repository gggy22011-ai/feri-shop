"""
Работа с БД Feris Shop: пользователи, страны, номера, заказы, SMS,
баг-репорты, балансы, транзакции, админ-логи.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta

import config
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .core import get_session
from .models import (
    AdminLog,
    BugReport,
    Country,
    Number,
    Order,
    Setting,
    Sms,
    Transaction,
    User,
)

NumberStatus = ("available", "reserved", "sold")
OrderStatus = ("pending", "paid", "cancelled")


# ─────────────────────────────────────────────────────────────────────────────
# Пользователи
# ─────────────────────────────────────────────────────────────────────────────
async def get_or_create_user(
    tg_id: int,
    username: str | None = None,
    first_name: str | None = None,
    referrer_id: int | None = None,
) -> tuple[User, bool]:
    """Возвращает (user, is_new). Регистрирует первого /start."""
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            stmt = (
                sqlite_insert(User)
                .values(
                    id=tg_id,
                    username=username,
                    first_name=first_name,
                    stars_balance=0,
                    rubles_balance=0.0,
                    referrer_id=None,
                    is_blocked=False,
                )
                .on_conflict_do_nothing(index_elements=["id"])
            )
            await session.execute(stmt)
            await session.commit()
            for _ in range(5):
                user = await session.get(User, tg_id)
                if user is not None:
                    if referrer_id and referrer_id != tg_id:
                        user.referrer_id = referrer_id
                        await session.commit()
                        await session.refresh(user)
                    return user, True
                await asyncio.sleep(0.02)
        changed = False
        user.last_active = datetime.utcnow()
        if username != user.username:
            user.username = username
            changed = True
        if not user.first_name and first_name:
            user.first_name = first_name
            changed = True
        if not user.referrer_id and referrer_id and referrer_id != tg_id:
            user.referrer_id = referrer_id
            changed = True
        if changed:
            await session.commit()
            await session.refresh(user)
        return user, False


async def get_user(tg_id: int) -> User | None:
    async with get_session() as session:
        return await session.get(User, tg_id)


async def find_user_by_username(clean_username: str) -> User | None:
    """Ищет юзера по @username (без @, регистр не важен)."""
    needle = clean_username.lower().lstrip("@")
    async with get_session() as session:
        users = await session.scalars(select(User))
        for u in users:
            if u.username and u.username.lower().lstrip("@") == needle:
                return u
    return None


async def set_user_blocked(tg_id: int, blocked: bool) -> User | None:
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return None
        user.is_blocked = blocked
        await session.commit()
        await session.refresh(user)
        return user


async def all_user_ids() -> list[int]:
    async with get_session() as session:
        rows = await session.scalars(select(User.id))
        return list(rows)


async def all_users() -> list[User]:
    async with get_session() as session:
        return list(await session.scalars(select(User)))


# ─────────────────────────────────────────────────────────────────────────────
# Балансы / транзакции
# ─────────────────────────────────────────────────────────────────────────────
async def add_transaction(
    user_id: int, type_: str, amount: float, description: str | None = None
) -> None:
    async with get_session() as session:
        session.add(Transaction(user_id=user_id, type=type_, amount=amount, description=description))
        await session.commit()


async def add_stars(tg_id: int, stars: int, description: str) -> bool:
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return False
        user.stars_balance += int(stars)
        await session.commit()
    await add_transaction(tg_id, "stars_in", int(stars), description)
    return True


async def subtract_stars(tg_id: int, stars: int) -> bool:
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None or user.stars_balance < stars:
            return False
        user.stars_balance -= int(stars)
        await session.commit()
    await add_transaction(tg_id, "stars_out", int(stars), "⭐ Оплата с баланса")
    return True


async def add_rubles(tg_id: int, rubles: float, description: str) -> bool:
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return False
        user.rubles_balance += float(rubles)
        await session.commit()
    await add_transaction(tg_id, "rubles_in", float(rubles), description)
    return True


async def subtract_rubles(tg_id: int, rubles: float) -> bool:
    """Списывает рубли (без транзакции). Возвращает False, если не хватает."""
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None or user.rubles_balance < float(rubles):
            return False
        user.rubles_balance = round(user.rubles_balance - float(rubles), 2)
        await session.commit()
        return True


async def change_rubles(
    tg_id: int, delta: float, type_: str, description: str
) -> float | None:
    """Изменяет рублёвый баланс на delta (может быть отрицательной)."""
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None:
            return None
        user.rubles_balance = round(user.rubles_balance + float(delta), 2)
        await session.commit()
        balance = user.rubles_balance
    await add_transaction(tg_id, type_, float(delta), description)
    return balance


async def subtract_rubles(tg_id: int, rubles: float) -> bool:
    async with get_session() as session:
        user = await session.get(User, tg_id)
        if user is None or user.rubles_balance < rubles:
            return False
        user.rubles_balance -= float(rubles)
        await session.commit()
    await add_transaction(tg_id, "rubles_out", float(rubles), "₽ Оплата с баланса")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Номера: цены/парсинг
# ─────────────────────────────────────────────────────────────────────────────
def normalize_phone(raw: str) -> str:
    """Убирает пробелы/скобки/дефисы, оставляет +цифры."""
    digits = re.sub(r"[\s\-()]", "", raw.strip())
    if not digits.startswith("+"):
        digits = "+" + digits
    return digits


def rubles_to_stars(rubles: float | int) -> int:
    return max(1, round(float(rubles) * config.STARS_PER_RUBLE))


def stars_to_rubles(stars: int | float) -> float:
    return round(float(stars) * config.RUBLES_PER_STAR, 2)


def parse_price_part(part: str) -> float:
    """'269₽' | '269' | '390⭐' → цена в рублях."""
    part = part.strip().lower().replace(",", ".")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([a-zа-я⭐₽]*)$", part)
    if not m:
        raise ValueError(f"Не распознана цена: {part!r}")
    value = float(m.group(1))
    suffix = m.group(2)
    if "⭐" in suffix or "зв" in suffix or suffix == "s":
        value = float(value) * config.RUBLES_PER_STAR
    return round(max(0.01, value), 2)


def parse_number_lines(lines: list[str]) -> list[dict]:
    """Парсит строки формата «страна | номер | оператор | цена».

    Оператор и цена необязательны: «страна | номер | цена», «страна | номер».
    Цена по умолчанию в рублях: «269₽» или просто «269». «390⭐» — звёзды.
    """
    result: list[dict] = []
    for raw in lines:
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 2:
            raise ValueError(f"Некорректная строка: {raw!r}")
        country = parts[0]
        phone = normalize_phone(parts[1])
        operator = None
        price_rubles = 0.0
        rest = parts[2:]
        if rest:
            price_rubles = parse_price_part(rest[-1])
            if len(rest) >= 2:
                operator = rest[0]
        price_stars = rubles_to_stars(price_rubles) if price_rubles else 0
        result.append(
            {
                "country": country,
                "country_flag": fetch_flag(country),
                "phone_number": phone,
                "operator": operator,
                "price_rubles": price_rubles,
                "price_stars": price_stars,
            }
        )
    return result


COUNTRY_FLAGS = {
    "россия": "🇷🇺", "казахстан": "🇰🇿", "украина": "🇺🇦", "беларусь": "🇧🇾",
    "белоруссия": "🇧🇾", "сша": "🇺🇸", "америка": "🇺🇸", "германия": "🇩🇪",
    "франция": "🇫🇷", "великобритания": "🇬🇧", "англия": "🇬🇧", "испания": "🇪🇸",
    "италия": "🇮🇹", "польша": "🇵🇱", "чехия": "🇨🇿", "нидерланды": "🇳🇱",
    "латвия": "🇱🇻", "литва": "🇱🇹", "эстония": "🇪🇪", "финляндия": "🇫🇮",
    "швеция": "🇸🇪", "норвегия": "🇳🇴", "дания": "🇩🇰", "швейцария": "🇨🇭",
    "австрия": "🇦🇹", "бельгия": "🇧🇪", "греция": "🇬🇷", "румыния": "🇷🇴",
    "болгария": "🇧🇬", "сербия": "🇷🇸", "хорватия": "🇭🇷", "япония": "🇯🇵",
    "китай": "🇨🇳", "индия": "🇮🇳", "турция": "🇹🇷", "израиль": "🇮🇱",
    "оаэ": "🇦🇪", "саудовская аравия": "🇸🇦", "узбекистан": "🇺🇿",
    "киргизия": "🇰🇬", "киргизстан": "🇰🇬", "таджикистан": "🇹🇯",
    "туркменистан": "🇹🇲", "азербайджан": "🇦🇿", "армения": "🇦🇲",
    "грузия": "🇬🇪", "молдова": "🇲🇩", "монголия": "🇲🇳", "вьетнам": "🇻🇳",
    "тайланд": "🇹🇭", "индонезия": "🇮🇩", "малайзия": "🇲🇾", "южная корея": "🇰🇷",
    "бразилия": "🇧🇷", "аргентина": "🇦🇷", "мексика": "🇲🇽", "канада": "🇨🇦",
    "египет": "🇪🇬", "марокко": "🇲🇦", "эквадор": "🇪🇨", "бангладеш": "🇧🇩",
    "пакистан": "🇵🇰", "иран": "🇮🇷", "иордания": "🇯🇴", "камерун": "🇨🇲",
    "кипр": "🇨🇾", "мавритания": "🇲🇷", "нигерия": "🇳🇬", "филиппины": "🇵🇭",
    "юар": "🇿🇦", "ангола": "🇦🇴", "австралия": "🇦🇺", "ирландия": "🇮🇪",
    "португалия": "🇵🇹", "словакия": "🇸🇰", "словения": "🇸🇮",
}


def fetch_flag(country: str) -> str:
    """Флаг страны: из встроенного словаря или из текста (если флаг уже встроен)."""
    key = country.strip().lower()
    mark = re.search(r"[\U0001F1E6-\U0001F1FF]{2}", country)
    if mark:
        return mark.group(0)
    return COUNTRY_FLAGS.get(key, "")


# ─────────────────────────────────────────────────────────────────────────────
# Страны (витрина)
# ─────────────────────────────────────────────────────────────────────────────
async def upsert_country(
    name: str, flag: str, price_rubles: float, enabled: bool = True
) -> None:
    name = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}\s*", "", name).strip() or name
    async with get_session() as session:
        c = await session.get(Country, name)
        if c is None:
            session.add(Country(name=name, country_flag=flag,
                                price_rubles=float(price_rubles), enabled=enabled))
        else:
            if flag:
                c.country_flag = flag
            c.price_rubles = float(price_rubles)
            c.enabled = enabled
        await session.commit()


async def get_country(name: str) -> Country | None:
    async with get_session() as session:
        return await session.get(Country, name)


async def remove_country(name: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(Country).where(Country.name == name)
        )
        await session.commit()
        return result.rowcount > 0


async def registered_countries() -> list[Country]:
    async with get_session() as session:
        return list(await session.scalars(select(Country).order_by(Country.name)))


async def countries_with_stock() -> list[tuple[str, str, int, float]]:
    """(страна, флаг, кол-во доступных, цена в ₽) для витрины.

    Основа — доступные номера в базе. Цена: из таблицы countries, если она
    там задана, иначе минимальная цена доступного номера страны.
    """
    async with get_session() as session:
        rows = await session.execute(
            select(
                Number.country,
                Number.country_flag,
                func.count(Number.id),
                func.min(Number.price_rubles),
            )
            .where(Number.status == "available")
            .group_by(Number.country, Number.country_flag)
            .order_by(Number.country)
        )
        raw = [(r[0], r[1], r[2], float(r[3] or 0.0)) for r in rows]
    prices_by_country: dict[str, float] = {}
    for c in await registered_countries():
        prices_by_country[c.name] = c.price_rubles
    result: list[tuple[str, str, int, float]] = []
    for country, flag, count, price in raw:
        price = prices_by_country.get(country, price)
        result.append((country, flag, count, price))
    return result


async def set_country_enabled(name: str, enabled: bool) -> bool:
    async with get_session() as session:
        c = await session.get(Country, name)
        if c is None:
            return False
        c.enabled = enabled
        await session.commit()
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Номера: склад
# ─────────────────────────────────────────────────────────────────────────────
async def add_numbers(items: list[dict]) -> int:
    """Добавляет номера в базу. Пропускает уже существующие."""
    added = 0
    existing = set()
    async with get_session() as session:
        rows = await session.scalars(select(Number.phone_number))
        existing = set(rows)
        for item in items:
            if item["phone_number"] in existing:
                continue
            if "price_stars" not in item:
                item = dict(item)
                item["price_stars"] = rubles_to_stars(item.get("price_rubles", 0)) \
                    if item.get("price_rubles") else 0
            session.add(Number(**item))
            existing.add(item["phone_number"])
            added += 1
        await session.commit()
    return added


async def get_number(nid: int) -> Number | None:
    async with get_session() as session:
        return await session.get(Number, nid)


async def get_number_by_phone(phone: str) -> Number | None:
    needle = normalize_phone(phone)
    async with get_session() as session:
        return await session.scalar(
            select(Number).where(Number.phone_number == needle)
        )


async def delete_number(nid: int) -> bool:
    async with get_session() as session:
        result = await session.execute(
            delete(Number).where(Number.id == nid, Number.status == "available")
        )
        await session.commit()
        return result.rowcount > 0


async def available_numbers(country: str | None = None) -> list[Number]:
    async with get_session() as session:
        stmt = select(Number).where(Number.status == "available")
        if country:
            stmt = stmt.where(Number.country == country)
        stmt = stmt.order_by(Number.id)
        return list(await session.scalars(stmt))


async def available_number_count(country: str | None = None) -> int:
    async with get_session() as session:
        stmt = select(func.count(Number.id)).where(Number.status == "available")
        if country:
            stmt = stmt.where(Number.country == country)
        return int(await session.scalar(stmt) or 0)


async def reserve_number(nid: int, user_id: int) -> Number | None:
    """Атомарно бронирует номер (защита от двойной продажи)."""
    async with get_session() as session:
        result = await session.execute(
            update(Number)
            .where(Number.id == nid, Number.status == "available")
            .values(status="reserved", reserved_by=user_id, reserved_at=datetime.utcnow())
        )
        await session.commit()
        if result.rowcount == 0:
            return None
        return await session.get(Number, nid)


async def release_stale_reservations() -> int:
    """Возвращает просроченные брони обратно в сток."""
    async with get_session() as session:
        cutoff = datetime.utcnow() - timedelta(seconds=config.RESERVATION_TTL_SECONDS)
        result = await session.execute(
            update(Number)
            .where(Number.status == "reserved", Number.reserved_at < cutoff)
            .values(status="available", reserved_by=None, reserved_at=None)
        )
        await session.commit()
        return result.rowcount or 0


async def buy_number_balance(
    nid: int, user_id: int, rubles: float = 0.0, stars: int = 0
) -> Number | None:
    """Мгновенная покупка с внутреннего баланса (₽ или ⭐)."""
    async with get_session() as session:
        user = await session.get(User, user_id)
        number = await session.get(Number, nid)
        if user is None or number is None:
            return None
        if number.status != "available" or number.owner_id is not None:
            return None
        if rubles > 0:
            if user.rubles_balance < rubles:
                return None
            user.rubles_balance -= rubles
            currency = "₽"
        else:
            if user.stars_balance < stars:
                return None
            user.stars_balance -= stars
            currency = "⭐"
        number.status = "sold"
        number.owner_id = user_id
        number.sold_at = datetime.utcnow()
        await session.commit()
        await session.refresh(number)
    await add_transaction(
        user_id, "purchase", float(rubles if rubles > 0 else stars),
        f"{currency} Покупка номера {number.phone_number} ({number.country})",
    )
    await pay_referrer_commission(user_id, number.price_rubles)
    return number


def _confirm_buy_inner(db_number) -> None:  # не используется, оставлено для читаемости
    pass


async def give_number_free(
    user_id: int, country: str, country_flag: str,
    phone: str, operator: str | None, price_rubles: float = 0.0,
) -> Number | None:
    """Админ вручает номер пользователю (появляется в «Моих номерах»)."""
    phone = normalize_phone(phone)
    number = Number(
        country=country,
        country_flag=country_flag,
        phone_number=phone,
        operator=operator,
        price_rubles=float(price_rubles),
        price_stars=rubles_to_stars(price_rubles) if price_rubles else 0,
        status="sold",
        owner_id=user_id,
        sold_at=datetime.utcnow(),
    )
    async with get_session() as session:
        exists = await session.scalar(select(Number).where(Number.phone_number == phone))
        if exists:
            return None
        session.add(number)
        await session.commit()
        await session.refresh(number)
        await add_transaction(
            user_id, "purchase", 0.0,
            f"🎁 Выдан админом: {phone} ({country})",
        )
        return number


async def take_number_from_user(nid: int, user_id: int) -> bool:
    """Изымает номер (возвращает в базу доступных)."""
    async with get_session() as session:
        result = await session.execute(
            update(Number)
            .where(Number.id == nid, Number.owner_id == user_id)
            .values(status="available", owner_id=None, sold_at=None)
        )
        await session.commit()
        return result.rowcount > 0


async def user_numbers(user_id: int) -> list[Number]:
    async with get_session() as session:
        return list(
            await session.scalars(
                select(Number)
                .where(Number.owner_id == user_id)
                .order_by(Number.sold_at.desc(), Number.id.desc())
            )
        )


# ─────────────────────────────────────────────────────────────────────────────
# Заказы (покупки через @Clulk / пополнения рублями)
# ─────────────────────────────────────────────────────────────────────────────
async def create_buy_order(number: Number, user_id: int) -> Order:
    """Создаёт заказ на покупку; номер уже зарезервирован за юзером."""
    async with get_session() as session:
        order = Order(
            user_id=user_id,
            kind="buy",
            number_id=number.id,
            phone=number.phone_number,
            country=number.country,
            country_flag=number.country_flag,
            price_rubles=number.price_rubles,
            currency="rubles",
            status="pending",
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def create_deposit_order(
    user_id: int, rubles: float, details: str = "Пополнение рублями через @Clulk",
) -> Order:
    async with get_session() as session:
        order = Order(
            user_id=user_id,
            kind="deposit",
            price_rubles=round(float(rubles), 2),
            currency="rubles",
            status="pending",
            details=details,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order


async def get_order(order_id: int) -> Order | None:
    async with get_session() as session:
        return await session.get(Order, order_id)


async def pending_buy_order(user_id: int, number_id: int) -> Order | None:
    async with get_session() as session:
        return await session.scalar(
            select(Order).where(
                Order.user_id == user_id,
                Order.number_id == number_id,
                Order.kind == "buy",
                Order.status == "pending",
            )
        )


async def user_orders(user_id: int, limit: int = 50) -> list[Order]:
    async with get_session() as session:
        return list(
            await session.scalars(
                select(Order)
                .where(Order.user_id == user_id)
                .order_by(Order.id.desc())
                .limit(limit)
            )
        )


async def pending_orders(limit: int = 30) -> list[Order]:
    async with get_session() as session:
        return list(
            await session.scalars(
                select(Order)
                .where(Order.status == "pending")
                .order_by(Order.id.asc())
                .limit(limit)
            )
        )


async def order_count_pending() -> int:
    async with get_session() as session:
        return int(
            await session.scalar(
                select(func.count(Order.id)).where(Order.status == "pending")
            ) or 0
        )


async def confirm_order(order_id: int, admin_id: int) -> Order | None:
    """Подтверждает оплату: для buy — выдача номера, для deposit — ₽ на баланс."""
    async with get_session() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "pending":
            return None
        if order.kind == "deposit":
            user = await session.get(User, order.user_id)
            if user is None:
                return None
            user.rubles_balance = round(user.rubles_balance + order.price_rubles, 2)
            order.status = "paid"
            order.confirmed_by = admin_id
            order.paid_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
        else:
            number = None
            if order.number_id:
                number = await session.get(Number, order.number_id)
            if number is None:
                return None
            result = await session.execute(
                update(Number)
                .where(
                    Number.id == number.id,
                    Number.status == "reserved",
                    Number.reserved_by == order.user_id,
                )
                .values(
                    status="sold", owner_id=order.user_id,
                    sold_at=datetime.utcnow(),
                    reserved_by=None, reserved_at=None,
                )
            )
            if result.rowcount == 0:
                return None
            order.status = "paid"
            order.confirmed_by = admin_id
            order.paid_at = datetime.utcnow()
            await session.commit()
            await session.refresh(order)
    if order.kind == "buy":
        num_phone = order.phone or "номер"
        await add_transaction(
            order.user_id, "purchase", float(order.price_rubles),
            f"₽ Покупка номера {num_phone} ({order.country})",
        )
        await pay_referrer_commission(order.user_id, order.price_rubles)
    else:
        await add_transaction(
            order.user_id, "rubles_in", float(order.price_rubles),
            f"₽ Пополнение через @Clulk (заказ #{order.id})",
        )
    return order


async def pay_order_from_balance(
    order_id: int, currency: str
) -> tuple[str, Order | None]:
    """Оплата заказа с внутреннего баланса (currency: rub | stars).

    Возвращает (status, order): ok / insufficient / invalid.
    """
    async with get_session() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "pending":
            return "invalid", None
        user = await session.get(User, order.user_id)
        if user is None:
            return "invalid", None
        price = float(order.price_rubles)
        if currency == "stars":
            need = rubles_to_stars(price)
            if user.stars_balance < need:
                return "insufficient", None
            user.stars_balance -= need
            currency_name = "⭐"
        elif currency == "rub" or currency == "rubles":
            if user.rubles_balance < price:
                return "insufficient", None
            user.rubles_balance = round(user.rubles_balance - price, 2)
            currency_name = "₽"
        else:
            return "invalid", None

        if order.kind == "buy":
            number = None
            if order.number_id:
                number = await session.get(Number, order.number_id)
            if number is None:
                return "invalid", None
            result = await session.execute(
                update(Number)
                .where(
                    Number.id == number.id,
                    Number.status == "reserved",
                    Number.reserved_by == order.user_id,
                )
                .values(
                    status="sold", owner_id=order.user_id,
                    sold_at=datetime.utcnow(),
                    reserved_by=None, reserved_at=None,
                )
            )
            if result.rowcount == 0:
                # Бронь могла протухнуть, а номер — перекупить другой
                # пользователь: не списываем баланс, но сообщаем о проблеме.
                return "invalid", None
        else:  # deposit через баланс не проводят; только приём от @Clulk
            return "invalid", None
        order.status = "paid"
        order.paid_at = datetime.utcnow()
        order.confirmed_by = order.user_id  # оплачено с баланса самим юзером
        await session.commit()
        await session.refresh(order)
    await add_transaction(
        order.user_id, "purchase", float(order.price_rubles),
        f"{currency_name} Покупка номера {order.phone} ({order.country})",
    )
    await pay_referrer_commission(order.user_id, order.price_rubles)
    return "ok", order


async def pay_deposit_with_stars(
    order_id: int,
) -> tuple[str, Order | None, int]:
    """Оплата пополнения ₽-баланса звёздами с внутреннего баланса.

    Без инвойсов: списываем ⭐ по курсу, зачисляем ₽, заказ помечаем paid.
    Возвращает (status, order, need_stars): ok / insufficient / invalid.
    """
    async with get_session() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "pending" or order.kind != "deposit":
            return "invalid", None, 0
        user = await session.get(User, order.user_id)
        if user is None:
            return "invalid", None, 0
        need = rubles_to_stars(order.price_rubles)
        if user.stars_balance < need:
            return "insufficient", None, need
        user.stars_balance -= need
        user.rubles_balance = round(user.rubles_balance + order.price_rubles, 2)
        order.status = "paid"
        order.paid_at = datetime.utcnow()
        order.confirmed_by = order.user_id  # оплачено звёздами с баланса
        await session.commit()
        await session.refresh(order)
    await add_transaction(
        order.user_id, "rubles_in", float(order.price_rubles),
        f"⭐→₽ Пополнение звёздами (заказ #{order.id})",
    )
    await add_transaction(
        order.user_id, "stars_out", need,
        f"⭐→₽ Покупка {order.price_rubles:g} ₽",
    )
    return "ok", order, need


async def cancel_order(order_id: int, admin_id: int) -> Order | None:
    """Отменяет заказ, возвращая номер в сток."""
    async with get_session() as session:
        order = await session.get(Order, order_id)
        if order is None or order.status != "pending":
            return None
        if order.kind == "buy" and order.number_id:
            await session.execute(
                update(Number)
                .where(
                    Number.id == order.number_id,
                    Number.status == "reserved",
                    Number.reserved_by == order.user_id,
                )
                .values(status="available", reserved_by=None, reserved_at=None)
            )
        order.status = "cancelled"
        order.confirmed_by = admin_id
        await session.commit()
        await session.refresh(order)
        return order


# ─────────────────────────────────────────────────────────────────────────────
# Реферальная система
# ─────────────────────────────────────────────────────────────────────────────
async def pay_referrer_commission(buyer_id: int, price_rubles: float) -> float:
    """Начисляет рефереру REF_PERCENT% с покупки (в рублях)."""
    user = await get_user(buyer_id)
    if user is None or not user.referrer_id or user.referrer_id == buyer_id:
        return 0.0
    percent = float(await get_shop_setting("ref_percent", "10"))
    bonus = round(float(price_rubles) * percent / 100.0, 2)
    if bonus <= 0:
        return 0.0
    ok = await add_rubles(
        user.referrer_id, bonus, f"₽ Реферальный бонус (+{percent}% от покупки)"
    )
    return bonus if ok else 0.0


def referral_link(username: str | None, user_id: int) -> str:
    bot = username or config.BOT_USERNAME or "Feris_shop_bot"
    bot = bot.lstrip("@")
    if ":" in bot:  # формат bot_username нельзя с токеном
        bot = bot.split(":", 1)[0]
    return f"https://t.me/{bot}?start=ref{user_id}"


# ─────────────────────────────────────────────────────────────────────────────
# SMS-коды
# ─────────────────────────────────────────────────────────────────────────────
async def add_sms(
    user_id: int, phone: str, app: str, code: str,
    number_id: int | None = None, added_by: int | None = None,
) -> Sms | None:
    async with get_session() as session:
        sms = Sms(user_id=user_id, phone=phone, app=app or "Telegram",
                  code=code, number_id=number_id, added_by=added_by)
        session.add(sms)
        await session.commit()
        await session.refresh(sms)
        return sms


async def user_sms(user_id: int) -> list[Sms]:
    async with get_session() as session:
        return list(
            await session.scalars(
                select(Sms).where(Sms.user_id == user_id).order_by(Sms.id.desc())
            )
        )


async def sms_history(limit: int = 50) -> list[Sms]:
    async with get_session() as session:
        return list(
            await session.scalars(
                select(Sms).order_by(Sms.id.desc()).limit(limit)
            )
        )


async def delete_sms(sms_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(delete(Sms).where(Sms.id == sms_id))
        await session.commit()
        return result.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# Баг-репорты
# ─────────────────────────────────────────────────────────────────────────────
async def add_bug(user_id: int, text: str) -> BugReport:
    async with get_session() as session:
        bug = BugReport(user_id=user_id, text=text, status="open")
        session.add(bug)
        await session.commit()
        await session.refresh(bug)
        return bug


async def bug_reports(status: str | None = None, limit: int = 50) -> list[BugReport]:
    async with get_session() as session:
        stmt = select(BugReport).order_by(BugReport.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(BugReport.status == status)
        return list(await session.scalars(stmt))


async def set_bug_status(bug_id: int, status: str) -> bool:
    async with get_session() as session:
        bug = await session.get(BugReport, bug_id)
        if bug is None:
            return False
        bug.status = status
        await session.commit()
        return True


async def delete_bug(bug_id: int) -> bool:
    async with get_session() as session:
        result = await session.execute(delete(BugReport).where(BugReport.id == bug_id))
        await session.commit()
        return result.rowcount > 0


# ─────────────────────────────────────────────────────────────────────────────
# Владельцы (доп. из БД) и настройки
# ─────────────────────────────────────────────────────────────────────────────
async def get_owners_list() -> list[str]:
    """@username владельцев: из .env (config) + из settings 'owners'."""
    extra = await get_setting("owners")
    merged = list(config.OWNER_USERNAMES)
    if extra:
        try:
            for name in json.loads(extra):
                name = str(name).strip().lstrip("@").lower()
                if name and name not in merged:
                    merged.append(name)
        except (ValueError, TypeError):
            pass
    return sorted(set(merged))


async def add_owner(username: str) -> bool:
    clean = username.strip().lstrip("@").lower()
    if not clean:
        return False
    owners = await get_owners_list()
    basic = set(config.OWNER_USERNAMES)
    if clean in owners:
        return False
    owners.append(clean)
    extra = sorted(o for o in owners if o not in basic)
    await set_setting("owners", json.dumps(extra, ensure_ascii=False))
    return True


async def remove_owner(username: str) -> bool:
    clean = username.strip().lstrip("@").lower()
    if clean in config.OWNER_USERNAMES:
        return False  # из .env не удаляем, только из БД-списка
    extra = json.loads(await get_setting("owners") or "[]") or []
    filtered = [o for o in extra if str(o).lower().lstrip("@") != clean]
    if len(filtered) == len(extra):
        return False
    await set_setting("owners", json.dumps(filtered, ensure_ascii=False))
    return True


async def is_owner(user_id: int = 0, username: str | None = "") -> bool:
    if user_id and user_id in config.ADMIN_IDS:
        return True
    if username:
        clean = username.lower().strip().lstrip("@")
        if clean in set(await get_owners_list()):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# FAQ (хранится в настройке "faq" как JSON-список [(вопрос, ответ)])
# ─────────────────────────────────────────────────────────────────────────────
async def get_faq() -> list[tuple[str, str]]:
    from utils import texts as t  # ленивый импорт против циклов

    raw = await get_setting("faq")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return [(str(q), str(a)) for q, a in data]
        except (ValueError, TypeError):
            pass
    return list(t.DEFAULT_FAQ)


async def set_faq(items: list[tuple[str, str]]) -> None:
    await set_setting("faq", json.dumps(items, ensure_ascii=False))


async def add_faq(question: str, answer: str) -> list[tuple[str, str]]:
    items = await get_faq()
    items.append((question, answer))
    await set_faq(items)
    return items


async def delete_faq(idx: int) -> list[tuple[str, str]]:
    """Удаляет по человекочитаемому индексу (1-based)."""
    items = await get_faq()
    if idx < 1 or idx > len(items):
        return items
    items.pop(idx - 1)
    await set_faq(items)
    return items


async def reset_faq() -> list[tuple[str, str]]:
    from utils import texts as t  # noqa: PLC0415

    await set_faq(t.DEFAULT_FAQ)
    return list(t.DEFAULT_FAQ)


# ─────────────────────────────────────────────────────────────────────────────
# Settings (ключ-значение, редактируются из админки)
# ─────────────────────────────────────────────────────────────────────────────
EDITABLE_SETTINGS: dict[str, str] = {
    "welcome_text": "Приветствие (/start)",
    "faq": "FAQ (JSON)",
    "ref_percent": "Реферальный % с покупки",
    "stars_per_ruble": "Курс: 1 ₽ = N ⭐",
}


async def get_setting(key: str) -> str | None:
    async with get_session() as session:
        s = await session.get(Setting, key)
        return s.value if s else None


async def set_setting(key: str, value: str) -> None:
    async with get_session() as session:
        s = await session.get(Setting, key)
        if s is None:
            session.add(Setting(key=key, value=value))
        else:
            s.value = value
        await session.commit()


def get_setting_sync(key: str) -> str | None:
    """Синхронное чтение настройки (для лёгких вспомогательных мест)."""
    import sqlite3
    import os

    url = config.DB_URL or ""
    path = url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
    if not os.path.isabs(path):
        path = os.path.join(config.PROJECT_DIR, path)
    try:
        conn = sqlite3.connect(path)
        row = conn.execute("select value from settings where key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


async def get_shop_setting(key: str, default: str) -> str:
    """Настройка из БД или default (если в БД пусто)."""
    val = await get_setting(key)
    if val is None or val == "":
        return default
    return val


# ─────────────────────────────────────────────────────────────────────────────
# Статистика
# ─────────────────────────────────────────────────────────────────────────────
async def get_stats() -> dict:
    async with get_session() as session:
        users = int(await session.scalar(select(func.count(User.id))) or 0)
        sold = int(
            await session.scalar(
                select(func.count(Number.id)).where(Number.status == "sold")
            ) or 0
        )
        available = int(
            await session.scalar(
                select(func.count(Number.id)).where(Number.status == "available")
            ) or 0
        )
        orders = int(await session.scalar(select(func.count(Order.id))) or 0)
        pending = int(
            await session.scalar(
                select(func.count(Order.id)).where(Order.status == "pending")
            ) or 0
        )
        stars_revenue = float(
            await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.type.in_(["purchase", "donate", "bonus"]),
                    Transaction.description.like("⭐ %"),
                )
            ) or 0
        )
        rubles_revenue = float(
            await session.scalar(
                select(func.coalesce(func.sum(Transaction.amount), 0)).where(
                    Transaction.description.like("₽ %"),
                )
            ) or 0
        )
    return {
        "users": users,
        "sold": sold,
        "available": available,
        "orders": orders,
        "pending": pending,
        "stars_revenue": int(stars_revenue),
        "rubles_revenue": rubles_revenue,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Админ-логи
# ─────────────────────────────────────────────────────────────────────────────
async def log_admin(
    admin_id: int, action: str,
    target_user_id: int | None = None, details: str | None = None,
) -> None:
    async with get_session() as session:
        session.add(
            AdminLog(
                admin_id=admin_id,
                action=action,
                target_user_id=target_user_id,
                details=details,
            )
        )
        await session.commit()