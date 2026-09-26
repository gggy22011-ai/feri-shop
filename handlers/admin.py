"""
Админ-панель Feris Shop: вход по паролю, подтверждение оплат, склад,
страны, FAQ, владельцы, баги, настройки, SMS, рассылка, статистика,
блокировки, логирование действий администратора.

Владельцы (@Clulk, @No7777oN) входят без пароля.
"""
from __future__ import annotations

import re
import time

import config
from aiogram import BaseMiddleware, Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import queries
from keyboards.admin_kb import (
    admin_back_kb,
    admin_panel_kb,
    bug_delete_kb,
    countries_kb,
    country_delete_kb,
    faq_delete_kb,
    faq_kb,
    number_choice_kb,
    orders_kb,
    owners_kb,
    settings_kb,
    sklad_kb,
    sms_action_kb,
    sms_kb,
    bugs_kb,
)
from utils import texts
from utils.helpers import date_format, parse_money_input, parse_user_input
from utils.logger import get_logger
from utils.states import (
    AdminAddNumbers,
    AdminAuth,
    AdminBlockUser,
    AdminBroadcast,
    AdminBugAdd,
    AdminCountryAdd,
    AdminCountryPrice,
    AdminDeleteNumber,
    AdminFaqAdd,
    AdminGiveMoney,
    AdminIssueNumber,
    AdminOwnerAdd,
    AdminOwnerDel,
    AdminSettingsEdit,
    AdminSmsAdd,
    AdminTakeMoney,
    AdminTakeNumber,
    AdminUserInfo,
)

logger = get_logger("admin")
router = Router(name="admin")


async def _resolve_target(raw: str) -> tuple[str | None, int | None]:
    """'123456789' или '@nickname' (или 'nickname') → (ошибка_or_None, user_id).

    Числовой ввод принимается как есть (пользователь может ещё не
    регистрироваться — например, при выдаче номера). Username резолвится
    через БД и должен существовать.
    """
    raw = (raw or "").strip().lstrip("@")
    if not raw:
        return "❌ Введите user_id или @username.", None
    if raw.isdigit():
        return None, int(raw)
    user = await queries.find_user_by_username(raw)
    if user is None:
        return "❌ Пользователь с таким username не найден.", None
    return None, user.id

# ─────────────────────────────────────────────────────────────────────────────
# Сессии админов (in-memory)
# ─────────────────────────────────────────────────────────────────────────────
_authorized: dict[int, float] = {}
_attempts: dict[int, int] = {}
_blocked_until: dict[int, float] = {}


def _grant(user_id: int) -> None:
    _authorized[user_id] = time.monotonic()


def _revoke(user_id: int) -> None:
    _authorized.pop(user_id, None)


def _is_authorized(user_id: int) -> bool:
    ts = _authorized.get(user_id)
    if ts is None:
        return False
    if time.monotonic() - ts > config.ADMIN_SESSION_TTL_SECONDS:
        _revoke(user_id)
        return False
    _authorized[user_id] = time.monotonic()
    return True


def _is_blocked(user_id: int) -> bool:
    block_until = _blocked_until.get(user_id, 0.0)
    return time.monotonic() < block_until


def _is_owner(user_id: int, username: str | None) -> bool:
    return config.is_owner(user_id, username)


# ─────────────────────────────────────────────────────────────────────────────
# Middleware: доступ к админ-роутеру
# ─────────────────────────────────────────────────────────────────────────────
class AdminGateMiddlewware(BaseMiddleware):
    async def __call__(self, handler, event, data) -> None:
        user = event.from_user
        if user is None:
            return await handler(event, data)

        if isinstance(event, Message):
            text = event.text or ""
            if text == "/admin":
                return await handler(event, data)
            state = data.get("state")
            cur_state = None
            if state is not None:
                cur_state = await state.get_state()
            if cur_state and cur_state.startswith("Admin"):
                return await handler(event, data)
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            cb = event.data or ""
            if cb.startswith("admin:"):
                if _is_owner(user.id, user.username) or _is_authorized(user.id):
                    return await handler(event, data)
                await event.answer("🔒 Войдите в админку — /admin", show_alert=True)
                return None
            return await handler(event, data)

        return await handler(event, data)


router.message.middleware(AdminGateMiddlewware())
router.callback_query.middleware(AdminGateMiddlewware())


# ─────────────────────────────────────────────────────────────────────────────
# Вход
# ─────────────────────────────────────────────────────────────────────────────
@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if _is_blocked(user.id):
        await message.answer(texts.ADMIN_BLOCKED)
        return
    if _is_owner(user.id, user.username) or _is_authorized(user.id):
        await _open_panel(message, user.id, user.username)
        return
    await state.set_state(AdminAuth.waiting_password)
    await message.answer(texts.ADMIN_ASK_PASSWORD)


@router.message(AdminAuth.waiting_password)
async def check_password(message: Message, state: FSMContext) -> None:
    user = message.from_user
    if _is_blocked(user.id):
        await message.answer(texts.ADMIN_BLOCKED)
        return
    if (message.text or "").strip() == config.ADMIN_PASSWORD:
        _attempts.pop(user.id, None)
        _grant(user.id)
        await state.clear()
        await _open_panel(message, user.id, user.username)
        return
    attempts = _attempts.get(user.id, 0) + 1
    _attempts[user.id] = attempts
    if attempts >= config.MAX_PASSWORD_ATTEMPTS:
        _blocked_until[user.id] = time.monotonic() + config.PASSWORD_BLOCK_SECONDS
        _attempts.pop(user.id, None)
        await state.clear()
        await message.answer(texts.ADMIN_BLOCKED)
        return
    await message.answer(
        texts.ADMIN_WRONG_PASSWORD.format(
            attempt=attempts, max=config.MAX_PASSWORD_ATTEMPTS
        )
    )


