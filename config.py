"""Настройки приложения.

Все параметры читаются из файла .env в корне проекта, чтобы пароли
не попадали в код и в GitHub. Остальные модули берут настройки только
отсюда, через get_settings().
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

# Подхватываем переменные из .env (если файла нет — используются значения по умолчанию).
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Параметры подключения к базе данных."""

    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str


def get_settings() -> Settings:
    """Собирает настройки из переменных окружения."""
    return Settings(
        db_host=os.getenv("DB_HOST", "localhost"),
        db_port=int(os.getenv("DB_PORT", "5432")),
        db_name=os.getenv("DB_NAME", "portfolio"),
        db_user=os.getenv("DB_USER", "portfolio_app"),
        db_password=os.getenv("DB_PASSWORD", ""),
    )
