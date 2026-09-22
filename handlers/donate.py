"""
Задонатить звёзды: инвойс ⭐ на выбранную сумму.
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.types import LabeledPrice

from utils import texts
from utils.logger import get_logger
from utils.states import DonateAmount

logger = get_logger("donate")
router = Router(name="donate")

DONATE_AMOUNTS = [10, 50, 100]


def _donate_kb() -> InlineKeyboardMarkup:
    rows = []
    for a in DONATE_AMOUNTS:
        rows.append([
            InlineKeyboardButton(text=f"{a} ⭐", callback_data=f"donate:amount:{a}")
        ])
    rows.append([
        InlineKeyboardButton(text="💬 Своя сумма", callback_data="donate:custom"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:donate")
async def cb_donate_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🎁 Выберите сумму доната в звёздах:", reply_markup=_donate_kb()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("donate:amount:"))
async def cb_donate_amount(callback: CallbackQuery, bot: Bot) -> None:
    stars = int(callback.data.split(":")[2])
    await _send_donate_invoice(bot, callback.from_user.id, stars)
    await callback.answer("Инвойс ⭐ отправлен")


@router.callback_query(F.data == "donate:custom")
async def cb_donate_custom(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "🎁 Введите сумму доната в звёздах (целое число, минимум 1):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:donate")]
        ]),
    )
    await state.set_state(DonateAmount.amount)
    await callback.answer()


@router.message(DonateAmount.amount)
async def msg_donate_custom(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        stars = int(message.text.strip())
        if stars < 1:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer(texts.DEPOSIT_WRONG_AMOUNT)
        return
    await state.clear()
    await _send_donate_invoice(bot, message.from_user.id, stars)


async def _send_donate_invoice(bot: Bot, chat_id: int, stars: int) -> None:
    stars = max(1, int(stars))
    await bot.send_invoice(
        chat_id=chat_id,
        title=texts.DONATE_TITLE,
        description=f"{stars} ⭐",
        payload=f"donate:{chat_id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="⭐", amount=stars)],
    )