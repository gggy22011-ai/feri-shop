"""
Inline-клавиатуры: заказы/чеки.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import Order


def orders_kb(orders: list[Order]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for order in orders[:30]:
        emoji = {
            "pending": "⏳", "paid": "✅", "cancelled": "❌",
        }.get(order.status, "•")
        kind = "📦" if order.kind == "buy" else "💳"
        item = order.phone or f"{order.price_rubles:g} ₽ (пополнение)"
        rows.append([InlineKeyboardButton(
            text=f"{emoji} {kind} #{order.id:06d} · {item}",
            callback_data=f"order:view:{order.id}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_view_kb(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📨 Получить код", callback_data="menu:codes"
            )],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:orders")],
        ]
    )