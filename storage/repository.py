"""Интерфейс хранилища: что умеет хранилище, без привязки к конкретной базе.

Фасад (services/portfolio_service.py) работает только с этим интерфейсом.
Поэтому в тестах вместо PostgreSQL можно подставить хранилище в памяти,
а в будущем — заменить базу, не трогая остальной код.
"""

from decimal import Decimal
from typing import Protocol

from core.models import Account, Instrument, Operation, Quote


class Repository(Protocol):
    """Набор действий с данными, которые нужны приложению."""

    # Счета
    def list_accounts(self) -> list[Account]:
        """Все счета в порядке создания."""

    def add_account(self, name: str, broker: str, account_type: str = "broker") -> Account:
        """Создаёт счёт и возвращает его с присвоенным номером."""

    def update_account(self, account: Account) -> None:
        """Переименовывает счёт / меняет брокера и тип."""

    def delete_account(self, account_id: int) -> None:
        """Удаляет счёт (фасад разрешает это только для счёта без операций)."""

    # Справочник бумаг
    def ensure_security(self, ticker: str) -> None:
        """Добавляет тикер в справочник, если его там ещё нет."""

    def list_securities(self) -> list[Instrument]:
        """Все бумаги справочника (у части могут быть не заполнены название и режим торгов)."""

    def update_security(self, instrument: Instrument) -> None:
        """Записывает название, ISIN, режим торгов и класс актива для тикера (сектор не трогает)."""

    def set_sector(self, ticker: str, sector: str | None) -> None:
        """Сектор бумаги (None — «не указан»)."""

    # Цены
    def save_quotes(self, quotes: list[Quote]) -> None:
        """Сохраняет цены в кэш. Повтор той же цены на то же время не дублируется."""

    def latest_quotes(self, tickers: list[str]) -> dict[str, Quote]:
        """Последняя сохранённая цена по каждому тикеру."""

    # Настройки
    def get_setting(self, key: str) -> str | None:
        """Значение настройки или None."""

    def set_setting(self, key: str, value: str) -> None:
        """Сохраняет настройку."""

    # Целевая структура
    def get_targets(self) -> dict[str, Decimal]:
        """Целевые доли классов активов, %: {"share": 50, ...}. Пусто — цели не заданы."""

    def save_targets(self, targets: dict[str, Decimal]) -> None:
        """Заменяет все целевые доли новыми."""

    # Операции
    def list_operations(self) -> list[Operation]:
        """Все операции всех счетов (порядок не гарантирован)."""

    def add_operation(self, operation: Operation) -> Operation:
        """Сохраняет новую операцию и возвращает её с присвоенным номером."""

    def update_operation(self, operation: Operation) -> None:
        """Перезаписывает операцию с тем же номером (operation.id)."""

    def delete_operation(self, operation_id: int) -> None:
        """Удаляет операцию по номеру."""
