"""
FAQ (редактируется через админ-панель, хранится в settings['faq'] как JSON).
"""
from __future__ import annotations

import json

from aiogram import F, Router
from aiogram.types import CallbackQuery

from database import queries
from keyboards.user_kb import faq_kb

router = Router(name="faq")


def _load_faq(raw: str) -> list[tuple[str, str]]:
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            items = []
            for pair in data:
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    items.append((str(pair[0]), str(pair[1])))
            if items:
                return items
    except (ValueError, TypeError):
        pass
    return []


@router.callback_query(F.data == "menu:faq")
async def cb_faq(callback: CallbackQuery) -> None:
    from utils import texts

    raw = await queries.get_setting("faq")
    items = _load_faq(raw) if raw else []
    if not items:
        items = texts.DEFAULT_FAQ
    await callback.message.edit_text(
        texts.faq_text(items), reply_markup=faq_kb()
    )
    await callback.answer()