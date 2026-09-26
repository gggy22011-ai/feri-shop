"""
Покупка номеров: страны → страна → номера → номер → оплата (заявка @Clulk /
баланс ₽ / баланс ⭐). Админ подтверждает оплату — номер выдаётся.
"""
from __future__ import annotations

import config

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from database import queries
from keyboards.shop_kb import (
    buy_screen_kb,
    buy_stars_kb,
    countries_kb,
    country_card_kb,
    number_card_kb,
    numbers_kb,
)
from utils import notify, texts
from utils.logger import get_logger

logger = get_logger("shop")

router = Router(name="shop")

PAYMENT = config.PAYMENT_USERNAME.lstrip("@")


def _split_country(data: str):
    _, _, raw = data.partition(":")
    flag, country = raw.split("|", 1)
    return flag, country


def _country_price(countries: list, name: str, fallback: float) -> float:
    for _c, _f, _count, price in countries:
        if _c == name:
            return price
    return fallback


async def _open_countries(callback: CallbackQuery) -> None:
    countries = await queries.countries_with_stock()
    if not countries:
        await callback.message.edit_text(
            "❌ В базе пока нет номеров. Загляните позже!"
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        texts.SHOP_COUNTRY_LIST, reply_markup=countries_kb(countries)
    )
    await callback.answer()


@router.callback_query(F.data == "menu:buy")
async def cb_shop_countries(callback: CallbackQuery) -> None:
    await _open_countries(callback)


@router.callback_query(F.data == "shop:list")
async def cb_shop_countries_back(callback: CallbackQuery) -> None:
    await _open_countries(callback)


