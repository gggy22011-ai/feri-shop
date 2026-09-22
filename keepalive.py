"""
Keepalive-пингер для бесплатного хостинга (Render/Koyeb).

Бесплатные инстансы «засыпают» без входящих запросов. Этот скрипт каждые
N минут дёргает URL (например /healthz бота) — инстанс не спит, бот
поллингует круглосуточно.

Запуск:
    python keepalive.py --url https://<ваш>.onrender.com/healthz --interval 5

Можно повесить в любое всегда-онлайн место: у себя на ПК, на втором VPS,
в Cron GitHub Actions и т.п. Альтернатива без своего кода — бесплатный
монитор UptimeRobot (интервал 5 минут).
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.request


def ping(url: str) -> int | None:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            # читаем тело, чтобы соединение реально закрылось
            resp.read(resp.length or 1024)
            return resp.status
    except Exception as exc:  # noqa: BLE001
        print(f"[{time.strftime('%H:%M:%S')}] ПИНГ ОШИБКА {url}: {exc}", flush=True)
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Keepalive-пингер бота")
    parser.add_argument("--url", required=True, help="URL эндпоинта, например .../healthz")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="интервал в минутах (по умолчанию 5)")
    parser.add_argument("--once", action="store_true", help="пингнуть один раз и выйти")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    interval = max(0.5, args.interval)
    print(f"✓ Keepalive запущен: {url} каждые {interval:g} мин. Ctrl+C — выход.")

    while True:
        status = ping(url)
        if status is not None:
            print(f"[{time.strftime('%H:%M:%S')}] ПИНГ {url} → {status}", flush=True)
        if args.once:
            break
        time.sleep(interval * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)