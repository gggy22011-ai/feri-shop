"""
Мои номера: список купленных, кнопка «Скопировать номер».
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import queries
from keyboards.shop_kb import my_numbers_kb
from utils import texts
from utils.helpers import date_format

router = Router(name="my_numbers")


def _numbers_text(numbers) -> str:
    if not numbers:
        return texts.MY_NUMBERS_EMPTY
    lines = [texts.MY_NUMBERS_TITLE.format(count=len(numbers))]
    for idx, num in enumerate(numbers, 1):
        lines.append(
            texts.MY_NUMBERS_ITEM.format(
                idx=idx,
                flag=num.country_flag or "",
                country=num.country,
                phone=num.phone_number,
                operator=num.operator or "—",
                price=num.price_rubles or 0,
                date=date_format(num.sold_at),
            )
        )
    return "\n".join(lines)


@router.callback_query(F.data == "menu:nums")
async def cb_my_numbers(callback: CallbackQuery) -> None:
    numbers = await queries.user_numbers(callback.from_user.id)
    await callback.message.edit_text(
        _numbers_text(numbers), reply_markup=my_numbers_kb(numbers)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("copy:"))
async def cb_copy_number(callback: CallbackQuery) -> None:
    nid = int(callback.data.split(":")[1])
    num = await queries.get_number(nid)
    if num is None or num.owner_id != callback.from_user.id:
        await callback.answer("Номер не найден", show_alert=True)
        return
    await callback.message.answer(f"<code>{num.phone_number}</code>")
    await callback.answer("📋 Номер отправлен")