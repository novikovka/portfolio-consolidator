"""Проверка операции перед сохранением, правкой и удалением.

Два вида проверок:
- validate_fields — поля самой операции (REQUIREMENTS 3.6);
- check_can_save / check_can_delete — не уйдёт ли количество бумаг «в минус».
"""

from datetime import datetime

from core.calculations import OversellError, calculate_account_positions
from core.models import Operation, OpType

MAX_NOTE_LENGTH = 1000


def validate_fields(op: Operation, now: datetime) -> list[str]:
    """Проверяет поля операции. Возвращает список понятных ошибок (пустой — всё в порядке)."""
    errors: list[str] = []

    if op.op_type in (OpType.BUY, OpType.SELL):
        if not op.ticker:
            errors.append("Укажите тикер бумаги, например SBER.")
        errors += _positive(op.quantity, "Укажите количество.", "Количество должно быть больше 0.")
        errors += _positive(op.price, "Укажите цену.", "Цена должна быть больше 0.")
    else:
        if op.op_type in (OpType.DIVIDEND, OpType.COUPON) and not op.ticker:
            errors.append("Укажите тикер бумаги, по которой пришла выплата.")
        errors += _positive(op.amount, "Укажите сумму.", "Сумма должна быть больше 0.")

    if op.fee is None or op.fee < 0:
        errors.append("Комиссия не может быть отрицательной.")
    if op.op_datetime > now:
        errors.append("Дата и время сделки не могут быть в будущем.")
    if op.note and len(op.note) > MAX_NOTE_LENGTH:
        errors.append(f"Заметка длиннее {MAX_NOTE_LENGTH} символов.")

    return errors


def check_can_save(existing: list[Operation], new: Operation) -> None:
    """Выбрасывает OversellError, если новая операция приведёт к продаже «в минус».

    Пересчитывает всю историю вместе с новой операцией. Поэтому ловит и случай,
    когда задним числом вносится продажа, после которой уже не хватит бумаг
    для более поздней продажи.
    """
    try:
        calculate_account_positions([*existing, new])
    except OversellError as error:
        if error.operation is new:
            raise
        # Сама новая операция в порядке, но ломает продажу, внесённую позже
        raise OversellError(
            f"После этой операции не хватит бумаг для более поздней продажи. {error}",
            operation=new,
        ) from error


def check_can_delete(remaining: list[Operation], deleted: Operation) -> None:
    """Выбрасывает OversellError, если без удаляемой операции не хватит бумаг.

    Пример: удаляем покупку 10 шт., а позже была продажа 8 шт. — продавать
    станет нечего, поэтому удаление запрещено.
    """
    try:
        calculate_account_positions(remaining)
    except OversellError as error:
        raise OversellError(
            f"Нельзя удалить операцию: без неё не хватит бумаг для более поздней продажи. {error}",
            operation=deleted,
        ) from error


def _positive(value, if_missing: str, if_not_positive: str) -> list[str]:
    """Ошибка, если значение не заполнено или не больше нуля."""
    if value is None:
        return [if_missing]
    if value <= 0:
        return [if_not_positive]
    return []


__all__ = ["MAX_NOTE_LENGTH", "OversellError", "check_can_delete", "check_can_save", "validate_fields"]
