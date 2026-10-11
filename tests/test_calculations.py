"""Тесты расчёта позиций. Запуск: pytest

Каждый тест проверяет одно правило из REQUIREMENTS.md (US-2, раздел 3.4).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from core.calculations import OversellError, calculate_positions
from core.models import Operation, OpType
from core.validation import check_can_save

ACC_A = 1
ACC_B = 2


def buy(qty, price, day, account=ACC_A, ticker="SBER", fee="0"):
    return Operation(
        account_id=account, op_datetime=datetime(2026, 10, day, 12, 0), op_type=OpType.BUY,
        ticker=ticker, quantity=Decimal(str(qty)), price=Decimal(str(price)), fee=Decimal(fee),
    )


def sell(qty, price, day, account=ACC_A, ticker="SBER", fee="0"):
    return Operation(
        account_id=account, op_datetime=datetime(2026, 10, day, 12, 0), op_type=OpType.SELL,
        ticker=ticker, quantity=Decimal(str(qty)), price=Decimal(str(price)), fee=Decimal(fee),
    )


def only(positions):
    """Единственная позиция из списка (и проверка, что она одна)."""
    assert len(positions) == 1
    return positions[0]


# 1
def test_two_buys_give_weighted_average():
    """10 шт. по 250 + 10 шт. по 300 → 20 шт. по 275."""
    p = only(calculate_positions([buy(10, 250, 1), buy(10, 300, 2)]))
    assert p.quantity == 20
    assert p.avg_price == 275


# 2
def test_sell_keeps_average_price():
    """Продажа уменьшает количество, но не меняет среднюю цену."""
    p = only(calculate_positions([buy(10, 250, 1), buy(10, 300, 2), sell(5, 320, 3)]))
    assert p.quantity == 15
    assert p.avg_price == 275


# 3
def test_sold_out_position_disappears():
    """Продала всё — позиции в списке нет."""
    assert calculate_positions([buy(10, 250, 1), sell(10, 300, 2)]) == []


# 4
def test_buy_after_full_sale_starts_fresh():
    """После полной продажи новая покупка считается с нуля."""
    p = only(calculate_positions([buy(10, 250, 1), sell(10, 300, 2), buy(5, 280, 3)]))
    assert p.quantity == 5
    assert p.avg_price == 280


# 5
def test_fee_is_included_in_average_price():
    """10 шт. по 250 + комиссия 10 ₽ → средняя 251."""
    p = only(calculate_positions([buy(10, 250, 1, fee="10")]))
    assert p.avg_price == 251
    assert p.cost == 2510


# 6
def test_cannot_sell_more_than_owned():
    """Продать 100 при наличии 15 → понятная ошибка."""
    ops = [buy(10, 250, 1), buy(10, 300, 2), sell(5, 320, 3), sell(100, 320, 4)]
    with pytest.raises(OversellError, match="Нельзя продать 100 шт. SBER.*только 15 шт."):
        calculate_positions(ops)


# 7
def test_operations_are_processed_in_time_order():
    """Порядок в списке не важен — расчёт идёт по дате и времени."""
    shuffled = [sell(5, 320, 3), buy(10, 300, 2), buy(10, 250, 1)]
    p = only(calculate_positions(shuffled))
    assert p.quantity == 15
    assert p.avg_price == 275


# 8
def test_accounts_are_calculated_separately_then_merged():
    """A: 10 по 100, B: 10 по 200, продажа 10 с A → итого 10 по 200, а не по 150."""
    ops = [buy(10, 100, 1, account=ACC_A), buy(10, 200, 2, account=ACC_B), sell(10, 150, 3, account=ACC_A)]

    total = only(calculate_positions(ops))
    assert total.quantity == 10
    assert total.avg_price == 200

    assert calculate_positions(ops, account_id=ACC_A) == []
    assert only(calculate_positions(ops, account_id=ACC_B)).avg_price == 200


# 9
def test_cash_operations_do_not_create_positions():
    """Пополнения, выводы, дивиденды и купоны не создают и не меняют позиций."""
    when = datetime(2026, 10, 5, 12, 0)
    cash_ops = [
        Operation(account_id=ACC_A, op_datetime=when, op_type=OpType.DEPOSIT, amount=Decimal("10000")),
        Operation(account_id=ACC_A, op_datetime=when, op_type=OpType.WITHDRAW, amount=Decimal("1000")),
        Operation(account_id=ACC_A, op_datetime=when, op_type=OpType.DIVIDEND, ticker="SBER", amount=Decimal("300")),
        Operation(account_id=ACC_A, op_datetime=when, op_type=OpType.COUPON, ticker="SU26238RMFS4", amount=Decimal("50")),
    ]
    assert calculate_positions(cash_ops) == []

    p = only(calculate_positions([buy(10, 250, 1), *cash_ops]))
    assert p.quantity == 10
    assert p.avg_price == 250


# 10
def test_cannot_sell_shares_from_another_account():
    """На A 10 шт., на B ничего — продать с B нельзя, даже если всего 10."""
    ops = [buy(10, 250, 1, account=ACC_A), sell(5, 300, 2, account=ACC_B)]
    with pytest.raises(OversellError):
        calculate_positions(ops)


# 11
def test_backdated_sell_that_breaks_later_sell_is_rejected():
    """Продажа задним числом, после которой не хватит бумаг на более позднюю продажу."""
    existing = [buy(10, 250, 1), sell(8, 300, 5)]
    check_can_save(existing, sell(2, 280, 3))           # 10 − 2 − 8 = 0 → можно
    with pytest.raises(OversellError, match="не хватит бумаг для более поздней продажи"):
        check_can_save(existing, sell(5, 280, 3))       # 10 − 5 = 5, а 5-го числа продаём 8
