"""Оценка портфеля по текущим ценам: стоимость и доходность (REQUIREMENTS 3.4).

- Стоимость позиции: акции и фонды — количество × цена;
  облигации — количество × номинал × цена% / 100.
- НКД облигаций показывается отдельно и в стоимость не входит.
- Доходность позиции = стоимость − вложено; в % = доходность / вложено × 100.
- Итоги по портфелю считаются только по бумагам, для которых есть цена;
  бумаги без цены показываются отдельно.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.models import Instrument, Position, Quote

HUNDRED = Decimal("100")


@dataclass(frozen=True)
class PositionValue:
    """Позиция вместе с текущей ценой. Если цены нет — price и всё, что от неё зависит, None."""

    position: Position
    price: Decimal | None = None
    price_time: datetime | None = None
    face_value: Decimal | None = None       # номинал, если это облигация
    accrued_per_bond: Decimal | None = None  # текущий НКД на одну облигацию

    @property
    def is_bond(self) -> bool:
        return self.face_value is not None

    @property
    def value(self) -> Decimal | None:
        if self.price is None:
            return None
        if self.is_bond:
            return self.position.quantity * self.face_value * self.price / HUNDRED
        return self.position.quantity * self.price

    @property
    def accrued(self) -> Decimal | None:
        """Накопленный купонный доход по всей позиции, ₽."""
        if self.accrued_per_bond is None:
            return None
        return self.position.quantity * self.accrued_per_bond

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


def value_positions(
    positions: list[Position],
    quotes: dict[str, Quote],
    instruments: dict[str, Instrument] | None = None,
) -> list[PositionValue]:
    """Добавляет к позициям текущие цены (если они есть) и номинал облигаций."""
    instruments = instruments or {}
    result = []
    for position in positions:
        instrument = instruments.get(position.ticker)
        face = instrument.face_value if instrument and instrument.is_bond else None
        quote = quotes.get(position.ticker)
        if quote is None:
            result.append(PositionValue(position, face_value=face))
        else:
            result.append(PositionValue(
                position, price=quote.price, price_time=quote.time,
                face_value=face, accrued_per_bond=quote.accrued_interest if face else None,
            ))
    return result


def portfolio_totals(values: list[PositionValue]) -> PortfolioTotals:
    priced = [v for v in values if v.price is not None]
    return PortfolioTotals(
        cost=sum((v.position.cost for v in values), Decimal("0")),
        priced_cost=sum((v.position.cost for v in priced), Decimal("0")),
        value=sum((v.value for v in priced), Decimal("0")),
        unpriced=len(values) - len(priced),
    )
