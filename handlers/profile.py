"""
Мой профиль: баланс, номера, дата регистрации, реферальная ссылка.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

import config
from database import queries
from keyboards.user_kb import back_to_menu_kb
from utils import texts
from utils.helpers import date_format

router = Router(name="profile")


@router.callback_query(F.data == "menu:profile")
async def cb_profile(callback: CallbackQuery) -> None:
    user = await queries.get_user(callback.from_user.id)
    if user is None:
        user, _ = await queries.get_or_create_user(
            callback.from_user.id,
            callback.from_user.username,
            callback.from_user.first_name,
        )
    numbers = await queries.user_numbers(callback.from_user.id)
    ref_percent = await queries.get_shop_setting("ref_percent", "10")
    text = texts.PROFILE_TEXT.format(
        first_name=user.first_name or "—",
        username=user.username and f"@{user.username}" or "—",
        user_id=user.id,
        rubles=user.rubles_balance,
        stars=user.stars_balance,
        purchases=len(numbers),
        reg=date_format(user.registered_at),
        ref=queries.referral_link(config.BOT_USERNAME, user.id),
        ref_percent=ref_percent,
        sign=texts.SIGNATURE,
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb())
    await callback.answer()