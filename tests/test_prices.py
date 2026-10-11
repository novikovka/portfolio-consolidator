"""Тесты оценки портфеля и обновления цен. Запуск: pytest

Биржа — заглушка FakeMarket (tests/fakes.py), «текущее время» управляется в тесте.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from core.models import Instrument, Operation, OpType, Position, Quote
from core.valuation import portfolio_totals, value_positions
from fakes import FakeMarket, InMemoryRepository
from services.portfolio_service import PortfolioService

SBER = Instrument("SBER", "Сбербанк", "RU0009029540", "TQBR", "share")
LKOH = Instrument("LKOH", "Лукойл", "RU0009024277", "TQBR", "share")
TMOS = Instrument("TMOS", "Т-Капитал Индекс", "RU000A101X76", "TQTF", "etf")
QUOTE_TIME = datetime(2026, 10, 11, 19, 15, 18)


class Clock:
    """Управляемое «текущее время»."""

    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock(datetime(2026, 10, 11, 20, 0))


@pytest.fixture
def market():
    return FakeMarket(
        instruments=[SBER, LKOH, TMOS],
        prices={"SBER": Decimal("301.20"), "LKOH": Decimal("6512"), "TMOS": Decimal("7.05")},
        quote_time=QUOTE_TIME,
    )


@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def service(repo, market, clock):
    return PortfolioService(repo, market, clock=clock)


def buy(service, ticker, qty, price):
    account = service.get_default_account()
    service.add_operation(Operation(
        account_id=account.id, op_datetime=datetime(2026, 10, 1, 12, 0), op_type=OpType.BUY,
        ticker=ticker, quantity=Decimal(str(qty)), price=Decimal(str(price)),
    ))


# --- Оценка (чистые функции) ------------------------------------------------

def test_position_value_and_profit():
    """120 SBER по средней 268,40, цена 301,20 → стоимость 36 144, доходность +3 936 (+12,22 %)."""
    position = Position("SBER", Decimal("120"), Decimal("32208"))
    [v] = value_positions([position], {"SBER": Quote("SBER", Decimal("301.20"), QUOTE_TIME)})
    assert v.value == Decimal("36144")
    assert v.pnl == Decimal("3936")
    assert round(v.pnl_pct, 2) == Decimal("12.22")


def test_loss_is_negative():
    position = Position("LKOH", Decimal("5"), Decimal("34250"))
    [v] = value_positions([position], {"LKOH": Quote("LKOH", Decimal("6512"), QUOTE_TIME)})
    assert v.pnl == Decimal("-1690")
    assert round(v.pnl_pct, 2) == Decimal("-4.93")


def test_totals_skip_positions_without_price():
    """Бумага без цены не искажает доходность: итог считается только по бумагам с ценой."""
    priced = Position("SBER", Decimal("10"), Decimal("2500"))
    unpriced = Position("XXXX", Decimal("1"), Decimal("1000"))
    values = value_positions([priced, unpriced], {"SBER": Quote("SBER", Decimal("300"), QUOTE_TIME)})
    totals = portfolio_totals(values)
    assert totals.cost == Decimal("3500")
    assert totals.value == Decimal("3000")
    assert totals.pnl == Decimal("500")
    assert totals.pnl_pct == Decimal("20")
    assert totals.unpriced == 1


# --- Обновление цен через фасад ---------------------------------------------

def test_first_open_fetches_prices_by_board(service, market):
    """Первое открытие «Портфеля»: цены запрашиваются, бумаги сгруппированы по режимам торгов."""
    buy(service, "SBER", 10, 250)
    buy(service, "TMOS", 1000, 6.5)
    view = service.get_portfolio()
    assert market.quote_requests == [{"TQBR": ["SBER"], "TQTF": ["TMOS"]}]
    prices = {v.position.ticker: v.price for v in view.positions}
    assert prices == {"SBER": Decimal("301.20"), "TMOS": Decimal("7.05")}
    assert view.totals.value == Decimal("3012") + Decimal("7050")
    assert view.warning is None


def test_board_and_name_are_learned_from_exchange(service, repo):
    """Тикер, введённый вручную, получает название и режим торгов из справочника биржи."""
    buy(service, "LKOH", 1, 6800)
    service.get_portfolio()
    assert repo.securities["LKOH"] == LKOH
    assert service.security_names()["LKOH"] == "Лукойл"


def test_fresh_prices_are_not_requested_again(service, market, clock):
    """Цены моложе 15 минут берутся из кэша; старше — запрашиваются заново."""
    buy(service, "SBER", 10, 250)
    service.get_portfolio()
    clock.now += timedelta(minutes=10)
    service.get_portfolio()
    assert len(market.quote_requests) == 1
    clock.now += timedelta(minutes=6)
    service.get_portfolio()
    assert len(market.quote_requests) == 2


def test_refresh_button_always_requests(service, market):
    buy(service, "SBER", 10, 250)
    service.get_portfolio()
    service.get_portfolio(refresh=True)
    assert len(market.quote_requests) == 2


def test_offline_uses_saved_prices_and_warns(service, market, clock):
    """Нет интернета → последние сохранённые цены и предупреждение, без падения."""
    buy(service, "SBER", 10, 250)
    service.get_portfolio()
    market.offline = True
    clock.now += timedelta(hours=1)
    view = service.get_portfolio()
    assert view.positions[0].price == Decimal("301.20")
    assert "Нет связи с Мосбиржей" in view.warning


def test_after_failure_automatic_retries_pause(service, market, clock):
    """После неудачи страница 2 минуты не ждёт биржу заново; кнопка «Обновить» — пробует сразу."""
    buy(service, "SBER", 10, 250)
    market.offline = True
    service.get_portfolio()
    requests_after_failure = len(market.quote_requests) + market.instrument_requests
    clock.now += timedelta(minutes=1)
    service.get_portfolio()
    assert len(market.quote_requests) + market.instrument_requests == requests_after_failure
    service.get_portfolio(refresh=True)
    assert len(market.quote_requests) + market.instrument_requests > requests_after_failure


def test_unknown_ticker_gets_warning(service):
    """Тикера нет на бирже (например, опечатка) → позиция без цены и понятное предупреждение."""
    buy(service, "NOPE", 1, 100)
    view = service.get_portfolio()
    assert view.positions[0].price is None
    assert "Нет цены для: NOPE" in view.warning


def test_quote_for_form(service, market, repo):
    """Форма: текущая цена выбранной бумаги; без связи — последняя сохранённая."""
    assert service.get_quote(SBER).price == Decimal("301.20")
    assert repo.securities["SBER"] == SBER
    market.offline = True
    assert service.get_quote(SBER).price == Decimal("301.20")
    assert service.get_quote(LKOH) is None
