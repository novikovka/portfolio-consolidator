"""Фасад: всё, что интерфейс может сделать с портфелем.

Интерфейс (ui/, app.py) вызывает только методы PortfolioService и ничего не
знает о SQL и расчётах. Фасад собирает вместе хранилище (storage/) и
бизнес-логику (core/): проверяет операцию, сохраняет её, считает позиции.
"""

from dataclasses import replace

from core.calculations import calculate_positions
from core.models import Account, Operation, Position
from core.validation import OversellError, check_can_delete, check_can_save
from storage.repository import Repository

# Счёт, в который пишутся операции, пока нет страницы «Счета» (этап 3)
DEFAULT_ACCOUNT_NAME = "Основной счёт"
DEFAULT_ACCOUNT_BROKER = "Не указан"


class OperationNotFound(LookupError):
    """Операции с таким номером нет — например, её уже удалили."""


class PortfolioService:
    """Работа с портфелем через любое хранилище, реализующее Repository."""

    def __init__(self, repository: Repository):
        self._repo = repository

    # --- Счета -----------------------------------------------------------

    def list_accounts(self) -> list[Account]:
        return self._repo.list_accounts()

    def get_default_account(self) -> Account:
        """Первый счёт; если счетов ещё нет — создаёт «Основной счёт»."""
        accounts = self._repo.list_accounts()
        if accounts:
            return accounts[0]
        return self._repo.add_account(DEFAULT_ACCOUNT_NAME, DEFAULT_ACCOUNT_BROKER)

    # --- Операции ---------------------------------------------------------

    def list_operations(self, account_id: int | None = None) -> list[Operation]:
        """Журнал операций: новые сверху. account_id=None — все счета."""
        operations = self._repo.list_operations()
        if account_id is not None:
            operations = [op for op in operations if op.account_id == account_id]
        return sorted(operations, key=lambda op: (op.op_datetime, op.id or 0), reverse=True)

    def add_operation(self, operation: Operation) -> Operation:
        """Проверяет и сохраняет новую операцию. Возвращает её с номером.

        Если операция приведёт к продаже «в минус», выбрасывает OversellError
        и ничего не сохраняет.
        """
        operation = _normalize(operation)
        check_can_save(self._repo.list_operations(), operation)
        self._register_security(operation)
        return self._repo.add_operation(operation)

    def update_operation(self, operation: Operation) -> None:
        """Проверяет и сохраняет изменённую операцию (по operation.id)."""
        operation = _normalize(operation)
        others = self._others(operation.id)
        check_can_save(others, operation)
        self._register_security(operation)
        self._repo.update_operation(operation)

    def delete_operation(self, operation_id: int) -> None:
        """Удаляет операцию, если без неё не сломаются более поздние продажи."""
        all_operations = self._repo.list_operations()
        deleted = _find(all_operations, operation_id)
        remaining = [op for op in all_operations if op.id != operation_id]
        check_can_delete(remaining, deleted)
        self._repo.delete_operation(operation_id)

    # --- Позиции ----------------------------------------------------------

    def get_positions(self, account_id: int | None = None) -> list[Position]:
        """Позиции по всем счетам (account_id=None) или по одному счёту."""
        return calculate_positions(self._repo.list_operations(), account_id=account_id)

    # --- Вспомогательное --------------------------------------------------

    def _others(self, operation_id: int | None) -> list[Operation]:
        """Все операции, кроме указанной. Ошибка, если такой операции нет."""
        all_operations = self._repo.list_operations()
        _find(all_operations, operation_id)
        return [op for op in all_operations if op.id != operation_id]

    def _register_security(self, operation: Operation) -> None:
        if operation.ticker:
            self._repo.ensure_security(operation.ticker)


def _normalize(operation: Operation) -> Operation:
    """Приводит тикер к единому виду: « sber » → «SBER»."""
    if operation.ticker is None:
        return operation
    return replace(operation, ticker=operation.ticker.strip().upper())


def _find(operations: list[Operation], operation_id: int | None) -> Operation:
    for op in operations:
        if op.id is not None and op.id == operation_id:
            return op
    raise OperationNotFound(f"Операция №{operation_id} не найдена — возможно, её уже удалили.")


__all__ = ["OperationNotFound", "OversellError", "PortfolioService"]
