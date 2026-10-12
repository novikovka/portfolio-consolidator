"""Расчёт позиций по операциям.

Правила (REQUIREMENTS.md, 3.4):
- Покупка: количество растёт, в стоимость добавляется сумма сделки + комиссия.
  Сумма сделки: акции и фонды — количество × цена; облигации — количество × номинал × цена% / 100.
  НКД в стоимость не входит (его вернёт ближайший купон), он учитывается только в деньгах.
  Средняя цена = стоимость / количество (₽ за штуку).
- Продажа: количество уменьшается, стоимость уменьшается пропорционально,
  поэтому средняя цена НЕ меняется.
- Продала всё — позиция исчезает; следующая покупка считается с нуля.
- Операции обрабатываются по времени, даже если пришли в другом порядке.
- Позиции считаются отдельно по каждому счёту и только потом складываются.
  Если смешать счета в одну кучу, средняя цена получится неправильной.
"""

from collections import defaultdict
from decimal import Decimal

from core.models import Operation, OpType, Position

ZERO = Decimal("0")


class OversellError(ValueError):
    """Попытка продать больше бумаг, чем есть на счёте.

    В поле operation — та продажа, на которой не хватило бумаг.
    """

    def __init__(self, message: str, operation: Operation):
        super().__init__(message)
        self.operation = operation


def calculate_account_positions(operations: list[Operation]) -> dict[tuple[int, str], Position]:
    """Позиции по каждому счёту отдельно.

    Возвращает словарь: (номер счёта, тикер) → позиция.
    Бумаги с нулевым остатком в результат не попадают.
    """
    quantity: dict[tuple[int, str], Decimal] = defaultdict(lambda: ZERO)
    cost: dict[tuple[int, str], Decimal] = defaultdict(lambda: ZERO)

    for op in _in_time_order(operations):
        if op.op_type not in (OpType.BUY, OpType.SELL):
            continue  # пополнения, выводы, дивиденды и купоны не меняют количество бумаг

        key = (op.account_id, op.ticker)

        if op.op_type == OpType.BUY:
            quantity[key] += op.quantity
            cost[key] += op.trade_amount + op.fee
            continue

        # Продажа
        available = quantity[key]
        if op.quantity > available:
            raise OversellError(
                f"Нельзя продать {_fmt(op.quantity)} шт. {op.ticker}: "
                f"на {op.op_datetime:%d.%m.%Y %H:%M} на этом счёте "
                f"только {_fmt(available)} шт.",
                operation=op,
            )
        # Списываем стоимость пропорционально проданной доле — средняя цена не меняется
        cost[key] -= cost[key] * op.quantity / available
        quantity[key] = available - op.quantity
        if quantity[key] == ZERO:
            cost[key] = ZERO  # убираем возможный хвост округления

    return {
        key: Position(ticker=key[1], quantity=qty, cost=cost[key])
        for key, qty in quantity.items()
        if qty > ZERO
    }


def calculate_positions(operations: list[Operation], account_id: int | None = None) -> list[Position]:
    """Позиции для таблицы «Портфель».

    account_id=None — все счета вместе (одна строка на бумагу),
    иначе — только указанный счёт. Результат отсортирован по тикеру.
    """
    total_quantity: dict[str, Decimal] = defaultdict(lambda: ZERO)
    total_cost: dict[str, Decimal] = defaultdict(lambda: ZERO)

    for (acc, ticker), position in calculate_account_positions(operations).items():
        if account_id is not None and acc != account_id:
            continue
        total_quantity[ticker] += position.quantity
        total_cost[ticker] += position.cost

    return [
        Position(ticker=ticker, quantity=total_quantity[ticker], cost=total_cost[ticker])
        for ticker in sorted(total_quantity)
    ]


def cash_flow(op: Operation) -> Decimal:
    """Сколько денег операция добавила (+) или забрала (−) со счёта.

    Покупка: −(сумма сделки + комиссия + НКД). Продажа: +(сумма сделки − комиссия + НКД).
    Пополнение, дивиденд, купон: +сумма. Вывод: −сумма.
    """
    accrued = op.accrued_interest or ZERO
    if op.op_type == OpType.BUY:
        return -(op.trade_amount + op.fee + accrued)
    if op.op_type == OpType.SELL:
        return op.trade_amount - op.fee + accrued
    if op.op_type == OpType.WITHDRAW:
        return -op.amount
    return op.amount  # пополнение, дивиденд, купон


def cash_balance(operations: list[Operation], account_id: int | None = None) -> Decimal:
    """Деньги на счёте (или на всех счетах): сумма всех поступлений и списаний.

    Может быть отрицательной, если пополнения не вносились — это нормально,
    приложение покажет подсказку (REQUIREMENTS, US-7).
    """
    return sum(
        (cash_flow(op) for op in operations if account_id is None or op.account_id == account_id),
        ZERO,
    )


def _in_time_order(operations: list[Operation]) -> list[Operation]:
    """Сортирует по дате и времени; при совпадении — по номеру в базе."""
    return sorted(operations, key=lambda op: (op.op_datetime, op.id or 0))


def _fmt(number: Decimal) -> str:
    """10.000000 → «10», 2.5000 → «2.5» — для сообщений пользователю."""
    text = f"{number.normalize():f}"
    return text.replace(".", ",")
