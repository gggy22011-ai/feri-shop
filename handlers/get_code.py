"""
Получить код: SMS-коды для купленных номеров (заносит админ/поддержка).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from database import queries
from utils import texts
from utils.helpers import dt_format

router = Router(name="get_code")


def _codes_kb(owned_phones: list[str]) -> InlineKeyboardMarkup:
    rows = []
    for phone in owned_phones:
        rows.append([InlineKeyboardButton(
            text=f"📋 Скопировать коды · {phone}",
            callback_data=f"codes:copy:{phone}",
        )])
    rows.append([InlineKeyboardButton(text="🔄 Обновить", callback_data="menu:codes")])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(F.data == "menu:codes")
async def cb_codes(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    numbers = await queries.user_numbers(user_id)
    sms_rows = await queries.user_sms(user_id)

    owned_phones = [n.phone_number for n in numbers]
    if not sms_rows and not owned_phones:
        await callback.message.edit_text(
            texts.GET_CODE_EMPTY, reply_markup=_codes_kb([])
        )
        await callback.answer()
        return

    lines = [texts.GET_CODE_TITLE]
    by_phone: dict[str, list] = {}
    for s in sms_rows:
        by_phone.setdefault(s.phone, []).append(s)

    for phone in owned_phones:
        codes = by_phone.get(phone, [])
        num = next((n for n in numbers if n.phone_number == phone), None)
        flag = (num.country_flag or "") if num else ""
        lines.append(f"{flag} <b>{phone}</b>")
        if not codes:
            if num is not None and num.activation_status == "waiting":
                # Автовыдача: номер уже куплен у сервиса, SMS ещё в пути.
                lines.append(
                    "   ⏳ Ждём SMS от Telegram — код придёт автоматически "
                    "и появится здесь."
                )
            else:
                lines.append("   ⏳ Кодов пока нет — как придёт, появится здесь.")
        for s in codes:
            lines.append(f"   {s.app}: <code>{s.code}</code> · {dt_format(s.created_at)}")
        lines.append("")

    extra = [s for s in sms_rows if s.phone not in owned_phones]
    for s in extra[:10]:
        lines.append(texts.GET_CODE_ITEM.format(
            phone=s.phone, app=s.app, code=s.code, date=dt_format(s.created_at)
        ))

    await callback.message.edit_text(
        "\n".join(lines).rstrip(), reply_markup=_codes_kb(owned_phones)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("codes:copy:"))
async def cb_codes_copy(callback: CallbackQuery) -> None:
    phone = callback.data.partition("codes:copy:")[2]
    sms_rows = [s for s in await queries.user_sms(callback.from_user.id) if s.phone == phone]
    if not sms_rows:
        await callback.answer("Кодов пока нет", show_alert=True)
        return
    text = "\n".join(f"{s.app}: {s.code}" for s in sms_rows)
    await callback.message.answer(f"📨 {phone}\n<pre>{text}</pre>")
    await callback.answer("📋 Коды отправлены")