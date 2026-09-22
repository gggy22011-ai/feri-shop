# Интеграционный тест диспетчера Feris Shop (без сети).
# Мокаем Bot: отправка сообщений/инвойсов логируется в список Log.
import asyncio
import os
import sys
import time
import traceback
from unittest.mock import AsyncMock

if os.name == "nt":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJ = r"C:\Users\Admin\Desktop\feri_shop"
sys.path.insert(0, PROJ)

import config  # noqa: E402

config.BOT_TOKEN = "123456:TESTTEST"
config.DB_URL = "sqlite+aiosqlite:///C:\\Temp\\opencode\\itest.db"
config.ADMIN_IDS = [900]
config.FLOOD_RATE_LIMIT = 0.0
config.OWNER_USERNAMES = ["clulk", "no7777on"]

from aiogram.types import (  # noqa: E402
    CallbackQuery,
    Chat,
    Message,
    PreCheckoutQuery,
    Update,
    User,
)

for f in [r"C:\Temp\opencode\itest.db"]:
    if os.path.exists(f):
        os.remove(f)

Log = []


def mk_user(uid, name="t"):
    return User(id=uid, is_bot=False, first_name=name, username=f"u{uid}")


def mk_msg(uid, text, mid=1):
    return Message(
        message_id=mid,
        date=int(time.time()),
        chat=Chat(id=uid, type="private"),
        from_user=mk_user(uid),
        text=text,
    )


def mk_cb(uid, data, mid=2, user=None):
    return CallbackQuery(
        id=str(mid),
        from_user=user or mk_user(uid),
        chat_instance="0",
        message=mk_msg(uid, "cb", mid),
        data=data,
    )


class FakeBot:
    def __init__(self):
        self.session = AsyncMock()
        self.me = mk_user(0, "Feris_shop")
        self.id = 123456

    async def __call__(self, method):
        name = type(method).__name__
        text = getattr(method, "text", None)
        if name == "SendMessage" or name == "SendInvoice":
            Log.append(("send", getattr(method, "chat_id", None), text, name == "SendInvoice"))
        elif name == "EditMessageText":
            Log.append(("edit", getattr(method, "chat_id", None), text))
        elif name == "AnswerCallbackQuery":
            Log.append(("cb_ans", None, text))
        elif name in ("AnswerPreCheckoutQuery", "RefundStarPayment"):
            Log.append((name.lower(), None, None))
        else:
            Log.append((name.lower(), None, None))
        return True

    async def get_chat(self, chat_id):
        class C:
            title = "test"
            id = -100 if "@" in str(chat_id) else chat_id
        return C()

    async def get_chat_member(self, chat_id, user_id):
        class M:
            status = "member"
        return M()

    async def send_invoice(self, chat_id, title, description, payload,
                           currency, prices, *args, **kwargs):
        Log.append(("send", chat_id, title, True))
        return True

    async def answer_pre_checkout_query(self, *args, **kwargs):
        Log.append(("preck", None, None))
        return True


