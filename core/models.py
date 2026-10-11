"""Основные сущности приложения: операция и позиция.

Деньги и количества — только Decimal (точные десятичные числа), никогда float:
0.1 + 0.2 во float даёт 0.30000000000000004, а в Decimal — ровно 0.3.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class OpType(str, Enum):
    """Тип операции. Значения совпадают с колонкой operations.op_type в базе."""

    BUY = "buy"            # покупка
    SELL = "sell"          # продажа
    DEPOSIT = "deposit"    # пополнение счёта
    WITHDRAW = "withdraw"  # вывод денег
    DIVIDEND = "dividend"  # дивиденд
    COUPON = "coupon"      # купон по облигации


@dataclass(frozen=True)
class Account:
    """Брокерский счёт или ИИС — строка таблицы accounts."""

    id: int
    name: str
    broker: str
    account_type: str = "broker"  # "broker" или "iis"


@dataclass(frozen=True)
class Operation:
    """Одна операция на счёте — строка таблицы operations.

    Для покупки и продажи заполнены ticker, quantity и price.
    Для пополнения, вывода, дивиденда и купона — amount.
    """

    account_id: int
    op_datetime: datetime
    op_type: OpType
    ticker: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = Decimal("0")
    amount: Decimal | None = None
    note: str | None = None
    id: int | None = None  # None — операция ещё не сохранена в базе


@dataclass(frozen=True)
class Instrument:
    """Ценная бумага из справочника: тикер, название, режим торгов, класс актива."""

    ticker: str
    name: str | None = None         # короткое название: «Сбербанк»
    isin: str | None = None
    board: str | None = None        # режим торгов MOEX: TQBR (акции), TQTF (фонды)
    asset_class: str | None = None  # "share", "etf", "bond"


@dataclass(frozen=True)
class Quote:
    """Цена бумаги на бирже в определённый момент (московское время)."""

    ticker: str
    price: Decimal
    time: datetime


@dataclass(frozen=True)
class Position:
    """Сколько бумаги есть и во что она обошлась.

    Хранится полная стоимость покупки (cost), а средняя цена считается из неё.
    Так при частичных продажах не накапливаются ошибки округления.
    """

    ticker: str
    quantity: Decimal
    cost: Decimal  # сколько денег вложено в оставшиеся бумаги, с комиссиями

    @property
    def avg_price(self) -> Decimal:
        """Средняя цена покупки одной бумаги."""
        return self.cost / self.quantity
