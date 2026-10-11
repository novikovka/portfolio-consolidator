"""Интерфейс источника рыночных данных.

Фасад работает только с этим интерфейсом. В тестах вместо биржи
подставляется заглушка, а при желании можно добавить другой источник цен.
"""

from typing import Protocol

from core.models import Instrument, Quote


class MarketDataError(Exception):
    """Биржа недоступна или ответила ошибкой. Текст — понятное объяснение."""


class PriceProvider(Protocol):
    def list_instruments(self) -> list[Instrument]:
        """Все бумаги, которые сейчас торгуются (для подсказок тикеров)."""

    def get_quotes(self, tickers_by_board: dict[str, list[str]]) -> dict[str, Quote]:
        """Текущие цены: {режим торгов: [тикеры]} → {тикер: цена}.

        Тикеров, по которым биржа не дала цену, в результате нет.
        """
