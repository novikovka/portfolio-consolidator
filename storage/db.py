"""Подключение к PostgreSQL и применение схемы.

Это единственное место, которое знает, как открыть соединение с базой.
Остальной код хранилища (шаг 1.4) будет получать соединение через connect().
"""

from pathlib import Path

import psycopg

from config import get_settings

# Путь к файлу со схемой: <корень проекта>/db/schema.sql
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"

# Сколько секунд ждать ответа базы, прежде чем сообщить об ошибке
CONNECT_TIMEOUT_SECONDS = 3


class DatabaseUnavailable(Exception):
    """База недоступна. Текст исключения — понятное объяснение, что делать."""


def connect() -> psycopg.Connection:
    """Открывает соединение с базой по настройкам из .env.

    При ошибке выбрасывает DatabaseUnavailable с подсказкой на русском.
    """
    settings = get_settings()
    try:
        return psycopg.connect(
            host=settings.db_host,
            port=settings.db_port,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except psycopg.OperationalError as error:
        raise DatabaseUnavailable(_explain(error)) from error


def apply_schema() -> None:
    """Создаёт таблицы, которых ещё нет. Безопасно запускать много раз."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connect() as conn:
        conn.execute(sql)


def list_tables() -> list[str]:
    """Возвращает имена таблиц приложения — для проверки, что схема на месте."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
    return [row[0] for row in rows]


def _explain(error: psycopg.OperationalError) -> str:
    """Превращает техническую ошибку подключения в понятную подсказку."""
    text = str(error).lower()
    settings = get_settings()

    if "password authentication failed" in text:
        return (
            "Неверный пароль к базе данных. Проверьте DB_PASSWORD в файле .env. "
            "Если пароль меняли после первого запуска базы, пересоздайте её: "
            "docker compose down -v, затем docker compose up -d."
        )
    if "does not exist" in text:
        return (
            f"База «{settings.db_name}» или пользователь «{settings.db_user}» не найдены. "
            "Проверьте DB_NAME и DB_USER в файле .env."
        )
    if "refused" in text or "timeout" in text or "could not connect" in text:
        return (
            f"База данных не отвечает ({settings.db_host}:{settings.db_port}). "
            "Запустите Docker Desktop и выполните в папке проекта: docker compose up -d"
        )
    return f"Не удалось подключиться к базе данных: {error}"
