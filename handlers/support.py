"""
Поддержка + сообщения о багах.
"""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from database import queries
from keyboards.user_kb import back_to_menu_kb, support_kb
from utils import notify, texts
from utils.states import BugReportText

router = Router(name="support")


def _bug_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:support")]
    ])


@router.callback_query(F.data == "menu:support")
async def cb_support(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        texts.SUPPORT_TEXT, reply_markup=support_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "support:bug")
async def cb_bug_report(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BugReportText.text)
    await callback.message.edit_text(
        texts.BUG_GREETING, reply_markup=_bug_back_kb()
    )
    await callback.answer()


@router.message(BugReportText.text)
async def msg_bug_report(message: Message, state: FSMContext, bot: Bot) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer(texts.BUG_GREETING)
        return
    await state.clear()
    await queries.add_bug(
        user_id=message.from_user.id,
        text=text,
    )
    try:
        await notify.notify_owners(
            bot,
            texts.BUG_NOTIFY.format(
                bug_id=0,
                username=message.from_user.username or "—",
                text=text,
            ),
        )
    except Exception:  # noqa: BLE001
        pass
    await message.answer(
        texts.BUG_SAVED, reply_markup=back_to_menu_kb()
    )