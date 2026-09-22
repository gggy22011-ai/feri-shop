"""
Обработка платежей Telegram Stars: pre_checkout_query и successful_payment.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from database import queries
from utils import notify, texts
from utils.logger import get_logger

logger = get_logger("payments")

router = Router(name="payments")


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    sp = message.successful_payment
    user_id = message.from_user.id
    username = message.from_user.username
    payload = sp.invoice_payload or ""
    amount = int(sp.total_amount or 0)  # для XTR это количество звёзд

    try:
        if payload.startswith("donate:"):
            await queries.add_transaction(user_id, "donate", amount, "⭐ Донат")
            await notify.notify_owners(
                message.bot,
                texts.DONATE_NOTIFY.format(
                    username=username or "—", stars=amount
                ),
            )
            await message.answer(texts.DONATE_THANKS.format(stars=amount))
        else:
            # Пополнение звёздами отключено: звёзды приходят только бонусами,
            # колесом или выдачей администратором.
            await message.answer(texts.PAYMENT_RECEIVED_HINT)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка обработки успешного платежа: %s", exc)
        await message.answer("⚠️ Что-то пошло не так. Обратитесь в поддержку.")