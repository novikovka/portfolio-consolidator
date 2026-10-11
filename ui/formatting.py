"""Разбор чисел из полей ввода и форматирование чисел для экрана.

Русский формат: пробел между разрядами, запятая перед копейками — 1 234 567,89.
Здесь нет Streamlit, поэтому всё легко проверяется тестами.
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from core.models import OpType

NBSP = " "  # неразрывный пробел: число не переносится на две строки

OP_TYPE_LABELS = {
    OpType.BUY: "Покупка",
    OpType.SELL: "Продажа",
    OpType.DEPOSIT: "Пополнение",
    OpType.WITHDRAW: "Вывод",
    OpType.DIVIDEND: "Дивиденд",
    OpType.COUPON: "Купон",
}


def parse_decimal(text: str | None) -> Decimal | None:
    """«298,50», «298.50», «1 234,5» → Decimal. Пустая строка → None.

    Если это не число, выбрасывает ValueError.
    """
    if text is None:
        return None
    cleaned = text.strip().replace(" ", "").replace(NBSP, "").replace(",", ".")
    if not cleaned:
        return None
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"«{text.strip()}» — не число") from None
    if not value.is_finite():
        raise ValueError(f"«{text.strip()}» — не число")
    return value


def fmt_money(value: Decimal, digits: int = 2) -> str:
    """1234567.891 → «1 234 567,89»."""
    text = f"{value:,.{digits}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", NBSP)


def fmt_signed_money(value: Decimal) -> str:
    """Сумма со знаком: «+1 416,00» / «−5 971,79»."""
    if value > 0:
        return "+" + fmt_money(value)
    if value < 0:
        return "−" + fmt_money(-value)
    return fmt_money(value)


def fmt_qty(value: Decimal) -> str:
    """Количество без лишних нулей: 10.000000 → «10», 2500 → «2 500», 0.5 → «0,5»."""
    normalized = value.normalize()
    digits = max(0, -normalized.as_tuple().exponent)
    return fmt_money(value, digits)


def fmt_price(value: Decimal) -> str:
    """Цена: минимум 2 знака после запятой, максимум 6. 250 → «250,00», 6.4215 → «6,4215»."""
    normalized = value.normalize()
    digits = min(6, max(2, -normalized.as_tuple().exponent))
    return fmt_money(value, digits)


def fmt_input(value: Decimal | None) -> str:
    """Число для подстановки в поле ввода при правке: 250.000000 → «250», 298.5 → «298,5»."""
    if value is None:
        return ""
    return f"{value.normalize():f}".replace(".", ",")


def fmt_datetime(value: datetime) -> str:
    """Дата и время сделки: «07.10.2026 11:42»."""
    return value.strftime("%d.%m.%Y %H:%M")
