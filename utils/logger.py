"""
Логирование магазина Feri_shop: консоль + ротируемый файл logs/bot.log.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

import config

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def setup_logger() -> logging.Logger:
    """Настраивает корневой логгер один раз и возвращает его."""
    global _configured
    logger = logging.getLogger()
    if _configured:
        return logger
    _configured = True

    logger.setLevel(config.log_level_int())
    formatter = logging.Formatter(_LOG_FORMAT)

    # Консоль
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    # Файл
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    file_handler = RotatingFileHandler(
        os.path.join(config.LOGS_DIR, "bot.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "feri_shop") -> logging.Logger:
    """Получить логгер для конкретного модуля."""
    return logging.getLogger(name)