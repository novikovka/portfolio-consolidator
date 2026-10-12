"""Структура портфеля и ребалансировка (REQUIREMENTS 3.4, US-9, US-10).

- Доли считаются от стоимости портфеля: бумаги по текущим ценам + деньги.
  Отрицательный остаток денег (покупки внесены, пополнения — нет) в
  стоимость не входит — как на странице «Портфель».
- Бумаги без цены в структуру не попадают: их стоимость неизвестна.
- Ребалансировка класса = цель % × стоимость портфеля − текущая стоимость класса.
  Плюс — докупить, минус — продать.
"""

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from core.valuation import PositionValue

HUNDRED = Decimal("100")
ZERO = Decimal("0")

# Классы, для которых можно задать цель (как в таблице target_allocation)
TARGET_CLASSES = ("share", "bond", "etf", "cash")
UNKNOWN_CLASS = "unknown"  # бумага введена вручную, и биржа не знает её класс
UNKNOWN_SECTOR = "Не указан"

CLASS_LABELS = {
    "share": "Акции",
    "bond": "Облигации",
    "etf": "Фонды",
    "cash": "Деньги",
    UNKNOWN_CLASS: "Не определён",
}

# Сектора, из которых выбирается сектор акции (биржа его не присылает)
SECTORS = (
    "Финансы", "Нефть и газ", "Металлы и добыча", "Электроэнергетика", "Телекоммуникации",
    "IT", "Потребительский сектор", "Химия и удобрения", "Транспорт", "Недвижимость", "Другое",
)


@dataclass(frozen=True)
class Slice:
    """Кусок круговой диаграммы: подпись, сумма в рублях и доля в %."""

    key: str
    value: Decimal
    share: Decimal


@dataclass(frozen=True)
class TargetRow:
    """Строка таблицы «Цели»: класс актива, факт, цель, отклонение, сумма ребалансировки."""

    asset_class: str
    value: Decimal           # текущая стоимость класса, ₽
    actual: Decimal          # фактическая доля, %
    target: Decimal          # целевая доля, %
    deviation: Decimal       # факт − цель, п.п. (плюс — перебор, минус — недобор)
    rebalance: Decimal       # сколько докупить (+) или продать (−), ₽


def counted_cash(cash: Decimal) -> Decimal:
    """Деньги, которые входят в стоимость портфеля: отрицательный остаток — 0."""
    return max(cash, ZERO)


def breakdown(values: dict[str, Decimal]) -> list[Slice]:
    """Суммы по группам → доли. Пустые группы пропускаются, крупные — первыми.

    Доли в сумме дают 100 % (до округления при показе).
    """
    positive = {key: value for key, value in values.items() if value > 0}
    total = sum(positive.values(), ZERO)
    if total == 0:
        return []
    slices = [Slice(key, value, value / total * HUNDRED) for key, value in positive.items()]
    return sorted(slices, key=lambda s: s.value, reverse=True)


def class_values(
    positions: list[PositionValue], asset_classes: dict[str, str | None], cash: Decimal
) -> dict[str, Decimal]:
    """Стоимость по классам: акции, облигации, фонды, деньги (+ «не определён»)."""
    result: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for v in positions:
        if v.value is not None:
            result[asset_classes.get(v.position.ticker) or UNKNOWN_CLASS] += v.value
    result["cash"] += counted_cash(cash)
    return dict(result)


def sector_values(
    positions: list[PositionValue],
    asset_classes: dict[str, str | None],
    sectors: dict[str, str | None],
) -> dict[str, Decimal]:
    """Стоимость бумаг по секторам. Сектор указывается только у акций;
    облигации и фонды идут одной группой по своему классу («Облигации», «Фонды»).
    Деньги сюда не входят — это структура бумаг."""
    result: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for v in positions:
        if v.value is None:
            continue
        ticker = v.position.ticker
        asset_class = asset_classes.get(ticker) or UNKNOWN_CLASS
        if asset_class == "share":
            key = sectors.get(ticker) or UNKNOWN_SECTOR
        else:
            key = CLASS_LABELS[asset_class]
        result[key] += v.value
    return dict(result)


def check_targets(targets: dict[str, Decimal]) -> list[str]:
    """Ошибки в целевых долях. Пустой список — всё правильно."""
    errors = []
    if any(share < 0 or share > HUNDRED for share in targets.values()):
        errors.append("Каждая доля должна быть от 0 до 100 %.")
    total = sum(targets.values(), ZERO)
    if total != HUNDRED:
        errors.append(f"Сумма долей должна быть 100 %, сейчас {_plain(total)} %.")
    return errors


def rebalance(class_totals: dict[str, Decimal], targets: dict[str, Decimal]) -> list[TargetRow]:
    """Факт, цель, отклонение и сумма ребалансировки по каждому классу с целью."""
    portfolio = sum((v for v in class_totals.values() if v > 0), ZERO)
    rows = []
    for asset_class in TARGET_CLASSES:
        if asset_class not in targets:
            continue
        value = max(class_totals.get(asset_class, ZERO), ZERO)
        actual = value / portfolio * HUNDRED if portfolio else ZERO
        target = targets[asset_class]
        rows.append(TargetRow(
            asset_class=asset_class,
            value=value,
            actual=actual,
            target=target,
            deviation=actual - target,
            rebalance=target / HUNDRED * portfolio - value,
        ))
    return rows


def over_threshold(rows: list[TargetRow], threshold: Decimal) -> list[TargetRow]:
    """Классы, которые отклонились от цели больше порога (в п.п., в любую сторону)."""
    return [row for row in rows if abs(row.deviation) > threshold]


def _plain(value: Decimal) -> str:
    """100.00 → «100», 92.5 → «92,5» — для текста ошибки."""
    return f"{value.normalize():f}".replace(".", ",")
