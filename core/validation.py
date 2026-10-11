"""Проверка операции перед сохранением, правкой и удалением.

Сейчас здесь одно правило: нельзя продать больше, чем есть на счёте.
Проверки обязательных полей формы появятся на шаге 1.5.
"""

from core.calculations import OversellError, calculate_account_positions
from core.models import Operation


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


__all__ = ["OversellError", "check_can_delete", "check_can_save"]
