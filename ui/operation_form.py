"""Сборка операции из значений полей формы.

Общая логика для страницы «Новая операция» и окна правки в журнале:
разбирает числа, собирает Operation и проверяет поля (core/validation.py).
Здесь нет Streamlit, поэтому функция проверяется тестами.

Какие поля у какого типа (REQUIREMENTS 3.6):
- покупка, продажа: бумага, количество, цена, комиссия (+ НКД для облигаций);
- пополнение, вывод: сумма;
- дивиденд, купон: бумага и сумма.
"""

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

from core.models import Operation, OpType
from core.validation import validate_fields
from ui.formatting import parse_decimal

TRADE_TYPES = (OpType.BUY, OpType.SELL)
TICKER_TYPES = (OpType.BUY, OpType.SELL, OpType.DIVIDEND, OpType.COUPON)

_INVALID = object()  # метка «в поле не число»


def build_operation(
    *,
    account_id: int,
    op_type: OpType,
    trade_date: date,
    trade_time: time,
    ticker: str = "",
    quantity_text: str = "",
    price_text: str = "",
    fee_text: str = "",
    amount_text: str = "",
    accrued_text: str = "",
    face_value: Decimal | None = None,
    note: str = "",
    operation_id: int | None = None,
    now: datetime | None = None,
) -> tuple[Operation | None, list[str]]:
    """Операция любого типа из полей формы.

    Возвращает (операция, []) если всё в порядке, иначе (None, список ошибок).
    Поля, которые этому типу не нужны, игнорируются.
    """
    is_trade = op_type in TRADE_TYPES
    is_bond_trade = is_trade and face_value is not None
    parse_errors: list[str] = []

    quantity = _parse("Количество", quantity_text, parse_errors) if is_trade else None
    price = _parse("Цена", price_text, parse_errors) if is_trade else None
    fee = _parse("Комиссия", fee_text, parse_errors) if is_trade else None
    accrued = _parse("НКД", accrued_text, parse_errors) if is_bond_trade else None
    amount = None if is_trade else _parse("Сумма", amount_text, parse_errors)

    operation = Operation(
        id=operation_id,
        account_id=account_id,
        op_datetime=datetime.combine(trade_date, trade_time).replace(second=0, microsecond=0),
        op_type=op_type,
        ticker=(ticker.strip().upper() or None) if op_type in TICKER_TYPES else None,
        quantity=quantity,
        price=price,
        fee=fee if fee not in (None, _INVALID) else Decimal("0"),
        amount=amount,
        note=note.strip() or None,
        face_value=face_value if is_bond_trade else None,
        accrued_interest=accrued if accrued is not _INVALID else None,
    )

    # Остальные поля проверяем, даже если какое-то число не разобралось, —
    # чтобы показать все ошибки сразу. Неразобранные поля подменяем допустимым
    # значением, чтобы к «не число» не добавилось ещё «укажите …».
    checked = replace(
        operation,
        quantity=Decimal("1") if quantity is _INVALID else operation.quantity,
        price=Decimal("1") if price is _INVALID else operation.price,
        amount=Decimal("1") if amount is _INVALID else operation.amount,
    )
    errors = parse_errors + validate_fields(checked, now or datetime.now())
    if errors:
        return None, errors
    return operation, []


def build_trade(**fields) -> tuple[Operation | None, list[str]]:
    """Покупка или продажа акции/фонда (короткая форма build_operation)."""
    return build_operation(**fields)


def _parse(label: str, text: str, errors: list[str]):
    """Число из поля; при ошибке добавляет сообщение и возвращает метку _INVALID."""
    try:
        return parse_decimal(text)
    except ValueError as error:
        errors.append(f"{label}: {error}.")
        return _INVALID