async def _open_panel(message: Message, admin_id: int, username: str | None) -> None:
    _grant(admin_id)
    await queries.log_admin(
        admin_id, texts.ADMIN_LOGIN_LOG,
        details=f"username=@{username}" if username else None,
    )
    pending = await queries.order_count_pending()
    await message.answer(
        texts.ADMIN_MAIN_PANEL, reply_markup=admin_panel_kb(pending)
    )


def _admin_err_kb() -> InlineKeyboardMarkup:
    return admin_back_kb()


# ─────────────────────────────────────────────────────────────────────────────
# Панель / выход / отмена
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:panel")
async def cb_admin_panel(callback: CallbackQuery) -> None:
    pending = await queries.order_count_pending()
    await callback.message.edit_text(
        texts.ADMIN_MAIN_PANEL, reply_markup=admin_panel_kb(pending)
    )
    await callback.answer()


@router.callback_query(F.data == "admin:exit")
async def cb_admin_exit(callback: CallbackQuery) -> None:
    _revoke(callback.from_user.id)
    await callback.message.edit_text(
        "🔒 Вы вышли из админ-панели.\n\n"
        "Хотите вернуться в магазин? — /start"
    )
    await callback.answer()


@router.callback_query(F.data == "admin:cancel")
async def cb_admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await cb_admin_panel(callback)


# ─────────────────────────────────────────────────────────────────────────────
# Подтверждение оплат / заказы
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:orders")
async def cb_admin_orders(callback: CallbackQuery) -> None:
    if _is_blocked(callback.from_user.id):
        await callback.answer(texts.ADMIN_BLOCKED, show_alert=True)
        return
    orders = await queries.pending_orders()
    if not orders:
        await callback.message.edit_text(
            "✅ Ожидающих оплаты заказов нет.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"🧾 Заказов в ожидании: <b>{len(orders)}</b>\n\n"
        "Выберите: ✅ подтвердить оплату или ❌ отменить.",
        reply_markup=orders_kb(orders),
    )
    await callback.answer()


async def _notify_order_result(bot: Bot, order, admin_id: int, confirmed: bool) -> None:
    if order is None:
        return
    if confirmed:
        if order.kind == "deposit":
            user = await queries.get_user(order.user_id)
            balance = user.rubles_balance if user else 0
            text = texts.DEPOSIT_CONFIRMED_USER.format(
                amount=order.price_rubles,
                order_id=order.id,
                balance=balance,
            )
        else:
            text = texts.ORDER_CONFIRMED_USER.format(
                order_id=order.id,
                result=f"📞 Номер {order.phone or '—'} ваш! "
                       f"Он в «Мои номера», коды — в «Получить код».",
            )
    else:
        text = texts.ORDER_CANCELLED_USER.format(order_id=order.id)
    await queries.log_admin(
        admin_id,
        "Подтвердить оплату" if confirmed else "Отменить заказ",
        target_user_id=order.user_id,
        details=f"#{order.id} {'✅' if confirmed else '❌'} "
                f"{order.phone or f'{order.price_rubles:g} ₽'}",
    )
    try:
        await bot.send_message(order.user_id, text)
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data.startswith("admin:order_x:"))
async def cb_admin_order_confirm(
    callback: CallbackQuery, bot: Bot
) -> None:
    oid = int(callback.data.rsplit(":", 1)[1])
    order = await queries.confirm_order(oid, callback.from_user.id)
    if order is None:
        await callback.message.edit_text(
            "❌ Не удалось подтвердить заказ: он уже обработан, либо номер "
            "больше не зарезервирован за покупателем (могла закончиться бронь)."
        )
        await callback.answer()
        await cb_admin_orders(callback)
        return
    await _notify_order_result(bot, order, callback.from_user.id, True)

    # Автовыдача реального номера после ручного подтверждения оплаты.
    try:
        from utils import auto_issue

        if order.number_id and config.SMS_AUTO_ISSUE:
            number = await queries.get_number(order.number_id)
            await auto_issue.issue_after_payment(order, number, bot)
    except Exception:  # noqa: BLE001
        logger.exception("Автовыдача номера не сработала для заказа #%s", order.id)

    msg = "✅ Заказ подтверждён, пользователю отправлено уведомление."
    await callback.message.edit_text(msg)
    await callback.answer()
    await cb_admin_orders(callback)


@router.callback_query(F.data.startswith("admin:order_z:"))
async def cb_admin_order_cancel(
    callback: CallbackQuery, bot: Bot
) -> None:
    oid = int(callback.data.rsplit(":", 1)[1])
    order = await queries.cancel_order(oid, callback.from_user.id)
    if order is None:
        await callback.message.edit_text(
            "❌ Не удалось отменить заказ: он уже обработан."
        )
        await callback.answer()
        await cb_admin_orders(callback)
        return
    await _notify_order_result(bot, order, callback.from_user.id, False)
    await callback.message.edit_text(
        "❌ Заказ отменён, номер возвращён в сток."
    )
    await callback.answer()
    await cb_admin_orders(callback)


# ─────────────────────────────────────────────────────────────────────────────
# Склад номеров
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:sklad")
async def cb_admin_sklad(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📱 <b>Склад номеров</b>\n\nВыберите действие:",
        reply_markup=sklad_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:add_numbers")
async def admin_add_numbers_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminAddNumbers.form)
    await callback.message.edit_text(
        "➕ <b>Добавление номеров</b>\n\n"
        "Каждая строка — один номер:\n"
        "<code>страна | номер | оператор | цена</code>\n"
        "или без оператора:\n"
        "<code>страна | номер | цена</code>\n\n"
        "Можно слать просто номера — страна определится "
        "по коду телефона (+380… → Украина):\n"
        "<code>+380970919218</code>\n\n"
        "Цена — в рублях ₽ (например <code>170</code> или <code>170₽</code>). "
        "Можно указать в звёздах: <code>250⭐</code> — переведём в ₽ по курсу.\n\n"
        "Пример:\n"
        "<code>Россия | +79123456789 | МТС | 149</code>\n"
        "<code>🇰🇿 Казахстан | +77001234567 | 269</code>\n"
        "<code>🇺🇸 США | +14155550123 | 50₽</code>\n\n"
        "Пришлите список номеров одним сообщением:",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminAddNumbers.form)
