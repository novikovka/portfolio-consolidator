"""Тесты формы операции, проверок полей, форматирования и суммы сделки. Запуск: pytest"""

from datetime import date, datetime, time
from decimal import Decimal

import pytest

from core.calculations import cash_flow
from core.models import Operation, OpType
from core.validation import validate_fields
from ui.formatting import fmt_money, fmt_price, fmt_qty, fmt_signed_money, parse_decimal
from ui.operation_form import build_trade

NOW = datetime(2026, 10, 11, 18, 0)
NBSP = " "


def form(**overrides):
    """Заполненная форма покупки; в тесте меняем только нужные поля."""
    fields = dict(
        account_id=1, op_type=OpType.BUY, trade_date=date(2026, 10, 7), trade_time=time(11, 42),
        ticker="sber", quantity_text="20", price_text="298,50", fee_text="1,79",
        note="  Докупила на коррекции  ", now=NOW,
    )
    fields.update(overrides)
    return build_trade(**fields)


# --- Разбор чисел -----------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("298,50", Decimal("298.50")),
    ("298.50", Decimal("298.50")),
    ("1 234,5", Decimal("1234.5")),
    (f"1{NBSP}234,5", Decimal("1234.5")),
    ("  10 ", Decimal("10")),
    ("", None),
])
def test_parse_decimal_accepts_comma_dot_and_spaces(text, expected):
    assert parse_decimal(text) == expected


@pytest.mark.parametrize("text", ["abc", "12,3,4", "1e", "nan"])
def test_parse_decimal_rejects_non_numbers(text):
    with pytest.raises(ValueError, match="не число"):
        parse_decimal(text)


# --- Форматирование ---------------------------------------------------------

def test_formatting_uses_russian_style():
    assert fmt_money(Decimal("1234567.891")) == f"1{NBSP}234{NBSP}567,89"
    assert fmt_signed_money(Decimal("-5971.79")) == f"−5{NBSP}971,79"
    assert fmt_signed_money(Decimal("1416")) == f"+1{NBSP}416,00"
    assert fmt_qty(Decimal("10.000000")) == "10"
    assert fmt_qty(Decimal("2500")) == f"2{NBSP}500"
    assert fmt_qty(Decimal("0.5")) == "0,5"
    assert fmt_price(Decimal("250")) == "250,00"
    assert fmt_price(Decimal("6.4215")) == "6,4215"
    assert fmt_price(Decimal("275.025")) == "275,025"


# --- Сумма сделки -----------------------------------------------------------

def test_cash_flow_sign_and_fee():
    """Покупка забирает деньги вместе с комиссией, продажа приносит за вычетом комиссии."""
    when = NOW
    buy = Operation(1, when, OpType.BUY, "SBER", Decimal("20"), Decimal("298.50"), Decimal("1.79"))
    sell = Operation(1, when, OpType.SELL, "YDEX", Decimal("2"), Decimal("4105"), Decimal("2.46"))
    deposit = Operation(1, when, OpType.DEPOSIT, amount=Decimal("20000"))
    withdraw = Operation(1, when, OpType.WITHDRAW, amount=Decimal("1000"))
    assert cash_flow(buy) == Decimal("-5971.79")
    assert cash_flow(sell) == Decimal("8207.54")
    assert cash_flow(deposit) == Decimal("20000")
    assert cash_flow(withdraw) == Decimal("-1000")


# --- Форма операции ---------------------------------------------------------

def test_valid_form_builds_operation():
    """Тикер в заглавных, запятая в числах, время без секунд, заметка без пробелов по краям."""
    op, errors = form()
    assert errors == []
    assert op.ticker == "SBER"
    assert op.quantity == 20 and op.price == Decimal("298.50") and op.fee == Decimal("1.79")
    assert op.op_datetime == datetime(2026, 10, 7, 11, 42)
    assert op.note == "Докупила на коррекции"


def test_empty_fee_means_zero_and_empty_note_means_none():
    op, errors = form(fee_text="", note="   ")
    assert errors == []
    assert op.fee == 0
    assert op.note is None


def test_not_a_number_is_reported_per_field():
    op, errors = form(quantity_text="десять", price_text="abc")
    assert op is None
    assert any(e.startswith("Количество:") for e in errors)
    assert any(e.startswith("Цена:") for e in errors)
    assert not any(e.startswith("Укажите") for e in errors)  # без лишних «укажите количество»


def test_all_problems_are_reported_at_once():
    """Цена «abc», пустой тикер и количество 0 — все три ошибки сразу."""
    op, errors = form(ticker="", quantity_text="0", price_text="abc")
    assert op is None
    assert errors == [
        "Цена: «abc» — не число.",
        "Укажите тикер бумаги, например SBER.",
        "Количество должно быть больше 0.",
    ]


@pytest.mark.parametrize("overrides, expected", [
    ({"ticker": "  "}, "Укажите тикер"),
    ({"quantity_text": ""}, "Укажите количество."),
    ({"quantity_text": "0"}, "Количество должно быть больше 0."),
    ({"price_text": "-5"}, "Цена должна быть больше 0."),
    ({"fee_text": "-1"}, "Комиссия не может быть отрицательной."),
    ({"trade_date": date(2026, 10, 12)}, "не могут быть в будущем"),
    ({"note": "а" * 1001}, "Заметка длиннее 1000 символов."),
])
def test_form_field_checks(overrides, expected):
    op, errors = form(**overrides)
    assert op is None
    assert any(expected in e for e in errors), errors


def test_validate_fields_for_cash_operations():
    """Для дивиденда нужны тикер и сумма (пригодится на этапе 3)."""
    dividend = Operation(1, NOW, OpType.DIVIDEND)
    assert validate_fields(dividend, NOW) == [
        "Укажите тикер бумаги, по которой пришла выплата.",
        "Укажите сумму.",
    ]
