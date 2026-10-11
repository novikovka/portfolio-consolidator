"""Тесты фасада PortfolioService. Запуск: pytest

Вместо PostgreSQL используется InMemoryRepository — хранилище в памяти
с тем же набором методов. Поэтому тесты быстрые и не трогают настоящую базу.
"""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal

import pytest

from core.models import Account, Operation, OpType
from services.portfolio_service import (
    DEFAULT_ACCOUNT_NAME,
    OperationNotFound,
    OversellError,
    PortfolioService,
)


class InMemoryRepository:
    """Хранилище в памяти: реализует те же методы, что PostgresRepository."""

    def __init__(self):
        self.accounts: list[Account] = []
        self.securities: set[str] = set()
        self.operations: dict[int, Operation] = {}
        self._next_id = 1

    def list_accounts(self):
        return list(self.accounts)

    def add_account(self, name, broker, account_type="broker"):
        account = Account(id=len(self.accounts) + 1, name=name, broker=broker, account_type=account_type)
        self.accounts.append(account)
        return account

    def ensure_security(self, ticker):
        self.securities.add(ticker)

    def list_operations(self):
        return list(self.operations.values())

    def add_operation(self, operation):
        saved = replace(operation, id=self._next_id)
        self.operations[saved.id] = saved
        self._next_id += 1
        return saved

    def update_operation(self, operation):
        self.operations[operation.id] = operation

    def delete_operation(self, operation_id):
        del self.operations[operation_id]


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def service(repo):
    return PortfolioService(repo)


def trade(op_type, qty, price, day, ticker="SBER", account=1):
    return Operation(
        account_id=account, op_datetime=datetime(2026, 10, day, 12, 0), op_type=op_type,
        ticker=ticker, quantity=Decimal(str(qty)), price=Decimal(str(price)),
    )


# 1
def test_default_account_is_created_once(service, repo):
    """При первом обращении создаётся «Основной счёт», при следующих — не дублируется."""
    first = service.get_default_account()
    second = service.get_default_account()
    assert first.name == DEFAULT_ACCOUNT_NAME
    assert first == second
    assert len(repo.accounts) == 1


# 2
def test_add_operation_saves_with_id_and_normalized_ticker(service, repo):
    """Ввела « sber » — сохранится «SBER», бумага попадёт в справочник."""
    saved = service.add_operation(trade(OpType.BUY, 10, 250, 1, ticker=" sber "))
    assert saved.id is not None
    assert saved.ticker == "SBER"
    assert "SBER" in repo.securities
    assert service.list_operations() == [saved]


# 3
def test_oversell_is_rejected_and_nothing_saved(service):
    """Продажа «в минус» не сохраняется."""
    service.add_operation(trade(OpType.BUY, 10, 250, 1))
    with pytest.raises(OversellError, match="Нельзя продать 15 шт. SBER"):
        service.add_operation(trade(OpType.SELL, 15, 300, 2))
    assert len(service.list_operations()) == 1


# 4
def test_positions_are_calculated_from_saved_operations(service):
    """Позиции считаются из того, что лежит в хранилище: 20 шт. по 275, затем 15 по 275."""
    service.add_operation(trade(OpType.BUY, 10, 250, 1))
    service.add_operation(trade(OpType.BUY, 10, 300, 2))
    service.add_operation(trade(OpType.SELL, 5, 320, 3))
    [position] = service.get_positions()
    assert position.quantity == 15
    assert position.avg_price == 275


# 5
def test_update_operation_recalculates_positions(service):
    """Исправила цену покупки — средняя цена пересчиталась."""
    saved = service.add_operation(trade(OpType.BUY, 10, 250, 1))
    service.update_operation(replace(saved, price=Decimal("260")))
    [position] = service.get_positions()
    assert position.avg_price == 260


# 6
def test_update_that_breaks_later_sell_is_rejected(service, repo):
    """Уменьшила покупку с 10 до 5 шт., а позже продано 8 — правка отклонена."""
    bought = service.add_operation(trade(OpType.BUY, 10, 250, 1))
    service.add_operation(trade(OpType.SELL, 8, 300, 5))
    with pytest.raises(OversellError, match="не хватит бумаг для более поздней продажи"):
        service.update_operation(replace(bought, quantity=Decimal("5")))
    assert repo.operations[bought.id].quantity == 10  # в хранилище ничего не изменилось


# 7
def test_delete_operation_recalculates_positions(service):
    """Удалила вторую покупку — осталась позиция по первой."""
    service.add_operation(trade(OpType.BUY, 10, 250, 1))
    second = service.add_operation(trade(OpType.BUY, 10, 300, 2))
    service.delete_operation(second.id)
    [position] = service.get_positions()
    assert position.quantity == 10
    assert position.avg_price == 250


# 8
def test_delete_buy_needed_by_later_sell_is_rejected(service):
    """Нельзя удалить покупку, если без неё продавать будет нечего."""
    bought = service.add_operation(trade(OpType.BUY, 10, 250, 1))
    service.add_operation(trade(OpType.SELL, 8, 300, 5))
    with pytest.raises(OversellError, match="Нельзя удалить операцию"):
        service.delete_operation(bought.id)
    assert len(service.list_operations()) == 2


# 9
def test_unknown_operation_cannot_be_changed_or_deleted(service):
    """Правка или удаление несуществующей операции — понятная ошибка."""
    with pytest.raises(OperationNotFound):
        service.delete_operation(999)
    with pytest.raises(OperationNotFound):
        service.update_operation(replace(trade(OpType.BUY, 1, 1, 1), id=999))


# 11
def test_preview_shows_position_before_and_after(service, repo):
    """Блок «После сохранения»: 10 по 250 → после покупки 10 по 300 станет 20 по 275. Ничего не сохраняется."""
    before, after = service.preview_position(trade(OpType.BUY, 10, 250, 1))
    assert before is None  # бумаги ещё не было
    assert (after.quantity, after.avg_price) == (10, 250)

    service.add_operation(trade(OpType.BUY, 10, 250, 1))
    before, after = service.preview_position(trade(OpType.BUY, 10, 300, 2, ticker="sber"))
    assert (before.quantity, before.avg_price) == (10, 250)
    assert (after.quantity, after.avg_price) == (20, 275)
    assert len(repo.operations) == 1

    before, after = service.preview_position(trade(OpType.SELL, 10, 300, 3))
    assert after is None  # позиция закроется полностью
    with pytest.raises(OversellError):
        service.preview_position(trade(OpType.SELL, 11, 300, 3))


# 10
def test_journal_is_newest_first_and_filters_by_account(service):
    """Журнал: новые операции сверху; можно показать только один счёт."""
    old = service.add_operation(trade(OpType.BUY, 1, 100, 1, account=1))
    new = service.add_operation(trade(OpType.BUY, 1, 100, 9, account=1))
    other = service.add_operation(trade(OpType.BUY, 1, 100, 5, account=2))
    assert service.list_operations() == [new, other, old]
    assert service.list_operations(account_id=1) == [new, old]
