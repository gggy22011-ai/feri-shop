"""
Inline-клавиатуры магазина: страны, номер, оплата через @Clulk.
"""
from __future__ import annotations

import config

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import Number

PAYMENT = config.PAYMENT_USERNAME.lstrip("@")


def countries_kb(countries: list[tuple[str, str, int, float]]) -> InlineKeyboardMarkup:
    """Список стран (страна, флаг, кол-во, цена ₽)."""
    rows = []
    for country, flag, count, price in countries:
        label = f"{flag} {country} — {price:g} ₽ ({count})"
        rows.append([InlineKeyboardButton(
            text=label, callback_data=f"shop:c:{flag}|{country}"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def country_card_kb(flag: str, country: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Показать номера", callback_data=f"shop:l:{flag}|{country}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy")],
        ]
    )


def numbers_kb(
    numbers: list[Number],
    flag: str,
    country: str,
) -> InlineKeyboardMarkup:
    """Список доступных номеров страны — кнопка открывает карточку номера."""
    rows: list[list[InlineKeyboardButton]] = []
    for num in numbers[:40]:
        rows.append([InlineKeyboardButton(
            text=f"{flag} {num.phone_number} · {(num.price_rubles or 0):g} ₽",
            callback_data=f"shop:n:{num.id}",
        )])
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data=f"shop:c:{flag}|{country}")
    ])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def number_card_kb(num_id: int, flag: str, country: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить номер", callback_data=f"shop:buy:{num_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"shop:l:{flag}|{country}")],
        ]
    )


def buy_screen_kb(
    order_id: int,
    num_id: int,
    can_rubles: bool = False,
    can_stars: bool = False,
) -> InlineKeyboardMarkup:
    pay = PAYMENT
    rows = [
        [
            InlineKeyboardButton(
                text=f"⭐ Оплатить реальными звёздами · @{config.STAR_OWNER}",
                callback_data=f"shop:stars:{order_id}:{num_id}",
            )
        ],
        [InlineKeyboardButton(
            text=f"💬 Написать @{pay}",
            url=f"https://t.me/{pay}",
        )],
        [InlineKeyboardButton(
            text="📋 Скопировать заявку",
            callback_data=f"shop:copy:{order_id}",
        )],
    ]
    if can_rubles:
        rows.append([InlineKeyboardButton(
            text="💳 Оплатить с баланса ₽",
            callback_data=f"shop:pay:{order_id}:rub",
        )])
    if can_stars:
        rows.append([InlineKeyboardButton(
            text="⭐ Оплатить с баланса (звёзды)",
            callback_data=f"shop:pay:{order_id}:stars",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад", callback_data=f"shop:n:{num_id}"
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def buy_stars_kb(order_id: int, num_id: int) -> InlineKeyboardMarkup:
    """Экран оплаты реальными звёздами: написать @владелец / копировать заявку."""
    stars_owner = config.STAR_OWNER
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💬 Написать @{stars_owner}",
                url=f"https://t.me/{stars_owner}",
            )],
            [InlineKeyboardButton(
                text="📋 Скопировать заявку (⭐)",
                callback_data=f"shop:copy_stars:{order_id}",
            )],
            [
                InlineKeyboardButton(
                    text="⬅️ К выбору оплаты",
                    callback_data=f"shop:screen:{order_id}:{num_id}",
                ),
                InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"),
            ],
        ]
    )


def deposit_method_kb(order_id: int, need_stars: int) -> InlineKeyboardMarkup:
    """Выбор способа оплаты пополнения: крипта (@Clulk) или звёздами."""
    pay = PAYMENT
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🪙 Крипта — @{pay}",
                    callback_data=f"deposit:method:crypto:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"⭐ Оплатить звёздами · {need_stars} ⭐",
                    callback_data=f"deposit:stars_pay:{order_id}",
                )
            ],
            [
                InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="deposit:menu"),
                InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"),
            ],
        ]
    )


def deposit_crypto_kb(order_id: int) -> InlineKeyboardMarkup:
    """Экран оплаты криптой: написать @Clulk / скопировать заявку."""
    pay = PAYMENT
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"💬 Написать @{pay}", url=f"https://t.me/{pay}")],
            [InlineKeyboardButton(
                text="📋 Скопировать заявку",
                callback_data=f"deposit:copy:{order_id}",
            )],
            [InlineKeyboardButton(
                text="⬅️ Выбрать способ",
                callback_data=f"deposit:summary:{order_id}",
            )],
            [
                InlineKeyboardButton(text="✏️ Изменить сумму", callback_data="deposit:menu"),
                InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu"),
            ],
        ]
    )


def copy_text_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )


def my_numbers_kb(numbers: list[Number]) -> InlineKeyboardMarkup:
    """Список купленных номеров с кнопками: копировать / чек / код."""
    rows: list[list[InlineKeyboardButton]] = []
    for num in numbers:
        rows.append([InlineKeyboardButton(
            text=f"📋 {num.phone_number}",
            callback_data=f"copy:{num.id}",
        )])
    rows.append([
        InlineKeyboardButton(text="📄 Чек", callback_data="menu:orders"),
        InlineKeyboardButton(text="📨 Код", callback_data="menu:codes"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)