"""
SQLAlchemy-модели магазина Feris Shop.

Схема (из ТЗ):
 users, numbers, countries, orders, transactions, sms, bug_reports,
 daily_bonuses, admin_logs, settings
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # = Telegram ID
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stars_balance: Mapped[int] = mapped_column(Integer, default=0)
    rubles_balance: Mapped[float] = mapped_column(Float, default=0.0)
    referrer_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    registered_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )
    last_active: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, default=None
    )


class Country(Base):
    """Страны магазина: флаг, цена по умолчанию, доступность в витрине."""

    __tablename__ = "countries"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    country_flag: Mapped[str] = mapped_column(String(16), default="")
    price_rubles: Mapped[float] = mapped_column(Float, default=0.0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Number(Base):
    __tablename__ = "numbers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    country: Mapped[str] = mapped_column(String(128), index=True)
    country_flag: Mapped[str] = mapped_column(String(16), default="")
    phone_number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_rubles: Mapped[float] = mapped_column(Float, default=0.0)
    price_stars: Mapped[int] = mapped_column(Integer, default=0)  # legacy
    status: Mapped[str] = mapped_column(  # available / reserved / sold
        String(16), default="available", index=True
    )
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    reserved_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )
    sold_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # ── Автовыдача реальных номеров (сервисы приёма SMS) ──────────────────
    # activation_id  — id активации у провайдера (sms-activate / 5sim)
    # activation_at  — когда закуплена активация (по нему считаем таймаут)
    # activation_status: none / waiting / done / expired / canceled
    activation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    activation_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    activation_status: Mapped[str] = mapped_column(String(16), default="none", index=True)
    activation_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Order(Base):
    """Заказы магазина: покупка номера и пополнение рублями.

    kind: buy / deposit
    status: pending / paid / cancelled
    Для buy получателем (владельцем) номера становится user_id после confirm.
    Для deposit подтверждение зачисляет рубли на баланс пользователя.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True, default="buy")
    number_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    country_flag: Mapped[str] = mapped_column(String(16), default="")
    price_rubles: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(16), default="rubles")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Transaction(Base):
    """Все движения денег: пополнения, покупки, донаты, корректировки.

    type: stars_in / stars_out / rubles_in / rubles_out / purchase / donate / bonus
    description для purchase/donate/bonus начинается с «⭐ » или «₽ » — по этому
    префиксу считается выручка по валютам.
    """

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(24), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class Sms(Base):
    """SMS-коды для номеров пользователей (админ заносит вручную)."""

    __tablename__ = "sms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)  # кому виден
    number_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str] = mapped_column(String(32))
    app: Mapped[str] = mapped_column(String(64), default="Telegram")
    code: Mapped[str] = mapped_column(String(128))
    added_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class BugReport(Base):
    """Лог багов: записи админов и жалобы пользователей."""

    __tablename__ = "bug_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class DailyBonus(Base):
    """Отметки получения ежедневного бонуса (одна запись на юзера)."""

    __tablename__ = "daily_bonuses"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claimed_on: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD (UTC)
    last_claimed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class AdminLog(Base):
    """Полный лог действий администратора."""

    __tablename__ = "admin_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(255))
    target_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now()
    )


class Setting(Base):
    """Тексты/параметры, редактируемые через админ-панель (например FAQ)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")