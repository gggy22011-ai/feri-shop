"""
Пополнение баланса (как в Meri Shop): сразу ввод суммы в рублях → далее
выбор способа оплаты — Крипта (@Clulk, заявка + подтверждение админом)
ИЛИ Звёздами ⭐ с баланса (мгновенно, по курсу 1 ₽ = 1.45 ⭐).

Пополнение баланса отдельными инвойсами звёзд отключено.
"""
from __future__ import annotations

import os

import config

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import queries
from keyboards.shop_kb import deposit_crypto_kb, deposit_method_kb
from utils import texts
from utils.helpers import parse_money_input
from utils.states import DepositAmount

router = Router(name="deposit")

PAYMENT = config.PAYMENT_USERNAME.lstrip("@")

DEPOSIT_DETAILS = "Пополнение через @Clulk"


def _amount_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
        ]
    )


def _stars_ok_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Пополнить ещё", callback_data="deposit:menu")],
            [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
        ]
    )


@router.callback_query(F.data == "menu:deposit")
async def cb_deposit_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(DepositAmount.amount)
    caption = texts.DEPOSIT_AMOUNT_ASK.format(payment=PAYMENT)
    photo_path = os.path.join(config.PROJECT_DIR, config.DEPOSIT_PHOTO_FILE)
    if os.path.isfile(photo_path):
        await callback.message.answer_photo(
            FSInputFile(photo_path), caption=caption, reply_markup=_amount_kb()
        )
    else:
        await callback.message.edit_text(caption, reply_markup=_amount_kb())
    await callback.answer()


@router.message(DepositAmount.amount)
async def msg_deposit_amount(message: Message, state: FSMContext) -> None:
    try:
        amount = parse_money_input(message.text or "")
    except ValueError:
        await message.answer(texts.DEPOSIT_WRONG_AMOUNT)
        return
    await state.clear()
    order = await queries.create_deposit_order(
        message.from_user.id, amount, details=DEPOSIT_DETAILS
    )
    need_stars = queries.rubles_to_stars(order.price_rubles)
    await message.answer(
        texts.DEPOSIT_METHODS.format(
            amount=order.price_rubles, need=need_stars, payment=PAYMENT
        ),
        reply_markup=deposit_method_kb(order.id, need_stars),
    )


@router.callback_query(F.data.startswith("deposit:summary:"))
async def cb_deposit_summary(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заказ не найден", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    need = queries.rubles_to_stars(order.price_rubles)
    await callback.message.edit_text(
        texts.DEPOSIT_METHODS.format(
            amount=order.price_rubles, need=need, payment=PAYMENT
        ),
        reply_markup=deposit_method_kb(order.id, need),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deposit:method:crypto:"))
async def cb_deposit_crypto(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[3])
    except (ValueError, IndexError):
        await callback.answer("Заказ не найден", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    await callback.message.edit_text(
        texts.DEPOSIT_CRYPTO_TEXT.format(amount=order.price_rubles, payment=PAYMENT),
        reply_markup=deposit_crypto_kb(order.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("deposit:stars_pay:"))
async def cb_deposit_stars_pay(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заказ не найден", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    status, paid_order, need = await queries.pay_deposit_with_stars(oid)
    if status == "insufficient":
        user = await queries.get_user(callback.from_user.id)
        await callback.message.edit_text(
            texts.DEPOSIT_STARS_NO.format(
                need=need,
                balance=user.stars_balance if user else 0,
                payment=PAYMENT,
            ),
            reply_markup=deposit_method_kb(oid, need),
        )
        await callback.answer()
        return
    if status != "ok" or paid_order is None:
        await callback.answer("❌ Заказ уже обработан.", show_alert=True)
        return
    user = await queries.get_user(paid_order.user_id)
    await callback.message.edit_text(
        texts.DEPOSIT_STARS_OK.format(
            amount=paid_order.price_rubles,
            stars=need,
            order_id=paid_order.id,
            balance=user.rubles_balance if user else 0,
        ),
        reply_markup=_stars_ok_kb(),
    )
    await callback.answer("✅ Баланс пополнен")


@router.callback_query(F.data.startswith("deposit:copy:"))
async def cb_deposit_copy(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    text = texts.DEPOSIT_CLULK_APPLICATION.format(amount=order.price_rubles)
    await callback.message.answer(f"<pre>{text}</pre>")
    await callback.answer("📋 Заявка скопирована")