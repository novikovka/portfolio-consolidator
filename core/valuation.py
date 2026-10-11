"""Оценка портфеля по текущим ценам: стоимость и доходность (REQUIREMENTS 3.4).

- Стоимость позиции = количество × текущая цена.
- Доходность позиции = стоимость − вложено; в % = доходность / вложено × 100.
- Итоги по портфелю считаются только по бумагам, для которых есть цена;
  бумаги без цены показываются отдельно.

Облигации (цена в % от номинала) — этап 3.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.models import Position, Quote

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PositionValue:
    """Позиция вместе с текущей ценой. Если цены нет — price и всё, что от неё зависит, None."""

    position: Position
    price: Decimal | None = None
    price_time: datetime | None = None

    @property
    def value(self) -> Decimal | None:
        return None if self.price is None else self.position.quantity * self.price

    @property
    def pnl(self) -> Decimal | None:
        return None if self.value is None else self.value - self.position.cost

    @property
    def pnl_pct(self) -> Decimal | None:
        if self.pnl is None or self.position.cost == 0:
            return None
        return self.pnl / self.position.cost * HUNDRED


@dataclass(frozen=True)
class PortfolioTotals:
    cost: Decimal          # вложено во все бумаги
    priced_cost: Decimal   # вложено в бумаги, у которых есть цена
    value: Decimal         # стоимость бумаг с ценой
    unpriced: int          # сколько бумаг без цены

    @property
    def pnl(self) -> Decimal:
        return self.value - self.priced_cost

    @property
    def pnl_pct(self) -> Decimal | None:
        return None if self.priced_cost == 0 else self.pnl / self.priced_cost * HUNDRED


def value_positions(positions: list[Position], quotes: dict[str, Quote]) -> list[PositionValue]:
    """Добавляет к позициям текущие цены (если они есть)."""
    result = []
    for position in positions:
        quote = quotes.get(position.ticker)
        if quote is None:
            result.append(PositionValue(position))
        else:
            result.append(PositionValue(position, price=quote.price, price_time=quote.time))
    return result


def portfolio_totals(values: list[PositionValue]) -> PortfolioTotals:
    priced = [v for v in values if v.price is not None]
    return PortfolioTotals(
        cost=sum((v.position.cost for v in values), Decimal("0")),
        priced_cost=sum((v.position.cost for v in priced), Decimal("0")),
        value=sum((v.value for v in priced), Decimal("0")),
        unpriced=len(values) - len(priced),
    )
