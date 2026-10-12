"""Тесты этапа 3: счета, деньги на счёте, облигации. Запуск: pytest

Облигация — ОФЗ 26238 из настоящего ответа ISS (tests/fixtures/moex_ofz26238_tqob.json).
"""

import json
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

import pytest

from core.calculations import calculate_positions, cash_balance, cash_flow
from core.models import Account, Instrument, Operation, OpType, Position, Quote
from core.valuation import value_positions
from fakes import FakeMarket, InMemoryRepository
from market.moex_provider import parse_instruments, parse_quotes
from services.portfolio_service import AccountError, PortfolioService
from ui.formatting import fmt_avg_price, fmt_bond_pct
from ui.operation_form import build_operation

NBSP = " "
NOW = datetime(2026, 10, 12, 18, 0)
OFZ = Instrument("SU26238RMFS4", "ОФЗ 26238", "RU000A1038V6", "TQOB", "bond", Decimal("1000"))
FIXTURE = Path(__file__).parent / "fixtures" / "moex_ofz26238_tqob.json"


def op(op_type, day=1, account=1, **fields):
    return Operation(account_id=account, op_datetime=datetime(2026, 10, day, 12, 0), op_type=op_type, **fields)


# --- Облигации: расчёты ------------------------------------------------------

def test_bond_trade_amount_uses_face_value():
    """10 ОФЗ номиналом 1000 по 95 % → сумма сделки 9 500 ₽; средняя цена 950 ₽ за штуку (+ комиссия)."""
    buy = op(OpType.BUY, ticker="OFZ", quantity=Decimal("10"), price=Decimal("95"),
             fee=Decimal("5"), face_value=Decimal("1000"), accrued_interest=Decimal("256.70"))
    assert buy.trade_amount == Decimal("9500")
    [position] = calculate_positions([buy])
    assert position.cost == Decimal("9505")          # НКД в стоимость не входит
    assert position.avg_price == Decimal("950.5")


def test_bond_cash_flow_includes_accrued_interest():
    """При покупке НКД платим, при продаже — получаем."""
    buy = op(OpType.BUY, ticker="OFZ", quantity=Decimal("10"), price=Decimal("95"),
             fee=Decimal("5"), face_value=Decimal("1000"), accrued_interest=Decimal("256.70"))
    sell = op(OpType.SELL, day=2, ticker="OFZ", quantity=Decimal("10"), price=Decimal("96"),
              fee=Decimal("5"), face_value=Decimal("1000"), accrued_interest=Decimal("300"))
    assert cash_flow(buy) == Decimal("-9761.70")
    assert cash_flow(sell) == Decimal("9895")


def test_bond_value_and_accrued():
    """10 ОФЗ по 50,732 % → стоимость 5 073,20 ₽; НКД 25,67 × 10 = 256,70 ₽ отдельно."""
    position = Position("SU26238RMFS4", Decimal("10"), Decimal("5030"))
    quote = Quote("SU26238RMFS4", Decimal("50.732"), NOW, accrued_interest=Decimal("25.67"))
    [v] = value_positions([position], {"SU26238RMFS4": quote}, {"SU26238RMFS4": OFZ})
    assert v.value == Decimal("5073.2")
    assert v.accrued == Decimal("256.70")
    assert v.pnl == Decimal("43.2")


# --- Облигации: ответ биржи ---------------------------------------------------

@pytest.fixture
def ofz_payload():
    with FIXTURE.open(encoding="utf-8") as file:
        return json.load(file, parse_float=Decimal)


def test_parse_bond_quote(ofz_payload):
    """Настоящий ответ: цена 50,732 % (LAST), НКД 25,67 ₽, время 12.10.2026 16:30:49."""
    quote = parse_quotes(ofz_payload)["SU26238RMFS4"]
    assert quote.price == Decimal("50.732")
    assert quote.accrued_interest == Decimal("25.67")
    assert quote.time == datetime(2026, 10, 12, 16, 30, 49)


def test_parse_bond_instrument(ofz_payload):
    [ofz] = parse_instruments(ofz_payload)
    assert (ofz.ticker, ofz.name, ofz.board, ofz.asset_class) == ("SU26238RMFS4", "ОФЗ 26238", "TQOB", "bond")
    assert ofz.face_value == Decimal("1000")


# --- Деньги на счёте ----------------------------------------------------------

def test_cash_balance_per_account():
    """Пополнение 10 000, покупка на 5 000 + комиссия 5, дивиденд 300, вывод 1 000 → 4 295 ₽."""
    ops = [
        op(OpType.DEPOSIT, amount=Decimal("10000")),
        op(OpType.BUY, ticker="SBER", quantity=Decimal("20"), price=Decimal("250"), fee=Decimal("5")),
        op(OpType.DIVIDEND, ticker="SBER", amount=Decimal("300")),
        op(OpType.WITHDRAW, amount=Decimal("1000")),
        op(OpType.DEPOSIT, account=2, amount=Decimal("777")),
    ]
    assert cash_balance(ops, account_id=1) == Decimal("4295")
    assert cash_balance(ops) == Decimal("5072")


def test_negative_cash_is_allowed():
    """Пополнения не вносились — остаток уходит в минус, но покупка не запрещена (вариант A)."""
    ops = [op(OpType.BUY, ticker="SBER", quantity=Decimal("10"), price=Decimal("300"))]
    assert cash_balance(ops) == Decimal("-3000")