async def admin_add_numbers_form(message: Message, state: FSMContext) -> None:
    lines = (message.text or "").strip().splitlines()
    try:
        items = queries.parse_number_lines(lines)
    except ValueError as exc:
        await message.answer(f"❌ {exc}\nПопробуйте снова:")
        return
    if not items:
        await message.answer("❌ Ничего не получилось распознать. Попробуйте снова:")
        return
    added = await queries.add_numbers(items)
    await queries.log_admin(
        message.from_user.id, "Добавить номера в базу",
        details=f"строк: {len(items)}, добавлено: {added}\n"
                f"{message.text[:400]}",
    )
    await state.clear()
    sample = ", ".join(i["phone_number"] for i in items[:5])
    await message.answer(
        f"✅ Добавлено номеров: <b>{added}</b> из {len(items)} "
        f"(дубли пропущены).\nПример: {sample}",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:list_numbers")
async def admin_list_numbers_start(callback: CallbackQuery) -> None:
    countries = await queries.countries_with_stock()
    rows = [
        [InlineKeyboardButton(text="🌍 Все страны", callback_data="admin:listall")]
    ]
    for country, flag, count, price in countries:
        rows.append([InlineKeyboardButton(
            text=f"{flag} {country} ({count}) · {price:g} ₽",
            callback_data=f"admin:listc:{country}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ В склад", callback_data="admin:sklad")])
    await callback.message.edit_text(
        "🗂 Список доступных номеров. Выберите страну для фильтра:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:listc:"))
async def admin_list_country(callback: CallbackQuery) -> None:
    country = callback.data.partition("admin:listc:")[2]
    await _render_available_list(callback, country)


@router.callback_query(F.data == "admin:listall")
async def admin_list_all(callback: CallbackQuery) -> None:
    await _render_available_list(callback, None)


