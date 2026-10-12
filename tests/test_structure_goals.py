"""Тесты этапа 4: структура портфеля, цели и ребалансировка. Запуск: pytest

Портфель для проверки «вручную» (стоимость 10 000 ₽):
- акции SBER: 100 шт. × 70 ₽ = 7 000 ₽ (70 %);
- облигации ОФЗ: 10 шт. × 1 000 ₽ × 20 % = 2 000 ₽ (20 %);
- деньги: 9 000 − 6 000 − 2 000 = 1 000 ₽ (10 %).
"""

from datetime import datetime
from decimal import Decimal

import pytest

from core.models import Instrument, Operation, OpType, Position
from core.structure import (
    Slice, breakdown, check_targets, class_values, over_threshold, rebalance, sector_values,
)
from core.valuation import PositionValue
from fakes import FakeMarket, InMemoryRepository
from services.portfolio_service import PortfolioService, TargetsError

NOW = datetime(2026, 10, 12, 18, 0)
SBER = Instrument("SBER", "Сбербанк", "RU0009029540", "TQBR", "share")
LKOH = Instrument("LKOH", "Лукойл", "RU0009024277", "TQBR", "share")
TMOS = Instrument("TMOS", "Т-Капитал Индекс МосБиржи", "RU000A101X76", "TQTF", "etf")
OFZ = Instrument("SU26238RMFS4", "ОФЗ 26238", "RU000A1038V6", "TQOB", "bond", Decimal("1000"))
TARGETS = {"share": Decimal("50"), "bond": Decimal("40"), "etf": Decimal("0"), "cash": Decimal("10")}


def op(op_type, account=1, day=1, **fields):
    return Operation(account_id=account, op_datetime=datetime(2026, 10, day, 12, 0), op_type=op_type, **fields)


def valued(ticker, value):
    """Позиция стоимостью value ₽ (1 шт. по цене value)."""
    return PositionValue(Position(ticker, Decimal("1"), value), price=value)


# --- Доли ---------------------------------------------------------------------

def test_breakdown_shares_sum_to_100_and_sorted():
    slices = breakdown({"Акции": Decimal("7000"), "Деньги": Decimal("1000"), "Облигации": Decimal("2000"),
                        "Фонды": Decimal("0")})
    assert [s.key for s in slices] == ["Акции", "Облигации", "Деньги"]   # пустые «Фонды» пропущены
    assert [s.share for s in slices] == [Decimal("70"), Decimal("20"), Decimal("10")]
    assert sum(s.share for s in slices) == Decimal("100")


def test_breakdown_of_empty_portfolio():
    assert breakdown({}) == []
    assert breakdown({"cash": Decimal("0")}) == []


def test_class_values_skip_unpriced_and_negative_cash():
    positions = [valued("SBER", Decimal("7000")), valued("OFZ", Decimal("2000")),
                 PositionValue(Position("NOPRICE", Decimal("5"), Decimal("500")))]  # цены нет
    values = class_values(positions, {"SBER": "share", "OFZ": "bond"}, cash=Decimal("-300"))
    assert values == {"share": Decimal("7000"), "bond": Decimal("2000"), "cash": Decimal("0")}


def test_unknown_class_for_manual_ticker():
    values = class_values([valued("MYTICK", Decimal("100"))], {}, cash=Decimal("0"))
    assert values["unknown"] == Decimal("100")


def test_sector_values_only_for_shares():
    positions = [valued("SBER", Decimal("700")), valued("LKOH", Decimal("200")),
                 valued("TMOS", Decimal("50")), valued("OFZ", Decimal("50"))]
    classes = {"SBER": "share", "LKOH": "share", "TMOS": "etf", "OFZ": "bond"}
    values = sector_values(positions, classes, {"SBER": "Финансы"})
    assert values == {"Финансы": Decimal("700"), "Не указан": Decimal("200"),
                      "Фонды": Decimal("50"), "Облигации": Decimal("50")}


# --- Цели ---------------------------------------------------------------------

def test_targets_must_sum_to_100():
    """Проверка из PLAN.md: цели с суммой 90 % → ошибка."""
    errors = check_targets({"share": Decimal("50"), "bond": Decimal("30"), "etf": Decimal("10"), "cash": Decimal("0")})
    assert errors == ["Сумма долей должна быть 100 %, сейчас 90 %."]
    assert check_targets(TARGETS) == []


def test_targets_range():
    errors = check_targets({"share": Decimal("120"), "bond": Decimal("-20")})
    assert errors == ["Каждая доля должна быть от 0 до 100 %."]


def test_rebalance_matches_manual_calculation():
    """Проверка из PLAN.md: акции 70 % при цели 50 % → +20 п.п., продать на 2 000 ₽."""
    rows = rebalance({"share": Decimal("7000"), "bond": Decimal("2000"), "cash": Decimal("1000")}, TARGETS)
    by_class = {r.asset_class: r for r in rows}
    shares = by_class["share"]
    assert (shares.actual, shares.target, shares.deviation) == (Decimal("70"), Decimal("50"), Decimal("20"))
    assert shares.rebalance == Decimal("-2000")                       # 50 % × 10 000 − 7 000
    assert by_class["bond"].rebalance == Decimal("2000")              # докупить
    assert by_class["etf"].rebalance == Decimal("0")
    assert by_class["cash"].deviation == Decimal("0")
    assert sum(r.rebalance for r in rows) == Decimal("0")             # продали столько же, сколько докупили


