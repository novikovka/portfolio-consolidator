"""Интерфейс хранилища: что умеет хранилище, без привязки к конкретной базе.

Фасад (services/portfolio_service.py) работает только с этим интерфейсом.
Поэтому в тестах вместо PostgreSQL можно подставить хранилище в памяти,
а в будущем — заменить базу, не трогая остальной код.
"""

from typing import Protocol

from core.models import Account, Operation


class Repository(Protocol):
    """Набор действий с данными, которые нужны приложению."""

    # Счета
    def list_accounts(self) -> list[Account]:
        """Все счета в порядке создания."""

    def add_account(self, name: str, broker: str, account_type: str = "broker") -> Account:
        """Создаёт счёт и возвращает его с присвоенным номером."""

    # Справочник бумаг
    def ensure_security(self, ticker: str) -> None:
        """Добавляет тикер в справочник, если его там ещё нет."""

    # Операции
    def list_operations(self) -> list[Operation]:
        """Все операции всех счетов (порядок не гарантирован)."""

    def add_operation(self, operation: Operation) -> Operation:
        """Сохраняет новую операцию и возвращает её с присвоенным номером."""

    def update_operation(self, operation: Operation) -> None:
        """Перезаписывает операцию с тем же номером (operation.id)."""

    def delete_operation(self, operation_id: int) -> None:
        """Удаляет операцию по номеру."""
