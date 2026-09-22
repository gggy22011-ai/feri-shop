"""
Начальные данные магазина Feris Shop: настройки по умолчанию.
Страны/номера добавляются через админ-панель (склад вручную), поэтому
сида товаров здесь нет.
"""
from __future__ import annotations

import json

from sqlalchemy import func, select

from .core import get_session
from .models import Setting

# Настройки, которые создаются при первом старте (управляются из админки).
DEFAULT_SETTINGS: dict[str, str] = {
    "welcome_text": "",
    "faq": "",
    "ref_percent": "10",
    "stars_per_ruble": "1.45",
}


async def seed_settings_if_empty() -> None:
    """Добавляет настройки по умолчанию, если их нет (не перезаписывает)."""
    from utils import texts  # ленивый импорт — не гоняем циклы

    defaults = dict(DEFAULT_SETTINGS)
    defaults["faq"] = json.dumps(texts.DEFAULT_FAQ, ensure_ascii=False)
    if not defaults["welcome_text"]:
        defaults["welcome_text"] = texts.DEFAULT_GREETING_BODY

    async with get_session() as session:
        for key, value in defaults.items():
            exists = await session.get(Setting, key)
            if exists is None:
                session.add(Setting(key=key, value=value))
        await session.commit()


async def seed_all() -> None:
    """Полный сид при старте бота."""
    await seed_settings_if_empty()