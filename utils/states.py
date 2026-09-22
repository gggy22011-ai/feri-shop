"""
FSM-состояния магазина Feris Shop.
Все пошаговые сценарии (ввод денег, админские формы и т.п.).
"""
from aiogram.filters.state import State, StatesGroup


class AdminAuth(StatesGroup):
    """Вход в админку по паролю."""
    waiting_password = State()


class DepositAmount(StatesGroup):
    """Ввод суммы пополнения в рублях (сразу после «Пополнить баланс»)."""
    amount = State()


class DonateAmount(StatesGroup):
    """Ввод своей суммы доната в звёздах."""
    amount = State()


class BugReportText(StatesGroup):
    """Текст баг-репорта от пользователя."""
    text = State()


class AdminIssueNumber(StatesGroup):
    """Выдать номер пользователю."""
    user_id = State()
    country = State()
    phone = State()
    operator = State()


class AdminGiveMoney(StatesGroup):
    """Выдать валюту (рубли)."""
    user_id = State()
    amount = State()
    reason = State()


class AdminTakeMoney(StatesGroup):
    """Забрать валюту (рубли)."""
    user_id = State()
    amount = State()
    reason = State()


class AdminUserInfo(StatesGroup):
    """Информация о пользователе."""
    query = State()


class AdminTakeNumber(StatesGroup):
    """Забрать номер у пользователя."""
    user_id = State()
    phone = State()


class AdminAddNumbers(StatesGroup):
    """Массовое добавление номеров в базу."""
    form = State()


class AdminListNumbersFilter(StatesGroup):
    """Фильтр списка доступных номеров."""
    country = State()


class AdminDeleteNumber(StatesGroup):
    """Удалить номер из базы."""
    phone = State()


class AdminBroadcast(StatesGroup):
    """Рассылка: текст, затем подтверждение."""
    text = State()
    confirm = State()


class AdminBlockUser(StatesGroup):
    """Заблокировать / разблокировать пользователя."""
    user_id = State()


class AdminCountryAdd(StatesGroup):
    """Добавить страну (название → флаг/цена)."""
    name = State()
    price = State()


class AdminCountryPrice(StatesGroup):
    """Изменить цену выбранной страны."""
    name = State()
    price = State()


class AdminFaqAdd(StatesGroup):
    """Добавить вопрос в FAQ."""
    question = State()
    answer = State()


class AdminOwnerAdd(StatesGroup):
    username = State()


class AdminOwnerDel(StatesGroup):
    username = State()


class AdminBugAdd(StatesGroup):
    text = State()


class AdminSettingsEdit(StatesGroup):
    """Изменить настройку: key → value."""
    key = State()
    value = State()


class AdminSmsAdd(StatesGroup):
    """Добавить SMS-код: user_id → телефон → сервис → код."""
    user_id = State()
    phone = State()
    app = State()
    code = State()