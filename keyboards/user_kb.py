"""
Inline-клавиатуры пользователя: главное меню и общие кнопки.
"""
from __future__ import annotations

import config

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_kb() -> InlineKeyboardMarkup:
    """🏠 Главное меню (по ТЗ — 10 разделов)."""
    rows = [
        [
            InlineKeyboardButton(text="🛒 Купить номер", callback_data="menu:buy"),
            InlineKeyboardButton(text="📦 Мои номера", callback_data="menu:nums"),
        ],
        [
            InlineKeyboardButton(text="📨 Получить код", callback_data="menu:codes"),
            InlineKeyboardButton(text="🧾 Мои заказы / Чеки", callback_data="menu:orders"),
        ],
        [
            InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="menu:deposit"),
            InlineKeyboardButton(text="👤 Мой профиль", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="menu:support"),
            InlineKeyboardButton(text="ℹ️ FAQ", callback_data="menu:faq"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )


def support_kb() -> InlineKeyboardMarkup:
    payment = config.PAYMENT_USERNAME.lstrip("@")
    support = config.SUPPORT_USERNAME.lstrip("@")
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💬 Написать поддержке (@{support})",
                url=f"https://t.me/{support}",
            )],
            [InlineKeyboardButton(
                text=f"💳 По оплате (@{payment})",
                url=f"https://t.me/{payment}",
            )],
            [InlineKeyboardButton(
                text="📢 FAQ-канал",
                url=config.CHANNEL_URL,
            )],
            [InlineKeyboardButton(text="🐞 Сообщить о баге", callback_data="support:bug")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
        ]
    )


def faq_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 FAQ-канал",
                url=config.CHANNEL_URL,
            )],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
        ]
    )