def test_over_threshold_both_directions():
    rows = rebalance({"share": Decimal("7000"), "bond": Decimal("2000"), "cash": Decimal("1000")}, TARGETS)
    assert [r.asset_class for r in over_threshold(rows, Decimal("5"))] == ["share", "bond"]
    assert over_threshold(rows, Decimal("20")) == []                  # ровно 20 п.п. — ещё не «больше порога»


# --- Фасад -----------------------------------------------------------------------

@pytest.fixture
def repo():
    return InMemoryRepository()


@pytest.fixture
def service(repo):
    market = FakeMarket([SBER, LKOH, OFZ], {"SBER": Decimal("70"), "LKOH": Decimal("100"),
                                            "SU26238RMFS4": Decimal("20")}, NOW)
    for instrument in (SBER, LKOH, OFZ):
        repo.update_security(instrument)
    return PortfolioService(repo, market, clock=lambda: NOW)


def fill_manual_portfolio(service):
    """Портфель из шапки файла: 7 000 ₽ акций, 2 000 ₽ облигаций, 1 000 ₽ денег."""
    account = service.get_default_account()
    service.add_operation(op(OpType.DEPOSIT, account=account.id, amount=Decimal("9000")))
    service.add_operation(op(OpType.BUY, account=account.id, day=2, ticker="SBER",
                             quantity=Decimal("100"), price=Decimal("60")))
    service.add_operation(op(OpType.BUY, account=account.id, day=3, ticker="SU26238RMFS4",
                             quantity=Decimal("10"), price=Decimal("20")))
    return account


def test_overview_structure(service):
    fill_manual_portfolio(service)
    service.set_sector("SBER", "Финансы")
    overview = service.get_overview()
    assert overview.portfolio.total_value == Decimal("10000")
    assert overview.by_class == [Slice("share", Decimal("7000"), Decimal("70")),
                                 Slice("bond", Decimal("2000"), Decimal("20")),
                                 Slice("cash", Decimal("1000"), Decimal("10"))]
    # Сектора — структура бумаг без денег: 7 000 / 9 000 и 2 000 / 9 000
    assert [(s.key, round(s.share, 2)) for s in overview.by_sector] == [("Финансы", Decimal("77.78")),
                                                                       ("Облигации", Decimal("22.22"))]
    assert overview.by_account == [Slice("Основной счёт", Decimal("10000"), Decimal("100"))]
    assert overview.share_sectors == {"SBER": "Финансы"}
    assert overview.targets == [] and overview.alerts == []           # цели ещё не заданы


def test_overview_alerts_after_targets(service, repo):
    fill_manual_portfolio(service)
    service.save_targets(TARGETS, Decimal("5"))
    assert repo.targets == TARGETS and repo.settings["deviation_threshold_pp"] == "5"
    overview = service.get_overview()
    assert [(r.asset_class, r.deviation, r.rebalance) for r in overview.alerts] == [
        ("share", Decimal("20"), Decimal("-2000")), ("bond", Decimal("-20"), Decimal("2000"))]
    # Порог 25 п.п. → предупреждения пропадают
    service.save_targets(TARGETS, Decimal("25"))
    assert service.get_overview().alerts == []


def test_save_targets_collects_all_errors(service, repo):
    with pytest.raises(TargetsError) as error:
        service.save_targets({"share": Decimal("50"), "bond": Decimal("40")}, Decimal("0"))
    assert error.value.errors == ["Сумма долей должна быть 100 %, сейчас 90 %.",
                                  "Порог должен быть больше 0 и не больше 100 п.п."]
    assert repo.targets == {}                                          # ничего не сохранилось
    assert service.get_threshold() == Decimal("5")                     # значение по умолчанию


def test_negative_cash_of_one_account_does_not_eat_another(service):
    """Счёт A: +3 000 ₽ денег. Счёт B: купили на 1 000 ₽ без пополнения (−1 000 ₽).
    В стоимость входят 3 000 ₽ денег счёта A, а минус счёта B считается как 0."""
    a = service.get_default_account()
    b = service.add_account("Сбер ИИС", "Сбербанк", "iis")
    service.add_operation(op(OpType.DEPOSIT, account=a.id, amount=Decimal("3000")))
    service.add_operation(op(OpType.BUY, account=b.id, ticker="LKOH", quantity=Decimal("10"), price=Decimal("100")))
    overview = service.get_overview()
    assert overview.portfolio.cash == Decimal("2000")                  # сумма остатков, как на «Портфеле»
    assert overview.portfolio.total_value == Decimal("4000")           # 1 000 бумаг + 3 000 денег
    assert overview.by_account == [Slice("Основной счёт", Decimal("3000"), Decimal("75")),
                                   Slice("Сбер ИИС", Decimal("1000"), Decimal("25"))]
    assert sum(s.value for s in overview.by_class) == overview.portfolio.total_value


def test_sector_is_kept_when_directory_refreshes(service, repo):
    """Справочник биржи обновляет название и режим торгов, но не стирает сектор, заданный вручную."""
    service.set_sector("SBER", "Финансы")
    repo.update_security(SBER)
    assert repo.securities["SBER"].sector == "Финансы"
    with pytest.raises(ValueError):
        service.set_sector("SBER", "Космос")
