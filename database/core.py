"""Ядро БД Feris Shop: engine, сессии, создание таблиц.

Миграции идемпотентны и НЕ удаляют пользовательские данные: при несовпадении
PRAGMA user_version добавляются недостающие колонки/таблицы, лишние колонки
старых схем остаются нетронутыми.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from .models import Base

SCHEMA_VERSION = 3

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def init_engine() -> None:
    """Создаёт engine и фабрику сессий по DB_URL из конфига."""
    global _engine, _session_factory
    _engine = create_async_engine(config.DB_URL, echo=False, future=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


# Колонки, которые могли появиться в новых версиях схемы: (таблица, колонка, DDL).
_ADDITIVE_COLUMNS = {
    "users": [
        ("referrer_id", "INTEGER"),
    ],
    "numbers": [
        ("price_rubles", "FLOAT"),
    ],
}


async def _ensure_columns(conn) -> None:
    """Добавляет отсутствующие колонки (ALTER TABLE ADD COLUMN)."""
    for table, columns in _ADDITIVE_COLUMNS.items():
        existing = set()
        try:
            rows = await conn.execute(
                text(f"PRAGMA table_info({table})")
            )
            existing = {r[1] for r in rows.fetchall()}
        except Exception:  # noqa: BLE001
            continue
        for col, ddl in columns:
            if col in existing:
                continue
            await conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
            )
            # Легаси-строки без цены приводятся к 0, иначе в магазине
            # всплывёт «None ₽» (а в клавиатурах — TypeError от форматирования).
            if table == "numbers" and col == "price_rubles":
                try:
                    await conn.execute(
                        text("UPDATE numbers SET price_rubles=0 WHERE price_rubles IS NULL")
                    )
                except Exception:  # noqa: BLE001
                    pass


async def init_db() -> None:
    """Создаёт/дополняет схему до текущей версии; данные сохраняются."""
    if _engine is None:
        init_engine()
    async with _engine.begin() as conn:
        # Сначала полная схема (fresh-база создаётся сразу актуальной).
        await conn.run_sync(Base.metadata.create_all)
        try:
            version = await conn.scalar(text("PRAGMA user_version")) or 0
        except Exception:  # noqa: BLE001
            # Не-SQLite (например Postgres): PRAGMA недоступен, миграции не нужны —
            # create_all уже собрал актуальную схему.
            version = SCHEMA_VERSION
        if version < SCHEMA_VERSION:
            # Для старых баз точечно добавляем отсутствующие колонки.
            await _ensure_columns(conn)
            await conn.execute(text(f"PRAGMA user_version={SCHEMA_VERSION}"))


@asynccontextmanager
async def get_session() -> AsyncIterator:
    """
    Асинхронный контекстный менеджер сессии.
    Использование:  async with get_session() as session: ...
    """
    if _session_factory is None:
        init_engine()
    async with _session_factory() as session:
        yield session