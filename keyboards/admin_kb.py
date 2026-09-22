"""
Inline-клавиатуры админ-панели Feris Shop.
"""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import Number


def admin_panel_kb(pending: int = 0) -> InlineKeyboardMarkup:
    """Главная панель администратора (по ТЗ, без промокодов)."""
    confirm_label = "✅ Подтверждение оплат"
    if pending:
        confirm_label += f" ({pending})"
    rows = [
        [InlineKeyboardButton(text=confirm_label, callback_data="admin:orders")],
        [InlineKeyboardButton(text="📇 Инфо о пользователе", callback_data="admin:user_info")],
        [
            InlineKeyboardButton(text="➕ Выдать номер", callback_data="admin:issue"),
            InlineKeyboardButton(text="🗑 Забрать номер", callback_data="admin:take_number"),
        ],
        [
            InlineKeyboardButton(text="💰 Выдать валюту", callback_data="admin:give_money"),
            InlineKeyboardButton(text="💸 Забрать валюту", callback_data="admin:take_money"),
        ],
        [InlineKeyboardButton(text="📱 Склад номеров", callback_data="admin:sklad")],
        [InlineKeyboardButton(text="🌍 Управление странами", callback_data="admin:countries")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="🎫 Управление FAQ", callback_data="admin:faq")],
        [InlineKeyboardButton(text="👑 Управление владельцами", callback_data="admin:owners")],
        [InlineKeyboardButton(text="🔧 Лог багов", callback_data="admin:bugs")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="admin:settings")],
        [InlineKeyboardButton(text="📨 Управление SMS", callback_data="admin:sms")],
        [InlineKeyboardButton(text="🚫 Блокировки пользователя", callback_data="admin:block")],
        [InlineKeyboardButton(text="🔒 Выйти из панели", callback_data="admin:exit")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sklad_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить номера", callback_data="admin:add_numbers"),
             InlineKeyboardButton(text="🗂 Список", callback_data="admin:list_numbers")],
            [InlineKeyboardButton(text="🗑 Удалить номер", callback_data="admin:delete_number")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def countries_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить страну", callback_data="admin:c_add"),
             InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:c_del")],
            [InlineKeyboardButton(text="📋 Список стран", callback_data="admin:c_list")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def faq_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="admin:faq_add"),
             InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:faq_del")],
            [InlineKeyboardButton(text="🔍 Посмотреть FAQ", callback_data="admin:faq_view"),
             InlineKeyboardButton(text="🔄 Сброс", callback_data="admin:faq_reset")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def owners_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="admin:o_add"),
             InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:o_del")],
            [InlineKeyboardButton(text="📋 Список владельцев", callback_data="admin:o_list")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def bugs_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="admin:b_add"),
             InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:b_del")],
            [InlineKeyboardButton(text="📋 Список багов", callback_data="admin:b_list")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def settings_kb(keys: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for key in keys:
        rows.append([InlineKeyboardButton(
            text=f"⚙️ {key}", callback_data=f"admin:set:{key}"
        )])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sms_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить код", callback_data="admin:sms_add")],
            [InlineKeyboardButton(text="📋 История SMS", callback_data="admin:sms_list"),
             InlineKeyboardButton(text="🗑 Удалить", callback_data="admin:sms_del")],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")]
        ]
    )


def number_choice_kb(numbers: list[Number], action: str) -> InlineKeyboardMarkup:
    """Выбор номера из списка (для изъятия / удаления)."""
    rows = []
    for num in numbers[:20]:
        rows.append([InlineKeyboardButton(
            text=f"{num.phone_number} — {num.country}",
            callback_data=f"{action}:{num.id}",
        )])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def orders_kb(orders) -> InlineKeyboardMarkup:
    """Список ожидающих оплаты заказов с кнопками подтвердить/отменить."""
    rows: list[list[InlineKeyboardButton]] = []
    for o in orders[:15]:
        crypto = bool(o.kind == "deposit" and o.details and "крипто" in o.details)
        kind = "📦 buy" if o.kind == "buy" else ("₿ crypto" if crypto else "💳 deposit")
        item = (o.phone or f"{'₿ ' if crypto else ''}{o.price_rubles:g} ₽")
        rows.append([
            InlineKeyboardButton(text=f"✅ #{o.id:06d} {item}", callback_data=f"admin:order_x:{o.id}"),
            InlineKeyboardButton(text=f"❌ #{o.id:06d}", callback_data=f"admin:order_z:{o.id}"),
        ])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def sms_action_kb(sms_rows, action: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for sms in sms_rows[:15]:
        rows.append([InlineKeyboardButton(
            text=f"#{sms.id} · {sms.phone} · {sms.app} · {sms.code}",
            callback_data=f"{action}:{sms.id}",
        )])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def country_delete_kb(countries) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for c in countries[:20]:
        rows.append([InlineKeyboardButton(
            text=f"{c.country_flag or '🌐'} {c.name} · {c.price_rubles:g} ₽",
            callback_data=f"admin:c_del1:{c.name}",
        )])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def faq_delete_kb(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for idx, q in items[:20]:
        rows.append([InlineKeyboardButton(text=f"🗑 {idx}. {q[:40]}", callback_data=f"admin:faq_del1:{idx}")])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def bug_delete_kb(bugs) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for b in bugs[:15]:
        rows.append([InlineKeyboardButton(
            text=f"#{b.id} · {b.text[:40]}",
            callback_data=f"admin:b_del1:{b.id}",
        )])
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)