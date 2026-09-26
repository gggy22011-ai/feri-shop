"""
РђРІС‚РѕРІС‹РґР°С‡Р° СЂРµР°Р»СЊРЅС‹С… РЅРѕРјРµСЂРѕРІ Рё РїСЂРёС‘Рј SMS-РєРѕРґРѕРІ.

РџРѕРґРґРµСЂР¶РёРІР°СЋС‚СЃСЏ РїСЂРѕРІР°Р№РґРµСЂС‹ РїСЂРёС‘РјР° SMS (РїРµСЂРµРєР»СЋС‡Р°СЋС‚СЃСЏ РІ config.SMS_PROVIDER):
  * "sms-activate" вЂ” https://api.sms-activate.ae (РєР»СЋС‡ SMS_ACTIVATE_KEY)
  * "5sim"         вЂ” https://api.5sim.net      (РєР»СЋС‡ FIVESIM_KEY)
  * "test"         вЂ” С„РµР№РєРѕРІС‹Р№ РїСЂРѕРІР°Р№РґРµСЂ Р±РµР· РґРµРЅРµРі Рё СЃРµС‚Рё, РґР»СЏ Р»РѕРєР°Р»СЊРЅРѕР№ РїСЂРѕРІРµСЂРєРё С„Р»РѕСѓ

РџСѓР±Р»РёС‡РЅС‹Р№ API РјРѕРґСѓР»СЏ:
    provider = get_provider()
    act = await provider.issue(country_code)   # -> Activation
    code = await provider.wait_code(act, timeout=...)  # -> str | None
    await provider.cancel(act)                 # РѕС‚РјРµРЅР° Р°РєС‚РёРІР°С†РёРё (РґРµРЅСЊРіРё РЅРµ СЃРіРѕСЂР°СЋС‚)

Р’СЃРµ СЃРµС‚РµРІС‹Рµ РІС‹Р·РѕРІС‹ вЂ” РЅР° СѓР¶Рµ СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅРѕРј aiohttp, РЅРѕРІС‹С… Р·Р°РІРёСЃРёРјРѕСЃС‚РµР№ РЅРµС‚.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

import config
from utils.logger import get_logger

logger = get_logger("sms_api")

SMS_ACTIVATE_URL = "https://api.sms-activate.ae/stubs/handler_api.php"
FIVESIM_URL = "https://api.5sim.net"

WAIT_CODE = "wait"
DONE = "done"
EXPIRED = "expired"
CANCELED = "canceled"
TIMEOUT = "timeout"


class SmsError(RuntimeError):
    """РћС€РёР±РєР° РїСЂРѕРІР°Р№РґРµСЂР°: РЅРµС‚ РґРµРЅРµРі, РЅРµС‚ СЃРІРѕР±РѕРґРЅС‹С… РЅРѕРјРµСЂРѕРІ, РЅРµРІРµСЂРЅС‹Р№ РєР»СЋС‡."""


@dataclass
class Activation:
    """Р—Р°РєСѓРїР»РµРЅРЅР°СЏ Р°РєС‚РёРІР°С†РёСЏ: РїСЂРѕРІР°Р№РґРµСЂ, РµС‘ id, СЂРµР°Р»СЊРЅС‹Р№ РЅРѕРјРµСЂ, С†РµРЅР°."""

    provider: str
    activation_id: str
    phone: str
    country: str = ""
    service: str = ""
    cost: float = 0.0
    created_at: float = field(default_factory=time.time)

    @property
    def normalized_phone(self) -> str:
        """РќРѕРјРµСЂ РІ РІРёРґРµ +79XXXXXXXXX (РєР°Рє РїРѕРєР°Р·С‹РІР°РµРј СЋР·РµСЂСѓ)."""
        digits = re.sub(r"\D", "", self.phone or "")
        if not digits:
            return self.phone or ""
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        return "+" + digits


def extract_code(text: str) -> str:
    """Р”РѕСЃС‚Р°С‘С‚ РєРѕРґ РёР· С‚РµРєСЃС‚Р° SMS: 'Your code is 12345' -> '12345'."""
    if not text:
        return ""
    if text.isdigit() and 4 <= len(text) <= 8:
        return text
    # РџСЂРµРґРїРѕС‡РёС‚Р°РµРј СЃР°РјС‹Рµ РґР»РёРЅРЅС‹Рµ С‡РёСЃР»Р° (4вЂ“8 С†РёС„СЂ) вЂ” СЌС‚Рѕ Рё РµСЃС‚СЊ РєРѕРґ.
    candidates = re.findall(r"\d{4,8}", text)
    if not candidates:
        candidates = re.findall(r"\d+", text)
    if not candidates:
        return ""
    return max(candidates, key=len)


def provider_country(country: str | None) -> str:
    """РЎС‚СЂР°РЅР° РёР· РІРёС‚СЂРёРЅС‹ -> РєРѕРґ СЃС‚СЂР°РЅС‹ Сѓ РїСЂРѕРІР°Р№РґРµСЂР° (С‡РµСЂРµР· SMS_COUNTRY_MAP)."""
    key = (country or "").strip().lower()
    return config.SMS_COUNTRY_MAP.get(key, config.SMS_COUNTRY_DEFAULT)


def is_ready() -> bool:
    """Р“РѕС‚РѕРІР° Р»Рё Р°РІС‚РѕРІС‹РґР°С‡Р° (РїСЂРѕРІР°Р№РґРµСЂ РІС‹Р±СЂР°РЅ, РєР»СЋС‡ РµСЃС‚СЊ)."""
    return config.sms_provider_ready()


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Р‘Р°Р·РѕРІС‹Р№ РєР»Р°СЃСЃ
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
class BaseProvider:
    name = "base"

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None

    async def session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=config.SMS_HTTP_TIMEOUT)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def balance(self) -> float:
        raise NotImplementedError

    async def issue(self, country: str, service: str | None = None) -> Activation:
        raise NotImplementedError

    async def poll_code(self, act: Activation) -> tuple[str, str]:
        """Р’РѕР·РІСЂР°С‰Р°РµС‚ (СЃС‚Р°С‚СѓСЃ, РєРѕРґ): СЃС‚Р°С‚СѓСЃ РёР· WAIT_CODE/DONE/EXPIRED/CANCELED."""
        raise NotImplementedError

    async def cancel(self, act: Activation) -> bool:
        raise NotImplementedError

    async def wait_code(self, act: Activation, timeout_s: int) -> tuple[str, str]:
        """РћРїСЂР°С€РёРІР°РµС‚ СЃРµСЂРІРёСЃ РґРѕ РїРѕР»СѓС‡РµРЅРёСЏ РєРѕРґР°. Р’РѕР·РІСЂР°С‰Р°РµС‚ (СЃС‚Р°С‚СѓСЃ, РєРѕРґ)."""
        deadline = time.monotonic() + timeout_s
        while True:
            status, code = await self.poll_code(act)
            if status != WAIT_CODE:
                return status, code
            if time.monotonic() >= deadline:
                return TIMEOUT, ""
            await asyncio.sleep(5)

    async def _get_json(self, url: str, **kwargs: Any) -> Any:
        sess = await self.session()
        async with sess.get(url, **kwargs) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise SmsError(f"HTTP {resp.status}: {text[:200]}")
            return text


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# sms-activate
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
class SmsActivateProvider(BaseProvider):
    name = "sms-activate"
    url = SMS_ACTIVATE_URL

    _ERR = {
        "no_balance": "РќР° Р±Р°Р»Р°РЅСЃРµ СЃРµСЂРІРёСЃР° РЅРµС‚ РґРµРЅРµРі",
        "no_numbers": "РќРµС‚ СЃРІРѕР±РѕРґРЅС‹С… РЅРѕРјРµСЂРѕРІ РїРѕРґ СЌС‚РѕС‚ СЃРµСЂРІРёСЃ/СЃС‚СЂР°РЅСѓ",
        "bad_key": "РќРµРІРµСЂРЅС‹Р№ API-РєР»СЋС‡ sms-activate",
        "bad_service": "РќРµРІРµСЂРЅС‹Р№ РєРѕРґ СЃРµСЂРІРёСЃР° (SMS_SERVICE)",
        "bad_country": "РќРµРІРµСЂРЅС‹Р№ РєРѕРґ СЃС‚СЂР°РЅС‹ (SMS_COUNTRY_MAP)",
        "no_activation": "РђРєС‚РёРІР°С†РёСЏ РЅРµ РЅР°Р№РґРµРЅР° Сѓ СЃРµСЂРІРёСЃР°",
    }

    async def _api(self, **params: Any) -> dict:
        params["api_key"] = config.SMS_API_KEY
        raw = await self._get_json(self.url, params={k: v for k, v in params.items() if v is not None})
        try:
            data: dict = await json.loads(raw)
        except ValueError:
            raise SmsError(f"РќРµРѕР¶РёРґР°РЅРЅС‹Р№ РѕС‚РІРµС‚ СЃРµСЂРІРёСЃР°: {raw[:200]}") from None
        if data.get("status") == "error":
            kind = data.get("activate_type") or "unknown"
            raise SmsError(self._ERR.get(kind, f"РћС€РёР±РєР° СЃРµСЂРІРёСЃР°: {kind}"))
        return data

    async def balance(self) -> float:
        data = await self._api(action="getBalance")
        return float(data.get("balance", 0) or 0)

    async def issue(self, country: str, service: str | None = None) -> Activation:
        data = await self._api(
            action="getNumber",
            service=service or config.SMS_SERVICE,
            country=country,
            operator="any",
        )
        act_id = data.get("activation_id")
        phone = data.get("phone")
        if not act_id or not phone:
            raise SmsError(f"РЎРµСЂРІРёСЃ РЅРµ РІРµСЂРЅСѓР» РЅРѕРјРµСЂ: {data}")
        return Activation(
            provider=self.name,
            activation_id=str(act_id),
            phone=str(phone),
            country=str(data.get("country", country)),
            service=service or config.SMS_SERVICE,
            cost=float(data.get("cost", 0) or 0),
        )

    async def poll_code(self, act: Activation) -> tuple[str, str]:
        data = await self._api(action="getStatus", id=act.activation_id)
        status = str(data.get("status", "")).upper()
        if status == "STATUS_WAIT_CODE":
            return WAIT_CODE, ""
        if status == "STATUS_CANCEL":
            return CANCELED, ""
        if status == "STATUS_OK":
            activation = data.get("activation") or {}
            text = activation.get("text") or ""
            code = extract_code(text)
            if not code:
                return WAIT_CODE, ""
            return DONE, code
        if status in ("STATUS_TIMEOUT",):
            return EXPIRED, ""
        return WAIT_CODE, ""

    async def cancel(self, act: Activation) -> bool:
        try:
            await self._api(action="setStatus", id=act.activation_id, status=8)
            return True
        except SmsError as e:
            logger.warning("РќРµ СѓРґР°Р»РѕСЃСЊ РѕС‚РјРµРЅРёС‚СЊ Р°РєС‚РёРІР°С†РёСЋ %s: %s", act.activation_id, e)
            return False


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# 5sim
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
class FiveSimProvider(BaseProvider):
    name = "5sim"

    def _headers(self) -> dict:
        key = config.SMS_API_KEY
        return {"Authorization": f"Bearer {key}", "X-API-KEY": key, "Accept": "application/json"}

    async def _get(self, path: str) -> Any:
        return await self._get_json(FIVESIM_URL + path, headers=self._headers())

    async def _post(self, path: str) -> Any:
        sess = await self.session()
        async with sess.post(FIVESIM_URL + path, headers=self._headers()) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise SmsError(f"HTTP {resp.status}: {text[:200]}")
            return await json.loads(text or "{}")

    async def balance(self) -> float:
        data = await self._get("/v1/user/profile")
        return float(data.get("balance", 0) or 0)

    async def _product_id(self, country: str, service: str | None) -> int:
        # Р’ 5sim РєР°С‚РµРіРѕСЂРёРё РЅР°Р·С‹РІР°СЋС‚СЃСЏ РёРјРµРЅР°РјРё: tg -> Telegram.
        category = "Telegram" if (service or config.SMS_SERVICE).lower() in ("tg", "telegram") else (service or config.SMS_SERVICE)
        data = await self._get(f"/v1/products?category={category}&country={country}")
        products = data.get("products") or []
        if not products:
            raise SmsError(f"РќРµС‚ С‚РѕРІР°СЂРѕРІ Сѓ 5sim: РєР°С‚РµРіРѕСЂРёСЏ={category}, СЃС‚СЂР°РЅР°={country}")
        best = min(products, key=lambda p: float(p.get("price", 0) or 0))
        return int(best["id"])

    async def issue(self, country: str, service: str | None = None) -> Activation:
        pid = await self._product_id(country, service)
        data = await self._post(f"/v1/purchases/activation/{pid}")
        act_id, phone = data.get("id"), data.get("phone")
        if not act_id or not phone:
            raise SmsError(f"5sim РЅРµ РІРµСЂРЅСѓР» РЅРѕРјРµСЂ: {data}")
        return Activation(
            provider=self.name,
            activation_id=str(act_id),
            phone=str(phone),
            country=str(data.get("country", country)),
            service=service or config.SMS_SERVICE,
            cost=float(data.get("price", 0) or 0),
        )

    async def poll_code(self, act: Activation) -> tuple[str, str]:
        data = await self._get(f"/v1/activations/{act.activation_id}")
        status = str(data.get("status", "")).upper()
        if status in ("NEW", "WAIT_CODE", "PENDING"):
            return WAIT_CODE, ""
        if status == "DONE":
            code = extract_code(data.get("code") or "")
            if not code:
                # 5sim РёРЅРѕРіРґР° РѕС‚РґР°С‘С‚ С‚РѕР»СЊРєРѕ С‚РµРєСЃС‚ SMS.
                texts = [s.get("text", "") for s in (data.get("sms") or [])]
                code = extract_code(" ".join(t for t in texts if t))
            return (DONE, code) if code else (WAIT_CODE, "")
        if status in ("TIMEOUT", "EXPIRED"):
            return EXPIRED, ""
        if status in ("ERROR", "CANCEL"):
            return CANCELED, ""
        return WAIT_CODE, ""

    async def cancel(self, act: Activation) -> bool:
        try:
            await self._post(f"/v1/activations/{act.activation_id}/finish")
            return True
        except SmsError as e:
            logger.warning("РќРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РІРµСЂС€РёС‚СЊ Р°РєС‚РёРІР°С†РёСЋ 5sim %s: %s", act.activation_id, e)
            return False


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# РўРµСЃС‚РѕРІС‹Р№ РїСЂРѕРІР°Р№РґРµСЂ: Р±РµР· СЃРµС‚Рё Рё Р±РµР· РґРµРЅРµРі, РґР»СЏ РїСЂРѕРІРµСЂРєРё С„Р»РѕСѓ Р»РѕРєР°Р»СЊРЅРѕ
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
class TestProvider(BaseProvider):
    name = "test"

    # Состояние — модульное: get_provider() создаёт новый инстанс на каждый
    # вызов, а активация должна «жить» между опросами.
    _codes: dict[str, str] = {}
    _issued: list[Activation] = []

    async def balance(self) -> float:
        return 100.0

    async def issue(self, country: str, service: str | None = None) -> Activation:
        idx = len(TestProvider._issued) + 1
        act = Activation(self.name, f"t{idx}", f"+7999{idx:07d}", country, service or config.SMS_SERVICE, 0.5)
        TestProvider._issued.append(act)
        return act

    async def poll_code(self, act: Activation) -> tuple[str, str]:
        # Первый опрос — «ждём», второй — отдаём тестовый код.
        code = TestProvider._codes.get(act.activation_id)
        if code is None:
            TestProvider._codes[act.activation_id] = "12345"
            return WAIT_CODE, ""
        return DONE, code

    async def cancel(self, act: Activation) -> bool:
        TestProvider._codes.pop(act.activation_id, None)
        return True


_PROVIDERS = {
    "sms-activate": SmsActivateProvider,
    "sms_activate": SmsActivateProvider,
    "smsactivate": SmsActivateProvider,
    "5sim": FiveSimProvider,
    "test": TestProvider,
}


def get_provider() -> BaseProvider | None:
    """РџСЂРѕРІР°Р№РґРµСЂ РїРѕ config.SMS_PROVIDER; None вЂ” Р°РІС‚РѕРІС‹РґР°С‡Р° РІС‹РєР»СЋС‡РµРЅР°."""
    name = (config.SMS_PROVIDER or "").strip().lower()
    cls = _PROVIDERS.get(name)
    if cls is None:
        if name:
            logger.warning("РќРµРёР·РІРµСЃС‚РЅС‹Р№ SMS_PROVIDER=%r вЂ” Р°РІС‚РѕРІС‹РґР°С‡Р° РІС‹РєР»СЋС‡РµРЅР°", name)
        return None
    if name != "test" and not config.SMS_API_KEY:
        logger.warning("SMS_PROVIDER=%s, РЅРѕ РєР»СЋС‡ РЅРµ Р·Р°РґР°РЅ вЂ” Р°РІС‚РѕРІС‹РґР°С‡Р° РІС‹РєР»СЋС‡РµРЅР°", name)
        return None
    return cls()