# --- Фасад: счета, деньги, облигации -------------------------------------------

@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def service(repo):
    market = FakeMarket([OFZ], {"SU26238RMFS4": Decimal("50.732")}, NOW)
    market.accrued = {"SU26238RMFS4": Decimal("25.67")}
    return PortfolioService(repo, market, clock=lambda: NOW)


def test_create_rename_and_validate_accounts(service):
    main = service.get_default_account()
    iis = service.add_account("  Сбер ИИС ", "Сбербанк", "iis")
    assert iis.name == "Сбер ИИС"
    with pytest.raises(AccountError, match="уже есть"):
        service.add_account("сбер иис", "Сбербанк")
    with pytest.raises(AccountError, match="название"):
        service.add_account("   ", "Т-Банк")
    service.update_account(Account(main.id, "Т-Банк брокерский", "Т-Банк", "broker"))
    assert [a.name for a in service.list_accounts()] == ["Т-Банк брокерский", "Сбер ИИС"]


def test_only_empty_account_can_be_deleted(service):
    main = service.get_default_account()
    iis = service.add_account("Сбер ИИС", "Сбербанк", "iis")
    service.add_operation(op(OpType.DEPOSIT, account=iis.id, amount=Decimal("100")))
    with pytest.raises(AccountError, match="только пустой"):
        service.delete_account(iis.id)
    empty = service.add_account("ВТБ", "ВТБ")
    service.delete_account(empty.id)
    assert [a.id for a in service.list_accounts()] == [main.id, iis.id]


def test_last_account_cannot_be_deleted(service):
    main = service.get_default_account()
    with pytest.raises(AccountError, match="единственный"):
        service.delete_account(main.id)


def test_bond_face_value_is_filled_from_directory(service, repo):
    """Облигация выбрана из списка (справочник знает номинал) → номинал подставится в операцию."""
    repo.update_security(OFZ)
    saved = service.add_operation(op(OpType.BUY, ticker="SU26238RMFS4", quantity=Decimal("10"), price=Decimal("50")))
    assert saved.face_value == Decimal("1000")
    assert service.get_cash() == Decimal("-5000")


def test_portfolio_with_bond_and_cash(service, repo):
    account = service.get_default_account()
    repo.update_security(OFZ)
    service.add_operation(op(OpType.DEPOSIT, account=account.id, amount=Decimal("10000")))
    service.add_operation(op(OpType.BUY, day=2, account=account.id, ticker="SU26238RMFS4",
                             quantity=Decimal("10"), price=Decimal("50.3"), accrued_interest=Decimal("250")))
    view = service.get_portfolio()
    [v] = view.positions
    assert v.value == Decimal("5073.2")
    assert v.accrued == Decimal("256.70")
    assert view.cash == Decimal("10000") - Decimal("5030") - Decimal("250")
    assert view.total_value == Decimal("5073.2") + view.cash


def test_preview_cash_and_account_summaries(service):
    main = service.get_default_account()
    service.add_operation(op(OpType.DEPOSIT, account=main.id, amount=Decimal("1000")))
    before, after = service.preview_cash(op(OpType.WITHDRAW, account=main.id, amount=Decimal("300")))
    assert (before, after) == (Decimal("1000"), Decimal("700"))
    [summary] = service.account_summaries()
    assert (summary.operations, summary.cash, summary.securities) == (1, Decimal("1000"), 0)


# --- Форма: денежные операции и облигации --------------------------------------

def form(op_type, **fields):
    return build_operation(account_id=1, op_type=op_type, trade_date=date(2026, 10, 12),
                           trade_time=time(12, 0), now=NOW, **fields)


def test_form_deposit_and_withdraw_need_only_amount():
    deposit, errors = form(OpType.DEPOSIT, amount_text="10 000", ticker="SBER", quantity_text="5")
    assert errors == []
    assert (deposit.amount, deposit.ticker, deposit.quantity) == (Decimal("10000"), None, None)
    _, errors = form(OpType.WITHDRAW, amount_text="")
    assert errors == ["Укажите сумму."]


def test_form_dividend_needs_ticker_and_amount():
    _, errors = form(OpType.DIVIDEND, amount_text="0")
    assert errors == ["Укажите тикер бумаги, по которой пришла выплата.", "Сумма должна быть больше 0."]
    dividend, errors = form(OpType.DIVIDEND, ticker="sber", amount_text="1393,60")
    assert errors == [] and dividend.ticker == "SBER" and dividend.amount == Decimal("1393.60")


def test_form_bond_trade_with_accrued_interest():
    bond, errors = form(OpType.BUY, ticker="SU26238RMFS4", quantity_text="10", price_text="50,732",
                        accrued_text="256,70", face_value=Decimal("1000"))
    assert errors == []
    assert bond.face_value == Decimal("1000") and bond.accrued_interest == Decimal("256.70")
    _, errors = form(OpType.BUY, ticker="SU26238RMFS4", quantity_text="10", price_text="50",
                     accrued_text="-1", face_value=Decimal("1000"))
    assert errors == ["НКД не может быть отрицательным."]


def test_price_formatting_for_tables():
    assert fmt_avg_price(Decimal("340.217391")) == "340,22"
    assert fmt_avg_price(Decimal("6.42158")) == "6,4216"
    assert fmt_bond_pct(Decimal("50.732")) == f"50,732{NBSP}%"
    assert fmt_bond_pct(Decimal("95")) == f"95,00{NBSP}%"
