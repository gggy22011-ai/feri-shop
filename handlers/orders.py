"""
Мои заказы / Чеки: список заказов пользователя и карточка чека.
"""
from __future__ import annotations

import config

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import queries
from keyboards.misc_kb import orders_kb, order_view_kb
from keyboards.user_kb import back_to_menu_kb
from utils import texts
from utils.helpers import dt_format

router = Router(name="orders")

PAYMENT = config.PAYMENT_USERNAME.lstrip("@")


def _status_label(status: str) -> str:
    return {
        "pending": texts.ORDER_STATUS_PENDING,
        "paid": texts.ORDER_STATUS_PAID,
        "cancelled": texts.ORDER_STATUS_CANCELLED,
    }.get(status, status)


@router.callback_query(F.data == "menu:orders")
async def cb_orders(callback: CallbackQuery) -> None:
    orders = await queries.user_orders(callback.from_user.id)
    if not orders:
        await callback.message.edit_text(
            texts.ORDERS_EMPTY,
            reply_markup=back_to_menu_kb(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        texts.ORDERS_TITLE, reply_markup=orders_kb(orders)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order:view:"))
async def cb_order_view(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заказ не найден", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    if order.kind == "buy":
        item = f"{order.country_flag or ''} {order.phone or '—'}"
    elif order.details and "крипто" in order.details:
        item = f"₿ Пополнение криптой ({order.price_rubles:g} ₽)"
    else:
        item = f"💳 Пополнение баланса ({order.price_rubles:g} ₽)"
    await callback.message.edit_text(
        texts.RECEIPT_TEXT.format(
            order_id=f"{order.id:06d}",
            date=dt_format(order.paid_at or order.created_at),
            item=item,
            amount=order.price_rubles,
            status=_status_label(order.status),
            payment=PAYMENT,
        ),
        reply_markup=order_view_kb(order.id),
    )
    await callback.answer()