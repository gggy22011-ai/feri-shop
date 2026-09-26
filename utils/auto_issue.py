"""
Автовыдача реальных номеров и автоматическая доставка SMS-кодов.

Схема работы:
  1) Юзер оплатил физ. номер в магазине → вызывается issue_after_payment():
     бот сам закупает реальный номер у SMS-сервиса (sms-activate / 5sim),
     подменяет им номер-заглушку из витрины и пишет юзеру, что номер готов
     и код придёт автоматически.
  2) Фоновая задача poll_activations() (APScheduler, раз в SMS_POLL_SECONDS)
     опрашивает сервис по всем «ждущим» активациям и, как только пришёл код:
     сохраняет его в таблицу sms (его увидит «📨 Получить код») и присылает
     юзеру push. Если активация истекла — тоже сообщает, чтобы не ждал зря.

Если сервис не настроен (нет SMS_PROVIDER/ключа) — модуль молча выключен,
магазин работает в прежнем ручном режиме.
"""
from __future__ import annotations

import config
import sms_api
from aiogram import Bot
from database import queries
from database.models import Number, Order
from utils.logger import get_logger
from utils.notify import notify_owners

logger = get_logger("auto_issue")

# Сколько активаций опрашиваем за один проход (чтобы не упереться в лимиты).
MAX_PER_PASS = 15


async def _send(bot: Bot | None, user_id: int | None, text: str) -> None:
    if not bot or not user_id:
        return
    try:
        await bot.send_message(user_id, text)
    except Exception as e:  # noqa: BLE001
        logger.warning("Не удалось отправить юзеру %s: %s", user_id, e)


async def issue_after_payment(order: Order, number: Number, bot: Bot | None) -> str:
    """Закупает реальный номер для оплаченного заказа.

    Возвращает: issued / already / off / no_provider / conflict / error
    """
    if not config.SMS_AUTO_ISSUE:
        return "off"
    if number is None or number.activation_id:
        return "already"
    provider = sms_api.get_provider()
    if provider is None:
        return "no_provider"

    user_id = order.user_id
    country = number.country or order.country or ""
    country_code = sms_api.provider_country(country)
    try:
        act = await provider.issue(country_code)
    except sms_api.SmsError as e:
        logger.error("Сервис не выдал номер (%s, страна %s): %s", provider.name, country, e)
        await _send(
            bot, user_id,
            "⚠️ Не удалось автоматически получить номер у сервиса.\n"
            "Мы уже сообщим, когда всё настроим. Если срочно — напиши в поддержку.",
        )
        await notify_owners(
            bot,
            f"🚨 Автовыдача: сервис {provider.name} не выдал номер "
            f"(страна «{country}», код {country_code}).\nОшибка: {e}",
        )
        return "error"
    except Exception:  # noqa: BLE001
        logger.exception("Неожиданная ошибка при закупке номера (%s)", provider.name)
        return "error"

    cost = round(act.cost * config.SMS_PRICE_MARKUP, 2) if act.cost else 0.0
    phone = act.normalized_phone
    attached = await queries.attach_activation(
        number.id, act.provider, act.activation_id, phone=phone, cost_rubles=cost
    )
    if attached is None:
        # Такой номер уже есть в базе — активацию сдаём, чтобы не сгорели деньги.
        await provider.cancel(act)
        logger.warning("Номер %s уже в базе, активация %s отменена", phone, act.activation_id)
        return "conflict"

    await queries.set_order_phone(order.id, phone)
    logger.info(
        "Автовыдача: заказ #%s, юзер %s, номер %s (%s, id=%s, цена %s₽)",
        order.id, user_id, phone, act.provider, act.activation_id, cost or "-",
    )

    await _send(
        bot, user_id,
        f"✅ <b>Номер получен!</b>\n\n"
        f"📱 {act.country or country}: <code>{phone}</code>\n"
        f"⏳ Код от Telegram придёт сюда автоматически в течение "
        f"{config.SMS_WAIT_MINUTES} минут.\n\n"
        f"Код всегда доступен в разделе «📨 Получить код».",
    )

    # Контроль маржи: предупреждаем владельцев, если продажа ушла в минус.
    if cost and order.price_rubles and order.price_rubles < cost:
        await notify_owners(
            bot,
            f"⚠️ Продажа в минус: заказ #{order.id} — оплачено "
            f"{order.price_rubles}₽, номер стоит {cost}₽ "
            f"({act.provider}, {country}).",
        )
    return "issued"


async def poll_activations(bot: Bot | None) -> None:
    """Фоновая задача: проверяет SMS по всем ожидающим активациям."""
    if not config.SMS_AUTO_ISSUE:
        return
    provider = sms_api.get_provider()
    if provider is None:
        return

    # Страховка: если по активации давно не пришло ничего — гасим её.
    try:
        stale = await queries.expire_stale_activations(config.SMS_WAIT_MINUTES)
        if stale:
            logger.info("Истекло активаций без кода: %d", stale)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось проверить просроченные активации")

    try:
        numbers = await queries.waiting_activations()
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось получить список ожидающих активаций")
        return

    for number in numbers[:MAX_PER_PASS]:
        act = sms_api.Activation(
            provider=number.activation_provider or provider.name,
            activation_id=str(number.activation_id),
            phone=number.phone_number,
        )
        try:
            status, code = await provider.poll_code(act)
        except Exception as e:  # noqa: BLE001
            logger.warning("Ошибка опроса активации %s: %s", act.activation_id, e)
            continue

        if status == sms_api.DONE and code:
            user_id = number.owner_id
            await queries.add_sms(
                user_id=user_id or 0,
                phone=number.phone_number,
                app="Telegram",
                code=code,
                number_id=number.id,
                added_by=None,
            )
            await queries.set_activation_status(number.id, "done")
            await _send(
                bot, user_id,
                f"📨 <b>Код от Telegram</b>\n\n"
                f"Номер: <code>{number.phone_number}</code>\n"
                f"Код: <code>{code}</code>",
            )
            logger.info("Код %s получен для номера %s (юзер %s)", code, number.phone_number, user_id)

        elif status in (sms_api.EXPIRED, sms_api.CANCELED):
            await queries.set_activation_status(number.id, "expired")
            await _send(
                bot, number.owner_id,
                f"⌛ Не удалось получить код для <code>{number.phone_number}</code> — "
                f"активация на стороне сервиса истекла.\n"
                f"Напиши в поддержку, мы выдадим замену.",
            )
            await notify_owners(
                bot,
                f"⌛ Активация истекла без кода: номер {number.phone_number}, "
                f"id={act.activation_id} ({act.provider}).",
            )
