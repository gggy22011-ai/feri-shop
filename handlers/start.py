"""
Старт, главное меню, справка, отмена действий, реферальные ссылки.
"""
from __future__ import annotations

import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from database import queries
from keyboards.user_kb import main_menu_kb
from utils import notify, texts

router = Router(name="start")


def _parse_ref(text: str) -> int | None:
    """start=ref123456 → 123456."""
    m = re.search(r"(?:^|\s)start=ref(\d+)\b", (text or ""))
    return int(m.group(1)) if m else None


@router.message(Command("start"))
async def cmd_start(
    message: Message, bot: Bot, state: FSMContext, db_is_new: bool = False
) -> None:
    await state.clear()
    user = message.from_user
    ref_id = _parse_ref(message.text)
    if ref_id and ref_id != user.id:
        await queries.get_or_create_user(
            tg_id=user.id,
            username=user.username,
            first_name=user.first_name,
            referrer_id=ref_id,
        )
    if db_is_new and user:
        await notify.notify_owners(
            bot,
            texts.WELCOME_NEW_USER.format(
                username=user.username or "—", user_id=user.id
            ),
        )
    welcome = (await queries.get_setting("welcome_text")) or texts.DEFAULT_GREETING
    await message.answer(welcome)
    await message.answer(texts.MAIN_MENU_HINT, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(texts.HELP_TEXT, reply_markup=main_menu_kb())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELED, reply_markup=main_menu_kb())


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        texts.MAIN_MENU_HINT, reply_markup=main_menu_kb()
    )
    await callback.answer()