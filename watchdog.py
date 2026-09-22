"""
Ватчдог: держит bot.py живым 24/7.

Запуск: pythonw watchdog.py  (не создаёт окно консоли)
Ведёт логи в logs/watcher.log, логи бота — в logs/bot.log.
Если процесс бота упал — перезапускает. После серии частых падений
увеличивает паузу, чтобы не долбить Telegram.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
import time

WORKDIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(WORKDIR, ".venv", "Scripts", "python.exe")
BOT = os.path.join(WORKDIR, "bot.py")
LOGS_DIR = os.path.join(WORKDIR, "logs")
WATCH_LOG = os.path.join(LOGS_DIR, "watcher.log")
BOT_LOG = os.path.join(LOGS_DIR, "bot.log")

# Если бот упал быстрее этого времени (сек) — считаем «краш-панч» и копим паузу
SHORT_RUN = 20.0
MIN_DELAY = 5.0          # базовая пауза после падения
MAX_DELAY = 300.0        # потолок паузы при непрерывных падениях
CRASH_TOLERANCE = 3      # сколько подряд коротких падений до увеличения паузы


def log(msg: str) -> None:
    os.makedirs(LOGS_DIR, exist_ok=True)
    line = f"{datetime.datetime.now().isoformat(sep=' ', timespec='seconds')} | {msg}\n"
    with open(WATCH_LOG, "a", encoding="utf-8") as fh:
        fh.write(line)
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass


def ensure_single_instance() -> bool:
    """Не даём запустить несколько ватчдогов (pid-файл + проверка живости)."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    pid_file = os.path.join(LOGS_DIR, "watcher.pid")

    def pid_alive(pid: int) -> bool:
        try:
            r = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in r.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0].lower().endswith(".exe") and parts[1] == str(pid):
                    return True
            return False
        except Exception:  # noqa: BLE001
            return True  # не смогли проверить — не рискуем запускать дубль

    try:
        if os.path.exists(pid_file):
            old = int(open(pid_file, encoding="utf-8").read().strip() or 0)
            if old > 0 and old != os.getpid() and pid_alive(old):
                log(f"WATCHDOG: уже работает (pid {old}) — дубль выходит")
                return False
        with open(pid_file, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except Exception as exc:  # noqa: BLE001
        log(f"WATCHDOG: предупреждение pidfile: {exc}")
    return True


def run_bot() -> subprocess.Popen:
    log(f"Стартую бота: {PYTHON} {BOT}")
    os.makedirs(LOGS_DIR, exist_ok=True)
    out = open(BOT_LOG, "ab", buffering=0)
    proc = subprocess.Popen(
        [PYTHON, BOT],
        cwd=WORKDIR,
        stdout=out,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return proc, out


def main() -> None:
    if not ensure_single_instance():
        return
    log("WATCHDOG: запущен (24/7 supervisor)")
    delay = MIN_DELAY
    crashes = 0
    proc = None
    out = None

    while True:
        if proc is not None and proc.poll() is not None:
            code = proc.returncode
            alive = time.time() - started_at
            log(f"Бот завершился (код {code}) после {alive:.0f}с")
            if alive < SHORT_RUN:
                crashes += 1
            else:
                crashes = 0
            if crashes >= CRASH_TOLERANCE:
                delay = min(delay * 2, MAX_DELAY)
                log(f"Серия из {crashes} падений — пауза {delay:.0f}с")
            else:
                delay = MIN_DELAY
            if out is not None:
                try:
                    out.close()
                except Exception:  # noqa: BLE001
                    pass
            log(f"Перезапуск через {delay:.0f}с…")
            time.sleep(delay)
            proc, out = run_bot()
            started_at = time.time()
            continue

        # первичный запуск
        if proc is None:
            proc, out = run_bot()
            started_at = time.time()

        time.sleep(5)


if __name__ == "__main__":
    main()