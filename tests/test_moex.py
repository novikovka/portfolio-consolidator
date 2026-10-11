"""Тесты разбора ответов Мосбиржи. Запуск: pytest

Используется настоящий ответ ISS по SBER (tests/fixtures/moex_sber_tqbr.json),
сохранённый из браузера 11.10.2026. Интернет для тестов не нужен.
"""

import copy
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market.moex_provider import parse_instruments, parse_quotes

FIXTURE = Path(__file__).parent / "fixtures" / "moex_sber_tqbr.json"


@pytest.fixture
def payload():
    with FIXTURE.open(encoding="utf-8") as file:
        return json.load(file, parse_float=Decimal)


def set_marketdata(payload, **values):
    """Копия ответа с изменёнными полями marketdata для SBER."""
    changed = copy.deepcopy(payload)
    columns = changed["marketdata"]["columns"]
    row = changed["marketdata"]["data"][0]
    for name, value in values.items():
        row[columns.index(name)] = value
    return changed


def test_price_is_last_trade(payload):
    """Основная цена — последняя сделка (LAST = 285,84), время — SYSTIME."""
    quote = parse_quotes(payload)["SBER"]
    assert quote.price == Decimal("285.84")
    assert quote.time == datetime(2026, 10, 11, 19, 15, 18)


def test_no_trades_today_uses_current_price(payload):
    """Сделок не было (LAST пусто) → официальная текущая цена LCURRENTPRICE = 285,72."""
    quote = parse_quotes(set_marketdata(payload, LAST=None))["SBER"]
    assert quote.price == Decimal("285.72")


def test_no_current_price_uses_previous_close(payload):
    """Нет и текущей цены → закрытие прошлого дня PREVPRICE = 285,02."""
    quote = parse_quotes(set_marketdata(payload, LAST=None, LCURRENTPRICE=None))["SBER"]
    assert quote.price == Decimal("285.02")


def test_no_price_at_all_skips_security(payload):
    changed = set_marketdata(payload, LAST=None, LCURRENTPRICE=None)
    changed["securities"]["data"][0][changed["securities"]["columns"].index("PREVPRICE")] = None
    assert parse_quotes(changed) == {}


def test_instruments_from_securities_block(payload):
    """Справочник: тикер, короткое название, ISIN, режим торгов и класс актива."""
    [sber] = parse_instruments(payload)
    assert sber.ticker == "SBER"
    assert sber.name == "Сбербанк"
    assert sber.isin == "RU0009029540"
    assert sber.board == "TQBR"
    assert sber.asset_class == "share"


def test_inactive_instruments_are_skipped(payload):
    changed = copy.deepcopy(payload)
    changed["securities"]["data"][0][changed["securities"]["columns"].index("STATUS")] = "N"
    assert parse_instruments(changed) == []