async def _render_available_list(
    callback: CallbackQuery, country: str | None
) -> None:
    numbers = await queries.available_numbers(country)
    if not numbers:
        await callback.message.edit_text(
            "❌ Доступных номеров нет.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    parts = [f"🗂 Найдено: {len(numbers)}"]
    if country:
        parts[0] += f" ({country})"
    for num in numbers[:40]:
        parts.append(
            f"#{num.id} · {num.phone_number} · {num.operator or '—'} · "
            f"{num.price_rubles:g} ₽ · {num.country}"
        )
    if len(numbers) > 40:
        parts.append(f"... и ещё {len(numbers) - 40}")
    rows = []
    for num in numbers[:20]:
        rows.append([InlineKeyboardButton(
            text=f"🗑 Удалить {num.phone_number}",
            callback_data=f"admin:deln:{num.id}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin:list_numbers")])
    await callback.message.edit_text(
        "\n".join(parts), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:deln:"))
async def admin_delete_from_list(callback: CallbackQuery, state: FSMContext) -> None:
    nid = int(callback.data.rsplit(":", 1)[1])
    await _do_delete(callback, nid, state)


@router.callback_query(F.data == "admin:delete_number")
async def admin_delete_number_start(callback: CallbackQuery, state: FSMContext) -> None:
    numbers = await queries.available_numbers()
    if not numbers:
        await callback.message.edit_text(
            "❌ Список доступных номеров пуст.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await state.set_state(AdminDeleteNumber.phone)
    await callback.message.edit_text(
        "🗑 Введите номер для удаления или выберите из списка:",
        reply_markup=number_choice_kb(numbers, "admin:delp"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delp:"))
async def admin_delete_pick(callback: CallbackQuery, state: FSMContext) -> None:
    nid = int(callback.data.rsplit(":", 1)[1])
    await _do_delete(callback, nid, state)


async def _do_delete(callback: CallbackQuery, nid: int, state: FSMContext | None = None) -> None:
    num = await queries.get_number(nid)
    ok = await queries.delete_number(nid)
    if state is not None:
        await state.clear()
    if not ok:
        await callback.message.edit_text(
            "❌ Номер не найден или уже продан.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await queries.log_admin(
        callback.from_user.id, "Удалить номер из базы",
        details=num.phone_number if num else str(nid),
    )
    await callback.message.edit_text(
        f"🗑 Номер #{nid} удалён из базы.", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminDeleteNumber.phone)
async def admin_delete_manual(message: Message, state: FSMContext) -> None:
    num = await queries.get_number_by_phone(message.text or "")
    await state.clear()
    if num is None:
        await message.answer("❌ Номер не найден.", reply_markup=admin_back_kb())
        return
    ok = await queries.delete_number(num.id)
    await queries.log_admin(
        message.from_user.id, "Удалить номер из базы", details=num.phone_number
    )
    await message.answer(
        f"🗑 Номер {num.phone_number} удалён из базы.", reply_markup=admin_back_kb()
    )


# ─────────────────────────────────────────────────────────────────────────────
# Страны
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:countries")
async def cb_admin_countries(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🌍 <b>Управление странами</b>", reply_markup=countries_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:c_add")
async def admin_country_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminCountryAdd.name)
    await callback.message.edit_text(
        "🌍 Название страны (можно с флагом), например: Украина 🇺🇦",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminCountryAdd.name)
async def admin_country_add_name(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    flag = queries.fetch_flag(raw)
    name = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}\s*", "", raw).strip() or raw
    await state.update_data(name=name, flag=flag)
    await state.set_state(AdminCountryAdd.price)
    await message.answer(
        f"🌍 Страна: {flag} {name}\n💰 Введите цену в рублях (например 100):"
    )


@router.message(AdminCountryAdd.price)
async def admin_country_add_price(message: Message, state: FSMContext) -> None:
    try:
        price = round(parse_money_input(message.text or ""), 2)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену в рублях:")
        return
    data = await state.get_data()
    await queries.upsert_country(data["name"], data.get("flag") or "", price)
    await queries.log_admin(
        message.from_user.id, "Добавить страну",
        details=f"{data.get('flag') or ''}{data['name']} · {price} ₽",
    )
    await state.clear()
    await message.answer(
        f"✅ Страна {data.get('flag') or ''}<b>{data['name']}</b> добавлена "
        f"(цена {price:g} ₽).",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:c_list")
async def admin_country_list(callback: CallbackQuery) -> None:
    countries = await queries.registered_countries()
    if not countries:
        await callback.message.edit_text(
            "🌍 Зарегистрированных стран нет.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    lines = ["🌍 <b>Страны</b>\n"]
    rows = []
    for c in countries:
        status = "✅" if c.enabled else "⛔"
        lines.append(
            f"{status} {c.country_flag or '🌐'} <b>{c.name}</b> — "
            f"{c.price_rubles:g} ₽"
        )
        rows.append([InlineKeyboardButton(
            text=f"💲 Цена {c.country_flag or '🌐'} {c.name}",
            callback_data=f"admin:c_price:{c.name}",
        )])
    rows.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin:countries")])
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:c_price:"))
async def admin_country_edit_price_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    name = callback.data.partition("admin:c_price:")[2]
    country = await queries.get_country(name)
    if country is None:
        await callback.message.edit_text(
            "❌ Страна не найдена.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await state.update_data(name=name)
    await state.set_state(AdminCountryPrice.price)
    await callback.message.edit_text(
        f"💲 Текущая цена: {country.price_rubles:g} ₽\n"
        f"Введите новую цену в рублях:",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminCountryPrice.price)
async def admin_country_edit_price(message: Message, state: FSMContext) -> None:
    try:
        price = round(parse_money_input(message.text or ""), 2)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Введите корректную цену в рублях:")
        return
    data = await state.get_data()
    country = await queries.get_country(data["name"])
    await queries.upsert_country(data["name"], country.country_flag if country else "", price)
    await queries.log_admin(
        message.from_user.id, "Изменить цену страны",
        details=f"{data['name']} · {price} ₽",
    )
    await state.clear()
    await message.answer(
        f"✅ Цена страны <b>{data['name']}</b> теперь {price:g} ₽.",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:c_del")
async def admin_country_delete_list(callback: CallbackQuery) -> None:
    countries = await queries.registered_countries()
    if not countries:
        await callback.message.edit_text(
            "🌍 Зарегистрированных стран нет.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "🗑 Выберите страну для удаления:",
        reply_markup=country_delete_kb(countries),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:c_del1:"))
async def admin_country_delete_confirm(callback: CallbackQuery) -> None:
    name = callback.data.partition("admin:c_del1:")[2]
    ok = await queries.remove_country(name)
    await queries.log_admin(
        callback.from_user.id, "Удалить страну", details=name
    )
    await callback.message.edit_text(
        "✅ Страна <b>%s</b> удалена из списка стран." % name if ok
        else "❌ Страна не найдена.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Выдать / забрать номер
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:issue")
async def admin_issue_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminIssueNumber.user_id)
    await callback.message.edit_text(
        "📞 Введите user_id получателя (или @username):\n"
        "(можно узнать через «Информация о пользователе» или /admin)",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminIssueNumber.user_id)
async def admin_issue_userid(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    await state.update_data(target=uid)
    await state.set_state(AdminIssueNumber.country)
    await message.answer("🌍 Введите страну (можно с флагом), например: Россия 🇷🇺")


@router.message(AdminIssueNumber.country)
async def admin_issue_country(message: Message, state: FSMContext) -> None:
    raw = message.text.strip()
    flag = queries.fetch_flag(raw)
    name = re.sub(r"[\U0001F1E6-\U0001F1FF]{2}\s*", "", raw).strip() or raw
    await state.update_data(country=name, flag=flag)
    await state.set_state(AdminIssueNumber.phone)
    await message.answer("📞 Введите сам номер, например: +79123456789")


@router.message(AdminIssueNumber.phone)
async def admin_issue_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await state.set_state(AdminIssueNumber.operator)
    await message.answer(
        "🛰 Введите оператора (если есть).\n"
        "Если оператора нет — отправьте «—»."
    )


@router.message(AdminIssueNumber.operator)
async def admin_issue_operator(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    operator = None if message.text.strip() in {"—", "-", "нет", "."} else message.text.strip()
    uid = data.get("target")
    price = 0.0
    country = await queries.get_country(data.get("country") or "")
    if country:
        price = country.price_rubles
    num = await queries.give_number_free(
        user_id=uid,
        country=data.get("country") or "",
        country_flag=data.get("flag") or "",
        phone=data.get("phone") or "",
        operator=operator,
        price_rubles=price,
    )
    if num is None:
        await message.answer("❌ Номер с таким номером уже существует в базе.")
        await state.clear()
        return
    await queries.log_admin(
        message.from_user.id, "Выдать номер",
        target_user_id=uid,
        details=f"{num.country} {num.phone_number} {operator or ''}".strip(),
    )
    await state.clear()
    await message.answer(
        f"✅ Номер {num.phone_number} выдан пользователю {uid}.\n"
        f"Он доступен в «Мои номера» у получателя.",
        reply_markup=admin_back_kb(),
    )
    try:
        await message.bot.send_message(
            uid, f"📞 Вам выдан номер {num.phone_number}"
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "admin:take_number")
async def admin_take_number_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminTakeNumber.user_id)
    await callback.message.edit_text(
        "📥 Введите user_id (или @username) пользователя:", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminTakeNumber.user_id)
async def admin_take_number_userid(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    numbers = await queries.user_numbers(uid)
    if not numbers:
        await state.clear()
        await message.answer(
            "ℹ️ У этого пользователя нет номеров.", reply_markup=admin_back_kb()
        )
        return
    await state.update_data(target=uid)
    await state.set_state(AdminTakeNumber.phone)
    await message.answer(
        "📥 Выберите номер для изъятия (или введите его вручную):",
        reply_markup=number_choice_kb(numbers, "admin:tn"),
    )


@router.callback_query(F.data.startswith("admin:tn:"))
async def admin_take_number_pick(
    callback: CallbackQuery, state: FSMContext
) -> None:
    nid = int(callback.data.rsplit(":", 1)[1])
    data = await state.get_data()
    uid = data.get("target")
    num = await queries.get_number(nid)
    await state.clear()
    if num is None or num.owner_id != uid:
        await callback.message.edit_text(
            "❌ Номер не найден у пользователя.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    ok = await queries.take_number_from_user(nid, uid)
    await queries.log_admin(
        callback.from_user.id, "Забрать номер",
        target_user_id=uid, details=num.phone_number,
    )
    await callback.message.edit_text(
        f"✅ Номер {num.phone_number} изъят у {uid} и возвращён в базу.",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminTakeNumber.phone)
async def admin_take_number_manual(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    uid = data.get("target")
    num = await queries.get_number_by_phone(message.text or "")
    await state.clear()
    if num is None or num.owner_id != uid:
        await message.answer(
            "❌ Номер не найден у этого пользователя.", reply_markup=admin_back_kb()
        )
        return
    ok = await queries.take_number_from_user(num.id, uid)
    await queries.log_admin(
        message.from_user.id, "Забрать номер",
        target_user_id=uid, details=num.phone_number,
    )
    await message.answer(
        f"✅ Номер {num.phone_number} изъят у {uid} и возвращён в базу.",
        reply_markup=admin_back_kb(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Выдать / забрать валюту (₽ или ⭐) — выбор валюты кнопками
# ─────────────────────────────────────────────────────────────────────────────
def _currency_kb(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="₽ Рубли", callback_data=f"{prefix}:rubles"),
                InlineKeyboardButton(text="⭐ Звёзды", callback_data=f"{prefix}:stars"),
            ],
            [InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")],
        ]
    )


def _parse_plain_amount(raw: str) -> float | None:
    """Число из «100»/«50.5». Мусор → None."""
    try:
        value = parse_money_input(raw or "")
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


@router.callback_query(F.data == "admin:give_money")
async def admin_give_money_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminGiveMoney.user_id)
    await callback.message.edit_text(
        "💰 Введите user_id (или @username) пользователя:", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminGiveMoney.user_id)
async def admin_give_money_userid(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    await state.update_data(target=uid)
    await state.set_state(AdminGiveMoney.currency)
    await message.answer("💰 Выберите валюту:", reply_markup=_currency_kb("admin:give_cur"))


@router.callback_query(F.data.startswith("admin:give_cur:"))
async def admin_give_money_currency(callback: CallbackQuery, state: FSMContext) -> None:
    cur = callback.data.rsplit(":", 1)[1]
    if cur not in {"rubles", "stars"}:
        await callback.answer()
        return
    await state.update_data(currency=cur)
    await state.set_state(AdminGiveMoney.amount)
    label = "⭐" if cur == "stars" else "₽"
    await callback.message.edit_text(
        f"💳 Валюта: <b>{label}</b>\n\n💰 Введите сумму (число):"
    )
    await callback.answer()


@router.message(AdminGiveMoney.amount)
async def admin_give_money_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_plain_amount(message.text or "")
    if amount is None:
        await message.answer(texts.DEPOSIT_WRONG_AMOUNT)
        return
    await state.update_data(amount=amount)
    await state.set_state(AdminGiveMoney.reason)
    await message.answer(
        "📝 Причина (необязательно). Отправьте «—», чтобы пропустить:"
    )


@router.message(AdminGiveMoney.reason)
async def admin_give_money_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    reason = message.text.strip() if message.text and message.text.strip() not in {"—", "-"} else None
    label = "⭐" if data["currency"] == "stars" else "₽"
    if data["currency"] == "stars":
        await queries.add_stars(data["target"], int(data["amount"]),
                                f"{label} {reason or 'Начисление админом'}")
    else:
        await queries.add_rubles(data["target"], float(data["amount"]),
                                 f"{label} {reason or 'Начисление админом'}")
    user = await queries.get_user(data["target"])
    await queries.log_admin(
        message.from_user.id, "Выдать валюту",
        target_user_id=data["target"],
        details=f"+{data['amount']:g}{label} · {reason or ''}".strip(),
    )
    await state.clear()
    balance = f"{user.stars_balance} ⭐" if data["currency"] == "stars" else \
        f"{user.rubles_balance:g} ₽"
    await message.answer(
        f"✅ Начислено {data['amount']:g} {label} пользователю {data['target']}.\n"
        f"Новый баланс: {balance}",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:take_money")
async def admin_take_money_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminTakeMoney.user_id)
    await callback.message.edit_text(
        "🏦 Введите user_id (или @username) пользователя:", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminTakeMoney.user_id)
async def admin_take_money_userid(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    await state.update_data(target=uid)
    await state.set_state(AdminTakeMoney.currency)
    await message.answer("🏦 Выберите валюту:", reply_markup=_currency_kb("admin:take_cur"))


@router.callback_query(F.data.startswith("admin:take_cur:"))
async def admin_take_money_currency(callback: CallbackQuery, state: FSMContext) -> None:
    cur = callback.data.rsplit(":", 1)[1]
    if cur not in {"rubles", "stars"}:
        await callback.answer()
        return
    await state.update_data(currency=cur)
    await state.set_state(AdminTakeMoney.amount)
    label = "⭐" if cur == "stars" else "₽"
    await callback.message.edit_text(
        f"💳 Валюта: <b>{label}</b>\n\n🏦 Введите сумму для списания (число):"
    )
    await callback.answer()


@router.message(AdminTakeMoney.amount)
async def admin_take_money_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_plain_amount(message.text or "")
    if amount is None:
        await message.answer(texts.DEPOSIT_WRONG_AMOUNT)
        return
    await state.update_data(amount=amount)
    await state.set_state(AdminTakeMoney.reason)
    await message.answer("📝 Причина (обязательно), например «возврат», «ошибка»:")


@router.message(AdminTakeMoney.reason)
async def admin_take_money_reason(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    reason = (message.text or "").strip()
    label = "⭐" if data["currency"] == "stars" else "₽"
    if data["currency"] == "stars":
        ok = await queries.subtract_stars(data["target"], int(data["amount"]))
    else:
        user = await queries.get_user(data["target"])
        has = user.rubles_balance >= float(data["amount"]) if user else False
        ok = False
        if has:
            ok = await queries.subtract_rubles(data["target"], float(data["amount"]))
    await queries.log_admin(
        message.from_user.id, "Забрать валюту",
        target_user_id=data["target"],
        details=f"-{data['amount']:g}{label} · {reason}",
    )
    await state.clear()
    if not ok:
        await message.answer(
            "❌ Недостаточно средств на балансе пользователя.",
            reply_markup=admin_back_kb(),
        )
        return
    user = await queries.get_user(data["target"])
    balance = f"{user.stars_balance} ⭐" if data["currency"] == "stars" else \
        f"{user.rubles_balance:g} ₽"
    await message.answer(
        f"✅ Списано {data['amount']:g} {label} у пользователя {data['target']}.\n"
        f"Новый баланс: {balance}",
        reply_markup=admin_back_kb(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Информация о пользователе
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:user_info")
async def admin_user_info_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminUserInfo.query)
    await callback.message.edit_text(
        "ℹ️ Введите user_id или @username пользователя:\n"
        "Например: 123456789 или @nickname",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminUserInfo.query)
async def admin_user_info_query(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("@"):
        user = await queries.find_user_by_username(raw)
    else:
        uid = parse_user_input(raw)
        user = await queries.get_user(uid)
    await state.clear()
    if user is None:
        await message.answer("❌ Пользователь не найден.", reply_markup=admin_back_kb())
        return
    numbers = await queries.user_numbers(user.id)
    status = "🚫 заблокирован" if user.is_blocked else "✅ активен"
    lines = [
        "ℹ️ <b>Пользователь</b>\n",
        f"Имя: {user.first_name or '—'}",
        f"Username: {user.username and '@' + user.username or '—'}",
        f"User ID: <code>{user.id}</code>",
        f"Баланс: {user.rubles_balance:g} ₽ · {user.stars_balance} ⭐",
        f"Куплено номеров: {len(numbers)}",
        f"Дата регистрации: {date_format(user.registered_at)}",
        f"Статус: {status}",
        "",
        "<b>Номера:</b>",
    ]
    if numbers:
        for num in numbers:
            lines.append(f"• {num.country_flag or ''}{num.country} — {num.phone_number}")
    else:
        lines.append("— (нет номеров)")
    await message.answer("\n".join(lines), reply_markup=admin_back_kb())


# ─────────────────────────────────────────────────────────────────────────────
# FAQ
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:faq")
async def cb_admin_faq(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🎫 <b>Управление FAQ</b>", reply_markup=faq_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:faq_add")
async def admin_faq_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminFaqAdd.question)
    await callback.message.edit_text(
        "❓ Введите вопрос:", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminFaqAdd.question)
async def admin_faq_add_question(message: Message, state: FSMContext) -> None:
    await state.update_data(question=message.text.strip())
    await state.set_state(AdminFaqAdd.answer)
    await message.answer("💬 Введите ответ на вопрос:")


@router.message(AdminFaqAdd.answer)
async def admin_faq_add_answer(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    items = await queries.add_faq(data.get("question", ""), message.text.strip())
    await queries.log_admin(
        message.from_user.id, "Добавить FAQ",
        details=data.get("question", "")[:100],
    )
    await state.clear()
    await message.answer(
        f"✅ Вопрос добавлен. Всего в FAQ: {len(items)}.",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:faq_view")
async def admin_faq_view(callback: CallbackQuery) -> None:
    items = await queries.get_faq()
    await callback.message.edit_text(
        texts.faq_text(items), reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:faq_del")
async def admin_faq_delete_list(callback: CallbackQuery) -> None:
    items = await queries.get_faq()
    if not items:
        await callback.message.edit_text(
            "❓ FAQ пуст.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "🗑 Выберите вопрос для удаления:",
        reply_markup=faq_delete_kb(list(enumerate(items, 1))),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:faq_del1:"))
async def admin_faq_delete_confirm(callback: CallbackQuery) -> None:
    idx = int(callback.data.partition("admin:faq_del1:")[2])
    await queries.delete_faq(idx)
    await queries.log_admin(callback.from_user.id, "Удалить FAQ", details=f"#{idx}")
    await callback.message.edit_text(
        "✅ Вопрос удалён.", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "admin:faq_reset")
async def admin_faq_reset(callback: CallbackQuery) -> None:
    await queries.reset_faq()
    await queries.log_admin(callback.from_user.id, "Сброс FAQ")
    await callback.message.edit_text(
        "🔄 FAQ сброшен к стандартному.", reply_markup=admin_back_kb()
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Владельцы
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:owners")
async def cb_admin_owners(callback: CallbackQuery) -> None:
    await callback.message.edit_text("👑 <b>Управление владельцами</b>", reply_markup=owners_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:o_list")
async def admin_owners_list(callback: CallbackQuery) -> None:
    owners = await queries.get_owners_list()
    text = "👑 <b>Владельцы:</b>\n" + "\n".join(f"• @{o}" for o in owners)
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:o_add")
async def admin_owner_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminOwnerAdd.username)
    await callback.message.edit_text(
        "👑 Введите username владельца (без @):", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminOwnerAdd.username)
async def admin_owner_add(message: Message, state: FSMContext) -> None:
    ok = await queries.add_owner(message.text or "")
    await state.clear()
    if not ok:
        await message.answer(
            "❌ Этот владелец уже в списке или имя пустое.", reply_markup=admin_back_kb()
        )
        return
    await queries.log_admin(
        message.from_user.id, "Добавить владельца", details=message.text
    )
    await message.answer(
        f"✅ Владелец @{message.text.strip().lstrip('@')} добавлен.",
        reply_markup=admin_back_kb(),
    )


@router.callback_query(F.data == "admin:o_del")
async def admin_owner_del_start(callback: CallbackQuery, state: FSMContext) -> None:
    owners = await queries.get_owners_list()
    rows = [[InlineKeyboardButton(
        text=f"🗑 @{o}", callback_data=f"admin:o_del1:{o}"
    )] for o in owners]
    rows.append([InlineKeyboardButton(text="🔐 К панели", callback_data="admin:panel")])
    await callback.message.edit_text(
        "👑 Выберите владельца для удаления (из .env удалить нельзя):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:o_del1:"))
async def admin_owner_del_confirm(callback: CallbackQuery) -> None:
    uname = callback.data.partition("admin:o_del1:")[2]
    ok = await queries.remove_owner(uname)
    await queries.log_admin(callback.from_user.id, "Удалить владельца", details=uname)
    if not ok:
        await callback.message.edit_text(
            "❌ Нельзя удалить владельца из .env, либо его нет в БД-списке.",
            reply_markup=admin_back_kb(),
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"✅ Владелец @{uname} удалён.", reply_markup=admin_back_kb()
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Баги
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:bugs")
async def cb_admin_bugs(callback: CallbackQuery) -> None:
    await callback.message.edit_text("🔧 <b>Лог багов</b>", reply_markup=bugs_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:b_list")
async def admin_bugs_list(callback: CallbackQuery) -> None:
    bugs = await queries.bug_reports()
    if not bugs:
        await callback.message.edit_text(
            "🐞 Баг-репортов нет.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    lines = ["🔧 <b>Баг-репорты</b>\n"]
    for b in bugs[:50]:
        who = str(b.user_id)
        u = await queries.get_user(b.user_id)
        if u and u.username:
            who = f"@{u.username}"
        lines.append(
            f"#{b.id} · {who} [{date_format(b.created_at)}]\n"
            f"   {b.text[:200]}\n"
        )
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=bug_delete_kb(bugs)
    )
    await callback.answer()


@router.callback_query(F.data == "admin:b_add")
async def admin_bug_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBugAdd.text)
    await callback.message.edit_text(
        "🐞 Опишите баг (текст):", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminBugAdd.text)
async def admin_bug_add(message: Message, state: FSMContext) -> None:
    bug = await queries.add_bug(message.from_user.id, message.text.strip())
    await state.clear()
    await queries.log_admin(message.from_user.id, "Добавить баг", details=f"#{bug.id}")
    await message.answer(
        f"✅ Баг #{bug.id} записан.", reply_markup=admin_back_kb()
    )


@router.callback_query(F.data.startswith("admin:b_del1:"))
async def admin_bug_delete(callback: CallbackQuery) -> None:
    bid = int(callback.data.partition("admin:b_del1:")[2])
    await queries.delete_bug(bid)
    await queries.log_admin(callback.from_user.id, "Удалить баг", details=f"#{bid}")
    await callback.message.edit_text(
        "✅ Баг удалён.", reply_markup=admin_back_kb()
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Настройки
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:settings")
async def cb_admin_settings(callback: CallbackQuery) -> None:
    keys = list(queries.EDITABLE_SETTINGS.keys())
    await callback.message.edit_text(
        "⚙️ <b>Настройки</b>\n\nВыберите параметр для изменения:",
        reply_markup=settings_kb(keys),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:set:"))
async def admin_settings_edit_start(
    callback: CallbackQuery, state: FSMContext
) -> None:
    key = callback.data.partition("admin:set:")[2]
    current = await queries.get_setting(key)
    label = queries.EDITABLE_SETTINGS.get(key, key)
    await state.update_data(key=key)
    await state.set_state(AdminSettingsEdit.value)
    await callback.message.edit_text(
        f"⚙️ <b>{label}</b>\n\nТекущее значение:\n<code>{current}</code>\n\n"
        "Введите новое значение:",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminSettingsEdit.value)
async def admin_settings_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    key = data.get("key", "")
    value = (message.text or "").strip()
    await queries.set_setting(key, value)
    await queries.log_admin(
        message.from_user.id, "Изменить настройку", details=f"{key}"
    )
    await state.clear()
    await message.answer(
        f"✅ Настройка <b>{key}</b> обновлена.", reply_markup=admin_back_kb()
    )


# ─────────────────────────────────────────────────────────────────────────────
# SMS
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:sms")
async def cb_admin_sms(callback: CallbackQuery) -> None:
    await callback.message.edit_text("📨 <b>Управление SMS</b>", reply_markup=sms_kb())
    await callback.answer()


@router.callback_query(F.data == "admin:sms_add")
async def admin_sms_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminSmsAdd.user_id)
    await callback.message.edit_text(
        "📨 Введите user_id (или @username) получателя кода:", reply_markup=admin_back_kb()
    )
    await callback.answer()


@router.message(AdminSmsAdd.user_id)
async def admin_sms_add_user(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    user = await queries.get_user(uid)
    if user is None:
        await message.answer("❌ Пользователь не найден.", reply_markup=admin_back_kb())
        await state.clear()
        return
    numbers = await queries.user_numbers(uid)
    if numbers:
        await message.answer(
            f"✅ Пользователь найден. Его номера:\n"
            + "\n".join(f"• {n.phone_number}" for n in numbers)
            + "\n\n📨 Введите номер телефона (или нажмите кнопку):",
            reply_markup=number_choice_kb(numbers, "admin:sms_ph"),
        )
    else:
        await message.answer("📨 Введите номер телефона (с +):")
    await state.update_data(target=uid)
    await state.set_state(AdminSmsAdd.phone)


@router.callback_query(F.data.startswith("admin:sms_ph:"))
async def admin_sms_pick_phone(callback: CallbackQuery, state: FSMContext) -> None:
    nid = int(callback.data.rsplit(":", 1)[1])
    num = await queries.get_number(nid)
    await state.update_data(phone=num.phone_number if num else None)
    await state.set_state(AdminSmsAdd.app)
    if num:
        await callback.message.edit_text(
            f"📱 Телефон: {num.phone_number}\n🛰 Сервис (например Telegram, "
            f"WhatsApp, VK):"
        )
    await callback.answer()


@router.message(AdminSmsAdd.phone)
async def admin_sms_add_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=message.text.strip())
    await state.set_state(AdminSmsAdd.app)
    await message.answer("🛰 Сервис (например Telegram, WhatsApp, VK):")


@router.message(AdminSmsAdd.app)
async def admin_sms_add_app(message: Message, state: FSMContext) -> None:
    await state.update_data(app=message.text.strip() or "Telegram")
    await state.set_state(AdminSmsAdd.code)
    await message.answer("🔑 Введите сам код из SMS:")


@router.message(AdminSmsAdd.code)
async def admin_sms_add_code(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    uid = data.get("target")
    phone = data.get("phone") or ""
    app = data.get("app") or "Telegram"
    code = message.text.strip()
    num = await queries.get_number_by_phone(phone) if phone else None
    sms = await queries.add_sms(
        user_id=uid, phone=phone, app=app, code=code,
        number_id=num.id if num else None,
        added_by=message.from_user.id,
    )
    await queries.log_admin(
        message.from_user.id, "Добавить SMS", details=f"{phone} · {app} · {code}"
    )
    await state.clear()
    await message.answer(
        f"✅ SMS добавлено для #{sms.id} ({phone}, {app}).",
        reply_markup=admin_back_kb(),
    )
    try:
        await message.bot.send_message(
            uid,
            f"📨 Код для {phone} ({app}):\n<code>{code}</code>",
        )
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "admin:sms_list")
async def admin_sms_list(callback: CallbackQuery) -> None:
    rows = await queries.sms_history()
    if not rows:
        await callback.message.edit_text(
            "📨 SMS-история пуста.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    lines = ["📨 <b>История SMS</b>\n"]
    for s in rows[:30]:
        lines.append(f"#{s.id} · {s.phone} · {s.app}: <code>{s.code}</code>")
    await callback.message.edit_text(
        "\n".join(lines), reply_markup=sms_action_kb(rows, "admin:sms_del1")
    )
    await callback.answer()


@router.callback_query(F.data == "admin:sms_del")
async def admin_sms_delete_list(callback: CallbackQuery) -> None:
    rows = await queries.sms_history()
    if not rows:
        await callback.message.edit_text(
            "📨 SMS-история пуста.", reply_markup=admin_back_kb()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        "🗑 Выберите SMS для удаления:",
        reply_markup=sms_action_kb(rows, "admin:sms_del1"),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:sms_del1:"))
async def admin_sms_delete_confirm(callback: CallbackQuery) -> None:
    sid = int(callback.data.partition("admin:sms_del1:")[2])
    await queries.delete_sms(sid)
    await queries.log_admin(callback.from_user.id, "Удалить SMS", details=f"#{sid}")
    await callback.message.edit_text(
        "✅ SMS удалено.", reply_markup=admin_back_kb()
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Статистика
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:stats")
async def cb_admin_stats(callback: CallbackQuery) -> None:
    s = await queries.get_stats()
    text = (
        "📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {s['users']}\n"
        f"📞 Продано номеров: {s['sold']}\n"
        f"📦 Доступно в базе: {s['available']}\n"
        f"🧾 Заказов всего: {s['orders']} (в ожидании: {s['pending']})\n"
        f"⭐ Выручка звёздами: {s['stars_revenue']}\n"
        f"💰 Выручка рублями: {s['rubles_revenue']:g} ₽"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb())
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Рассылка
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBroadcast.text)
    await callback.message.edit_text(
        "📣 Введите текст рассылки для всех пользователей:",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminBroadcast.text)
async def admin_broadcast_text(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ Текст не может быть пустым.")
        return
    await state.update_data(text=text)
    await state.set_state(AdminBroadcast.confirm)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="admin:broadcast_yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="admin:cancel"),
        ]
    ])
    await message.answer(
        f"Предпросмотр:\n\n{text}\n\nОтправить всем пользователям?",
        reply_markup=kb,
    )


@router.callback_query(F.data == "admin:broadcast_yes")
async def admin_broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    text = data.get("text", "")
    await state.clear()
    user_ids = await queries.all_user_ids()
    admin_id = callback.from_user.id
    await callback.message.edit_text(
        f"📣 Отправляю рассылку {len(user_ids)} пользователям…",
    )
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await callback.bot.send_message(uid, text)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        if sent % 20 == 0:
            import asyncio  # noqa: PLC0415

            await asyncio.sleep(0.3)
    await queries.log_admin(
        admin_id, "Рассылка", details=f"получателей: {len(user_ids)}, "
        f"отправлено: {sent}, ошибок: {failed}"
    )
    await callback.message.answer(
        f"✅ Рассылка завершена.\n"
        f"Отправлено: {sent} · Ошибок: {failed}",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


# ─────────────────────────────────────────────────────────────────────────────
# Заблокировать / разблокировать
# ─────────────────────────────────────────────────────────────────────────────
@router.callback_query(F.data == "admin:block")
async def admin_block_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminBlockUser.user_id)
    await callback.message.edit_text(
        "🚫 Введите user_id (или @username) пользователя для блокировки/разблокировки:",
        reply_markup=admin_back_kb(),
    )
    await callback.answer()


@router.message(AdminBlockUser.user_id)
async def admin_block_userid(message: Message, state: FSMContext) -> None:
    err, uid = await _resolve_target(message.text or "")
    if err:
        await message.answer(err)
        return
    user = await queries.get_user(uid)
    await state.clear()
    if user is None:
        await message.answer("❌ Пользователь не найден.", reply_markup=admin_back_kb())
        return
    new_status = not user.is_blocked
    await queries.set_user_blocked(uid, new_status)
    await queries.log_admin(
        message.from_user.id,
        "Заблокировать" if new_status else "Разблокировать",
        target_user_id=uid,
    )
    await message.answer(
        f"🚫 Пользователь {uid} {'заблокирован' if new_status else 'разблокирован'}.",
        reply_markup=admin_back_kb(),
    )