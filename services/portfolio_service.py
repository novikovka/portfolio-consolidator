"""Фасад: всё, что интерфейс может сделать с портфелем.

Интерфейс (ui/, app.py) вызывает только методы PortfolioService и ничего не
знает о SQL, бирже и расчётах. Фасад собирает вместе хранилище (storage/),
рыночные данные (market/) и бизнес-логику (core/).
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Callable

from core.calculations import calculate_positions
from core.models import Account, Instrument, Operation, Position, Quote
from core.validation import OversellError, check_can_delete, check_can_save
from core.valuation import PortfolioTotals, PositionValue, portfolio_totals, value_positions
from market.price_provider import MarketDataError, PriceProvider
from storage.repository import Repository

# Счёт, в который пишутся операции, пока нет страницы «Счета» (этап 3)
DEFAULT_ACCOUNT_NAME = "Основной счёт"
DEFAULT_ACCOUNT_BROKER = "Не указан"

# Если цены обновлялись раньше, чем столько минут назад, — запрашиваем заново (REQUIREMENTS 3.5)
QUOTES_MAX_AGE = timedelta(minutes=15)
QUOTES_FETCHED_AT_KEY = "quotes_fetched_at"
# После неудачной попытки не дёргаем биржу при каждом открытии страницы, а ждём
RETRY_AFTER_FAILURE = timedelta(minutes=2)
QUOTES_FAILED_AT_KEY = "quotes_failed_at"


@dataclass(frozen=True)
class PortfolioView:
    """Всё, что нужно странице «Портфель»."""

    positions: list[PositionValue]
    totals: PortfolioTotals
    fetched_at: datetime | None  # когда последний раз получали цены с биржи
    warning: str | None          # например, «нет связи с Мосбиржей»


class OperationNotFound(LookupError):
    """Операции с таким номером нет — например, её уже удалили."""


class PortfolioService:
    """Работа с портфелем через любое хранилище, реализующее Repository."""

    def __init__(
        self,
        repository: Repository,
        market: PriceProvider | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self._repo = repository
        self._market = market
        self._now = clock  # в тестах подменяется, чтобы управлять «текущим временем»

    # --- Счета -----------------------------------------------------------

    def list_accounts(self) -> list[Account]:
        return self._repo.list_accounts()

    def get_default_account(self) -> Account:
        """Первый счёт; если счетов ещё нет — создаёт «Основной счёт»."""
        accounts = self._repo.list_accounts()
        if accounts:
            return accounts[0]
        return self._repo.add_account(DEFAULT_ACCOUNT_NAME, DEFAULT_ACCOUNT_BROKER)

    # --- Операции ---------------------------------------------------------

    def list_operations(self, account_id: int | None = None) -> list[Operation]:
        """Журнал операций: новые сверху. account_id=None — все счета."""
        operations = self._repo.list_operations()
        if account_id is not None:
            operations = [op for op in operations if op.account_id == account_id]
        return sorted(operations, key=lambda op: (op.op_datetime, op.id or 0), reverse=True)

    def add_operation(self, operation: Operation) -> Operation:
        """Проверяет и сохраняет новую операцию. Возвращает её с номером.

        Если операция приведёт к продаже «в минус», выбрасывает OversellError
        и ничего не сохраняет.
        """
        operation = _normalize(operation)
        check_can_save(self._repo.list_operations(), operation)
        self._register_security(operation)
        return self._repo.add_operation(operation)

    def update_operation(self, operation: Operation) -> None:
        """Проверяет и сохраняет изменённую операцию (по operation.id)."""
        operation = _normalize(operation)
        others = self._others(operation.id)
        check_can_save(others, operation)
        self._register_security(operation)
        self._repo.update_operation(operation)

    def delete_operation(self, operation_id: int) -> None:
        """Удаляет операцию, если без неё не сломаются более поздние продажи."""
        all_operations = self._repo.list_operations()
        deleted = _find(all_operations, operation_id)
        remaining = [op for op in all_operations if op.id != operation_id]
        check_can_delete(remaining, deleted)
        self._repo.delete_operation(operation_id)

    # --- Позиции ----------------------------------------------------------

    def get_positions(self, account_id: int | None = None) -> list[Position]:
        """Позиции по всем счетам (account_id=None) или по одному счёту."""
        return calculate_positions(self._repo.list_operations(), account_id=account_id)

    def preview_position(self, operation: Operation) -> tuple[Position | None, Position | None]:
        """Позиция по бумаге на счёте до и после новой операции — для блока «После сохранения».

        None означает «позиции нет». Ничего не сохраняет. Если операция приведёт
        к продаже «в минус», выбрасывает OversellError.
        """
        operation = _normalize(operation)
        existing = self._repo.list_operations()
        check_can_save(existing, operation)
        before = calculate_positions(existing, account_id=operation.account_id)
        after = calculate_positions([*existing, operation], account_id=operation.account_id)
        return _position_of(before, operation.ticker), _position_of(after, operation.ticker)

    # --- Цены и оценка портфеля -----------------------------------------

    def get_portfolio(self, account_id: int | None = None, refresh: bool = False) -> PortfolioView:
        """Позиции с текущими ценами, стоимостью и доходностью.

        Цены запрашиваются с биржи, если refresh=True или сохранённым больше 15 минут.
        Если биржа недоступна — используются последние сохранённые цены и
        возвращается предупреждение.
        """
        positions = self.get_positions(account_id=account_id)
        tickers = [p.ticker for p in positions]
        warning = None
        should_fetch = refresh or (self._quotes_are_stale() and not self._failed_recently())
        if tickers and self._market is not None and should_fetch:
            try:
                self.refresh_prices(tickers)
            except MarketDataError as error:
                self._repo.set_setting(QUOTES_FAILED_AT_KEY, self._now().isoformat(timespec="seconds"))
                warning = str(error)

        values = value_positions(positions, self._repo.latest_quotes(tickers))
        without_price = [v.position.ticker for v in values if v.price is None]
        if without_price and warning is None:
            warning = "Нет цены для: " + ", ".join(without_price) + ". Эти бумаги не входят в стоимость портфеля."
        return PortfolioView(values, portfolio_totals(values), self._fetched_at(), warning)

    def refresh_prices(self, tickers: list[str]) -> None:
        """Запрашивает цены с биржи и сохраняет их. Ошибка сети → MarketDataError."""
        boards = self._boards_for(tickers)
        groups: dict[str, list[str]] = defaultdict(list)
        for ticker in tickers:
            if boards.get(ticker):
                groups[boards[ticker]].append(ticker)
        quotes = self._market.get_quotes(dict(groups))
        self._repo.save_quotes(list(quotes.values()))
        self._repo.set_setting(QUOTES_FETCHED_AT_KEY, self._now().isoformat(timespec="seconds"))

    def list_instruments(self) -> list[Instrument]:
        """Все торгуемые акции и фонды — для выпадающего списка тикеров."""
        if self._market is None:
            return []
        return self._market.list_instruments()

    def get_quote(self, instrument: Instrument) -> Quote | None:
        """Текущая цена бумаги для формы. Нет связи с биржей → последняя сохранённая или None."""
        self._repo.update_security(instrument)  # запоминаем название и режим торгов
        if self._market is not None and instrument.board:
            try:
                quotes = self._market.get_quotes({instrument.board: [instrument.ticker]})
            except MarketDataError:
                quotes = {}
            if instrument.ticker in quotes:
                self._repo.save_quotes([quotes[instrument.ticker]])
                return quotes[instrument.ticker]
        return self._repo.latest_quotes([instrument.ticker]).get(instrument.ticker)

    def security_names(self) -> dict[str, str]:
        """Тикер → название бумаги (для таблиц)."""
        return {s.ticker: s.name for s in self._repo.list_securities() if s.name}

    def _boards_for(self, tickers: list[str]) -> dict[str, str | None]:
        """Режим торгов для каждого тикера. Неизвестные узнаём из справочника биржи."""
        known = {s.ticker: s.board for s in self._repo.list_securities()}
        missing = [t for t in tickers if not known.get(t)]
        if missing:
            by_ticker = {i.ticker: i for i in self._market.list_instruments()}
            for ticker in missing:
                if ticker in by_ticker:
                    self._repo.update_security(by_ticker[ticker])
                    known[ticker] = by_ticker[ticker].board
        return known

    def _fetched_at(self) -> datetime | None:
        value = self._repo.get_setting(QUOTES_FETCHED_AT_KEY)
        return datetime.fromisoformat(value) if value else None

    def _quotes_are_stale(self) -> bool:
        fetched_at = self._fetched_at()
        return fetched_at is None or self._now() - fetched_at > QUOTES_MAX_AGE

    def _failed_recently(self) -> bool:
        value = self._repo.get_setting(QUOTES_FAILED_AT_KEY)
        return value is not None and self._now() - datetime.fromisoformat(value) < RETRY_AFTER_FAILURE

    # --- Вспомогательное --------------------------------------------------

    def _others(self, operation_id: int | None) -> list[Operation]:
        """Все операции, кроме указанной. Ошибка, если такой операции нет."""
        all_operations = self._repo.list_operations()
        _find(all_operations, operation_id)
        return [op for op in all_operations if op.id != operation_id]

    def _register_security(self, operation: Operation) -> None:
        if operation.ticker:
            self._repo.ensure_security(operation.ticker)


def _normalize(operation: Operation) -> Operation:
    """Приводит тикер к единому виду: « sber » → «SBER»."""
    if operation.ticker is None:
        return operation
    return replace(operation, ticker=operation.ticker.strip().upper())


def _position_of(positions: list[Position], ticker: str | None) -> Position | None:
    return next((p for p in positions if p.ticker == ticker), None)


def _find(operations: list[Operation], operation_id: int | None) -> Operation:
    for op in operations:
        if op.id is not None and op.id == operation_id:
            return op
    raise OperationNotFound(f"Операция №{operation_id} не найдена — возможно, её уже удалили.")


__all__ = ["MarketDataError", "OperationNotFound", "OversellError", "PortfolioService", "PortfolioView"]