@router.callback_query(F.data.startswith("shop:c:"))
async def cb_shop_country(callback: CallbackQuery) -> None:
    try:
        flag, country = _split_country(callback.data)
    except ValueError:
        await callback.answer(texts.NUMBER_TAKEN, show_alert=True)
        return
    countries = await queries.countries_with_stock()
    country_data = next(
        ((c, f, count, price) for c, f, count, price in countries if c == country),
        (country, flag, 0, 0.0),
    )
    _c, _f, count, price = country_data
    await callback.message.edit_text(
        texts.COUNTRY_CARD.format(
            flag=flag, country=country, stock=count, price=price if price else 0
        ) if count else texts.SHOP_NO_NUMBERS,
        reply_markup=country_card_kb(flag, country) if count else None,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:l:"))
async def cb_shop_numbers(callback: CallbackQuery) -> None:
    try:
        flag, country = _split_country(callback.data)
    except ValueError:
        await callback.answer(texts.NUMBER_TAKEN, show_alert=True)
        return
    numbers = await queries.available_numbers(country)
    if not numbers:
        await callback.message.edit_text(
            texts.SHOP_NO_NUMBERS,
            reply_markup=countries_kb(await queries.countries_with_stock()),
        )
        await callback.answer()
        return
    shown = numbers[:40]
    lines = [texts.SHOP_NUMBERS_TITLE.format(flag=flag, country=country), ""]
    for num in shown:
        lines.append("")
        lines.append(texts.SHOP_NUMBER_LINE.format(
            phone=num.phone_number,
            operator=num.operator or "—",
            price=num.price_rubles or 0,
            stock=len(numbers),
        ))
    if len(numbers) > len(shown):
        lines.append(f"… и ещё {len(numbers) - len(shown)} номеров.")
    text = "\n".join(lines).rstrip()
    await callback.message.edit_text(
        text, reply_markup=numbers_kb(shown, flag, country)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:n:"))
async def cb_number_card(callback: CallbackQuery) -> None:
    try:
        nid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer(texts.NUMBER_TAKEN, show_alert=True)
        return
    num = await queries.get_number(nid)
    if num is None or num.status != "available":
        await callback.message.edit_text(texts.NUMBER_TAKEN)
        await callback.answer()
        return
    stock = await queries.available_number_count(num.country)
    await callback.message.edit_text(
        texts.NUMBER_CARD.format(
            flag=num.country_flag or "",
            phone=num.phone_number,
            price=num.price_rubles or 0,
            stock=stock,
        ),
        reply_markup=number_card_kb(num.id, num.country_flag or "", num.country),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:buy:"))
async def cb_buy_number(callback: CallbackQuery, bot: Bot) -> None:
    try:
        nid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer(texts.NUMBER_TAKEN, show_alert=True)
        return
    user_id = callback.from_user.id

    num = await queries.get_number(nid)
    if num is None or num.status != "available":
        await callback.message.edit_text(texts.NUMBER_TAKEN)
        await callback.answer()
        return

    existing = await queries.pending_buy_order(user_id, nid)
    if existing is not None:
        text = texts.ORDER_IN_PROGRESS.format(
            order_id=existing.id, payment=PAYMENT
        )
        await callback.message.edit_text(text)
        await callback.answer()
        return

    reserved = await queries.reserve_number(nid, user_id)
    if reserved is None:
        await callback.message.edit_text(texts.NUMBER_TAKEN)
        await callback.answer()
        return

    order = await queries.create_buy_order(reserved, user_id)
    user = await queries.get_user(user_id)
    price_r = float(reserved.price_rubles or 0)
    can_rubles = bool(user and user.rubles_balance >= price_r)
    need_stars = queries.rubles_to_stars(price_r)
    can_stars = bool(user and user.stars_balance >= need_stars)

    await callback.message.edit_text(
        texts.BUY_SCREEN.format(
            flag=reserved.country_flag or "",
            phone=reserved.phone_number,
            price=price_r,
            payment=PAYMENT,
            country=reserved.country,
        ),
        reply_markup=buy_screen_kb(order.id, nid, can_rubles, can_stars),
    )
    await callback.answer("Заявка создана. Оплатите через @%s" % PAYMENT)

    try:
        await notify.notify_owners(
            bot,
            texts.NEW_ORDER_NOTIFY.format(
                order_id=order.id,
                username=callback.from_user.username or "—",
                item=f"{reserved.country_flag or ''} {reserved.phone_number}",
                amount=price_r,
            ),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("shop:copy:"))
async def cb_copy_application(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    text = texts.BUY_APPLICATION_TEXT.format(
        phone=order.phone,
        country=order.country or "—",
        price=order.price_rubles,
    )
    await callback.message.answer(f"<pre>{text}</pre>")
    await callback.answer("📋 Заявка скопирована")


@router.callback_query(F.data.startswith("shop:stars:"))
async def cb_buy_stars(callback: CallbackQuery, bot: Bot) -> None:
    """Оплата реальными звёздами: перекидываем к владельцу, который принимает."""
    try:
        _, _, oid_s, nid_s = callback.data.split(":")
        oid, nid = int(oid_s), int(nid_s)
    except (ValueError, IndexError):
        await callback.answer("Ошибка", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    need = queries.rubles_to_stars(order.price_rubles or 0)
    await callback.message.edit_text(
        texts.BUY_STARS_SCREEN.format(
            flag=order.country_flag or "",
            phone=order.phone or "—",
            price=order.price_rubles or 0,
            need_stars=need,
            country=order.country or "—",
            stars_owner=config.STAR_OWNER,
            support=config.SUPPORT_USERNAME.lstrip("@"),
        ),
        reply_markup=buy_stars_kb(oid, nid),
    )
    await callback.answer()
    try:
        await notify.notify_owners(
            bot,
            texts.STARS_ORDER_NOTIFY.format(
                order_id=oid,
                username=callback.from_user.username or "—",
                item=f"{order.country_flag or ''} {order.phone or ''}",
                need_stars=need,
                amount=order.price_rubles or 0,
            ),
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("shop:copy_stars:"))
async def cb_copy_stars_application(callback: CallbackQuery) -> None:
    try:
        oid = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    text = texts.BUY_STARS_APPLICATION_TEXT.format(
        phone=order.phone,
        country=order.country or "—",
        need_stars=queries.rubles_to_stars(order.price_rubles or 0),
    )
    await callback.message.answer(f"<pre>{text}</pre>")
    await callback.answer("📋 Заявка скопирована")


@router.callback_query(F.data.startswith("shop:screen:"))
async def cb_buy_screen_back(callback: CallbackQuery) -> None:
    """Возврат на экран выбора оплаты (из экрана звёздной оплаты)."""
    try:
        _, _, oid_s, nid_s = callback.data.split(":")
        oid, nid = int(oid_s), int(nid_s)
    except (ValueError, IndexError):
        await callback.answer("Ошибка", show_alert=True)
        return
    order = await queries.get_order(oid)
    num = await queries.get_number(nid)
    if order is None or num is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    user = await queries.get_user(callback.from_user.id)
    price_r = float(order.price_rubles or 0)
    can_rubles = bool(user and user.rubles_balance >= price_r)
    can_stars = bool(user and user.stars_balance >= queries.rubles_to_stars(price_r))
    await callback.message.edit_text(
        texts.BUY_SCREEN.format(
            flag=order.country_flag or "",
            phone=order.phone,
            price=price_r,
            payment=config.PAYMENT_USERNAME.lstrip("@"),
            country=order.country,
        ),
        reply_markup=buy_screen_kb(oid, nid, can_rubles, can_stars),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("shop:pay:"))
async def cb_pay_from_balance(callback: CallbackQuery) -> None:
    try:
        _, _, rest = callback.data.partition("shop:pay:")
        oid, currency = rest.split(":")
        oid = int(oid)
    except (ValueError, IndexError):
        await callback.answer("Ошибка", show_alert=True)
        return
    order = await queries.get_order(oid)
    if order is None or order.user_id != callback.from_user.id:
        await callback.answer("Заказ не найден", show_alert=True)
        return
    user = await queries.get_user(callback.from_user.id)
    status, paid_order = await queries.pay_order_from_balance(oid, currency)
    if status == "insufficient":
        if currency == "stars":
            need = queries.rubles_to_stars(order.price_rubles)
            await callback.message.edit_text(
                texts.NOT_ENOUGH_STARS.format(
                    need=need, balance=user.stars_balance if user else 0
                )
            )
        else:
            await callback.message.edit_text(
                texts.NOT_ENOUGH_RUBLES.format(
                    need=order.price_rubles,
                    balance=user.rubles_balance if user else 0,
                )
            )
        await callback.answer()
        return
    if status != "ok" or paid_order is None:
        await callback.message.edit_text(texts.PURCHASE_FAILED)
        await callback.answer()
        return

    # Автовыдача: если SMS-сервис настроен — сразу закупаем реальный номер
    # и подменяем им номер-заглушку из витрины. Код придёт автоматически.
    phone = paid_order.phone
    try:
        from utils import auto_issue

        if paid_order.number_id and config.SMS_AUTO_ISSUE:
            number = await queries.get_number(paid_order.number_id)
            result = await auto_issue.issue_after_payment(paid_order, number, callback.bot)
            if result == "issued":
                fresh = await queries.get_number(paid_order.number_id)
                if fresh is not None:
                    phone = fresh.phone_number
    except Exception:  # noqa: BLE001
        logger.exception("Автовыдача номера не сработала для заказа #%s", paid_order.id)

    await callback.message.edit_text(
        texts.PURCHASE_OK.format(phone=phone)
    )
    await callback.answer("✅ Оплачено с баланса")