async def main() -> None:
    from database import init_db, queries
    from database.seed import seed_all
    import bot as botmod

    await init_db()
    await seed_all()

    # стартовые номера (цены в ₽) и балансы
    await queries.add_numbers([
        {"country": "Россия", "country_flag": "🇷🇺", "phone_number": "+79998887766",
         "operator": "МТС", "price_rubles": 149},
        {"country": "Казахстан", "country_flag": "🇰🇿", "phone_number": "+77019990011",
         "operator": None, "price_rubles": 269},
    ])
    await queries.upsert_country("Россия", "🇷🇺", 149)
    await queries.upsert_country("Казахстан", "🇰🇿", 269)
    await queries.get_or_create_user(10, "buyer", "Buyer")
    await queries.add_rubles(10, 500, "Тест")
    await queries.add_stars(10, 500, "Тест")

    fake_bot = FakeBot()
    botmod.bot = fake_bot
    dp = botmod.create_dispatcher()

    async def feed(upd):
        await dp.feed_update(bot=fake_bot, update=upd)
        await asyncio.sleep(0.03)

    def sent(text_part=None):
        return [x for x in Log if x[0] in ("send", "edit") and (text_part is None or (x[2] and text_part in x[2]))]

    owner = User(id=900, is_bot=False, first_name="owner", username="no7777on")

    # 1. /start
    Log.clear()
    await feed(Update(update_id=1, message=mk_msg(10, "/start", 1)))
    print("1 /start greet+menu:", "OK" if sent("Feris Shop") and sent("Главное меню") else f"FAIL {Log[-4:]}")

    # 2. главное меню → купить (список стран)
    Log.clear()
    await feed(Update(update_id=2, callback_query=mk_cb(10, "menu:buy", 2)))
    print("2 countries list:", "OK" if sent("Выберите страну") else f"FAIL {Log[-3:]}")

    # 3. выбор страны → карточка страны
    Log.clear()
    await feed(Update(update_id=3, callback_query=mk_cb(10, "shop:c:🇷🇺|Россия", 3)))
    ok3 = any(x[0] == "edit" and "В наличии" in (x[2] or "") for x in Log)
    print("3 country card:", "OK" if ok3 else f"FAIL {Log[-3:]}")

    # 4. список номеров страны
    Log.clear()
    await feed(Update(update_id=4, callback_query=mk_cb(10, "shop:l:🇷🇺|Россия", 4)))
    ok4 = any(x[0] == "edit" and "79998887766" in (x[2] or "") for x in Log)
    print("4 numbers list:", "OK" if ok4 else f"FAIL {Log[-3:]}")

    # 5. оформить заказ (рублями через @Clulk)
    Log.clear()
    num = (await queries.available_numbers("Россия"))[0]
    await feed(Update(update_id=5, callback_query=mk_cb(10, f"shop:buy:{num.id}", 5)))
    order = await queries.pending_buy_order(10, num.id)
    ok5 = order is not None and any(x[0] == "edit" and "ОПЛАТА НОМЕРА" in (x[2] or "") for x in Log)
    print("5 buy order screen:", "OK" if ok5 else f"FAIL {Log[-3:]}")

    # 6. оплата с ₽-баланса
    Log.clear()
    await feed(Update(update_id=6, callback_query=mk_cb(10, f"shop:pay:{order.id}:rub", 6)))
    ok6 = any("Номер" in (x[2] or "") and "ваш" in (x[2] or "") for x in Log)
    owned1 = await queries.user_numbers(10)
    print("6 pay from rub balance:", "OK" if ok6 and len(owned1) == 1 else f"FAIL {Log[-4:]}")

    # 7. доп.номер → заказ → оплата звёздами с баланса
    Log.clear()
    kz = (await queries.available_numbers("Казахстан"))[0]
    await feed(Update(update_id=7, callback_query=mk_cb(10, f"shop:buy:{kz.id}", 7)))
    order2 = await queries.pending_buy_order(10, kz.id)
    Log.clear()
    await feed(Update(update_id=8, callback_query=mk_cb(10, f"shop:pay:{order2.id}:stars", 8)))
    ok7 = any("Номер" in (x[2] or "") and "ваш" in (x[2] or "") for x in Log)
    owned2 = await queries.user_numbers(10)
    print("7 pay from stars balance:", "OK" if ok7 and len(owned2) == 2 else f"FAIL {Log[-4:]}")

    # 8. пополнение: сразу ввод суммы (рубли) → заявка → админ подтверждает
    Log.clear()
    await feed(Update(update_id=9, callback_query=mk_cb(10, "menu:deposit", 9)))
    await feed(Update(update_id=10, message=mk_msg(10, "300", 10)))
    dep = (await queries.user_orders(10))[0]
    ok8a = dep.kind == "deposit" and dep.status == "pending" and \
        any("Выберите способ оплаты" in (x[2] or "") for x in Log)
    user_before = await queries.get_user(10)
    confirmed = await queries.confirm_order(dep.id, 900)
    user_after = await queries.get_user(10)
    ok8b = confirmed is not None and user_after.rubles_balance == round(user_before.rubles_balance + 300, 2)
    print("8 rub deposit (amount input) + admin confirm:", f"{'OK' if ok8a else 'FAIL'} {'OK' if ok8b else 'FAIL'}")

    # 8b. пополнение звёздами с баланса (мгновенно, без инвойса)
    Log.clear()
    await feed(Update(update_id=18, callback_query=mk_cb(10, "menu:deposit", 18)))
    await feed(Update(update_id=19, message=mk_msg(10, "50", 19)))
    dep2 = (await queries.user_orders(10))[0]
    stars_before = (await queries.get_user(10)).stars_balance
    rub_before = (await queries.get_user(10)).rubles_balance
    status, paid2, need = await queries.pay_deposit_with_stars(dep2.id)
    u = await queries.get_user(10)
    ok8c = status == "ok" and paid2 is not None and need > 0 and \
        u.stars_balance == stars_before - need and \
        u.rubles_balance == round(rub_before + 50, 2)
    print("8b deposit with stars from balance:", "OK" if ok8c else f"FAIL {status} {need}")

    # 9. админка: заказы (должно быть пусто), статистика, профиль
    Log.clear()
    await feed(Update(update_id=11, message=(lambda m: m)(mk_msg(0, "/admin", 11)).model_copy(update={"from_user": owner})))
    ok9 = any("Панель администратора" in (x[2] or "") for x in Log)
    Log.clear()
    await feed(Update(update_id=12, callback_query=mk_cb(90, "admin:orders", 12, user=owner)))
    ok9b = any("Ожидающих оплаты заказов нет" in (x[2] or "") for x in Log)
    Log.clear()
    await feed(Update(update_id=13, callback_query=mk_cb(90, "admin:stats", 13, user=owner)))
    ok9c = any("Продано номеров" in (x[2] or "") for x in Log)
    print("9 admin entry+orders+stats:", f"{'OK' if ok9 else 'FAIL'} {'OK' if ok9b else 'FAIL'} {'OK' if ok9c else 'FAIL'}")

    # 10. не-админ admin: колбэк блокируется
    Log.clear()
    await feed(Update(update_id=14, callback_query=mk_cb(10, "admin:stats", 14)))
    blocked = any(x[0] == "cb_ans" for x in Log)
    print("10 non-admin blocked:", "OK" if blocked else f"FAIL {Log[-3:]}")

    # 11. профиль: ₽ и ⭐ балансы, реферальная ссылка
    Log.clear()
    await feed(Update(update_id=15, callback_query=mk_cb(10, "menu:profile", 15)))
    ok11 = len(sent("Баланс")) > 0 and "https://t.me/" in "\n".join((x[2] or "") for x in Log)
    print("11 profile with balances+ref:", "OK" if ok11 else f"FAIL {Log[-3:]}")

    # 12. мои номера + копирование
    Log.clear()
    await feed(Update(update_id=16, callback_query=mk_cb(10, "menu:nums", 16)))
    ok12 = any(x[0] == "edit" and "79998887766" in (x[2] or "") for x in Log)
    owned = {n.id: n.phone_number for n in await queries.user_numbers(10)}
    Log.clear()
    await feed(Update(update_id=17, callback_query=mk_cb(10, f"copy:{next(iter(owned))}", 17)))
    ok12b = any(owned.get(next(iter(owned))) in (x[2] or "") for x in Log)
    print("12 my numbers + copy:", f"{'OK' if ok12 else 'FAIL'} {'OK' if ok12b else 'FAIL'}")

    # 13. админ: список багов открывается (раньше падал — у BugReport нет username)
    await queries.add_bug(10, "Тестовый баг для списка")
    Log.clear()
    await feed(Update(update_id=20, callback_query=mk_cb(90, "admin:b_list", 20, user=owner)))
    ok13 = any("Баг-репорты" in (x[2] or "") for x in Log)
    print("13 admin bug list opens:", "OK" if ok13 else f"FAIL {Log[-3:]}")

    # 14. выдача валюты по @username (раньше требовал только числовой id)
    Log.clear()
    def m_owner(text, mid):
        return Message(
            message_id=mid,
            date=int(time.time()),
            chat=Chat(id=900, type="private"),
            from_user=owner,
            text=text,
        )
    await feed(Update(update_id=21, callback_query=mk_cb(900, "admin:give_money", 21, user=owner)))
    nick = (await queries.get_user(10)).username
    await feed(Update(update_id=22, message=m_owner(nick, 22)))
    await feed(Update(update_id=23, message=m_owner("100", 23)))
    await feed(Update(update_id=24, message=m_owner("—", 24)))
    u = await queries.get_user(10)
    ok14 = u is not None and u.rubles_balance > 701
    if not ok14:
        print("14 LOG:", Log[-8:])
    print("14 give money by @username:", "OK" if ok14 else f"FAIL {u.rubles_balance if u else None}")

    print("DONE")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        raise