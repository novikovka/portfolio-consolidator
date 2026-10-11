"""Сборка операции из значений полей формы.

Общая логика для страницы «Новая операция» и окна правки в журнале:
разбирает числа, собирает Operation и проверяет поля (core/validation.py).
Здесь нет Streamlit, поэтому функция проверяется тестами.
"""

from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal

from core.models import Operation, OpType
from core.validation import validate_fields
from ui.formatting import parse_decimal


def build_trade(
    *,
    account_id: int,
    op_type: OpType,
    trade_date: date,
    trade_time: time,
    ticker: str,
    quantity_text: str,
    price_text: str,
    fee_text: str,
    note: str,
    operation_id: int | None = None,
    now: datetime | None = None,
) -> tuple[Operation | None, list[str]]:
    """Покупка или продажа из полей формы.

    Возвращает (операция, []) если всё в порядке, иначе (None, список ошибок).
    """
    parse_errors: list[str] = []
    quantity = _parse("Количество", quantity_text, parse_errors)
    price = _parse("Цена", price_text, parse_errors)
    fee = _parse("Комиссия", fee_text, parse_errors)

    operation = Operation(
        id=operation_id,
        account_id=account_id,
        op_datetime=datetime.combine(trade_date, trade_time).replace(second=0, microsecond=0),
        op_type=op_type,
        ticker=ticker.strip().upper() or None,
        quantity=quantity,
        price=price,
        fee=fee if fee is not None else Decimal("0"),  # пустая комиссия = 0
        note=note.strip() or None,
    )
    # Остальные поля проверяем, даже если какое-то число не разобралось, —
    # чтобы показать все ошибки сразу. Неразобранные поля подменяем допустимым
    # значением, чтобы к «не число» не добавилось ещё «укажите …».
    checked = replace(
        operation,
        quantity=operation.quantity if quantity is not _INVALID else Decimal("1"),
        price=operation.price if price is not _INVALID else Decimal("1"),
        fee=operation.fee if fee is not _INVALID else Decimal("0"),
    )
    errors = parse_errors + validate_fields(checked, now or datetime.now())
    if errors:
        return None, errors
    return operation, []


_INVALID = object()  # метка «в поле не число»


def _parse(label: str, text: str, errors: list[str]):
    """Число из поля; при ошибке добавляет сообщение и возвращает метку _INVALID."""
    try:
        return parse_decimal(text)
    except ValueError as error:
        errors.append(f"{label}: {error}.")
        return _INVALID
