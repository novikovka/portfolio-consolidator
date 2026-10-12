"""Фасад: всё, что интерфейс может сделать с портфелем.

Интерфейс (ui/, app.py) вызывает только методы PortfolioService и ничего не
знает о SQL, бирже и расчётах. Фасад собирает вместе хранилище (storage/),
рыночные данные (market/) и бизнес-логику (core/).
"""

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

from core.calculations import calculate_positions, cash_balance
from core.calculations import cash_flow
from core.models import Account, Instrument, Operation, OpType, Position, Quote
from core.structure import (
    SECTORS, TARGET_CLASSES, Slice, TargetRow, breakdown, check_targets, class_values,
    counted_cash, over_threshold, rebalance, sector_values,
)
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

# Порог отклонения от целевой структуры, п.п. (значение по умолчанию — в db/schema.sql)
THRESHOLD_KEY = "deviation_threshold_pp"
DEFAULT_THRESHOLD = Decimal("5")


@dataclass(frozen=True)
class PortfolioView:
    """Всё, что нужно странице «Портфель»."""

    positions: list[PositionValue]
    totals: PortfolioTotals
    fetched_at: datetime | None  # когда последний раз получали цены с биржи
    warning: str | None          # например, «нет связи с Мосбиржей»
    cash: Decimal = Decimal("0")  # деньги на счёте/счетах; может быть < 0, если пополнения не вносились
    # Деньги, которые входят в стоимость: минус на одном счёте не «съедает» деньги другого
    cash_counted: Decimal = Decimal("0")

    @property
    def total_value(self) -> Decimal:
        """Стоимость портфеля: бумаги с ценой + деньги (отрицательный остаток не входит)."""
        return self.totals.value + self.cash_counted


@dataclass(frozen=True)
class Overview:
    """Всё, что нужно главной странице «Обзор»."""

    portfolio: PortfolioView
    by_class: list[Slice]      # акции / облигации / фонды / деньги
    by_sector: list[Slice]     # сектора акций + облигации и фонды одной группой
    by_account: list[Slice]    # подпись — название счёта
    targets: list[TargetRow]   # пусто, если цели не заданы
    alerts: list[TargetRow]    # классы с отклонением больше порога
    threshold: Decimal
    share_sectors: dict[str, str | None]  # акции в портфеле → их сектор (для таблицы секторов)


@dataclass(frozen=True)
class AccountSummary:
    """Строка страницы «Счета»."""

    account: Account
    operations: int
    securities: int
    value: Decimal   # стоимость бумаг по последним сохранённым ценам
    cash: Decimal


class AccountError(ValueError):
    """Нельзя создать, изменить или удалить счёт. Текст — понятное объяснение."""


class TargetsError(ValueError):
    """Целевые доли или порог заданы неверно. errors — все ошибки сразу."""

    def __init__(self, errors: list[str]):
        super().__init__(" ".join(errors))
        self.errors = errors


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

    def add_account(self, name: str, broker: str, account_type: str = "broker") -> Account:
        """Новый счёт. Название обязательно и не повторяется."""
        name, broker = self._check_account(name, broker, account_type)
        return self._repo.add_account(name, broker, account_type)

    def update_account(self, account: Account) -> None:
        """Переименовать счёт, сменить брокера или тип."""
        name, broker = self._check_account(account.name, account.broker, account.account_type, account.id)
        self._repo.update_account(replace(account, name=name, broker=broker))

    def delete_account(self, account_id: int) -> None:
        """Удалить счёт — только пустой (без операций) и не последний."""
        if any(op.account_id == account_id for op in self._repo.list_operations()):
            raise AccountError("Удалить можно только пустой счёт: сначала удалите или перенесите его операции.")
        if len(self._repo.list_accounts()) <= 1:
            raise AccountError("Нельзя удалить единственный счёт.")
        self._repo.delete_account(account_id)

    def account_summaries(self) -> list[AccountSummary]:
        """Счета со стоимостью бумаг, деньгами и числом операций (по сохранённым ценам)."""
        operations = self._repo.list_operations()
        instruments = {s.ticker: s for s in self._repo.list_securities()}
        result = []
        for account in self._repo.list_accounts():
            own = [op for op in operations if op.account_id == account.id]
            positions = calculate_positions(own)
            values = value_positions(positions, self._repo.latest_quotes([p.ticker for p in positions]), instruments)
            result.append(AccountSummary(
                account=account,
                operations=len(own),
                securities=len(positions),
                value=portfolio_totals(values).value,
                cash=cash_balance(own),
            ))
        return result

    def _counted_cash(self, operations: list[Operation], account_id: int | None) -> Decimal:
        """Деньги для стоимости портфеля: по каждому счёту отдельно, минус считается как 0."""
        if account_id is not None:
            return counted_cash(cash_balance(operations, account_id=account_id))
        return sum(
            (counted_cash(cash_balance(operations, account_id=a.id)) for a in self._repo.list_accounts()),
            Decimal("0"),
        )

    def _check_account(self, name: str, broker: str, account_type: str, account_id: int | None = None):
        name, broker = (name or "").strip(), (broker or "").strip()
        if not name:
            raise AccountError("Укажите название счёта.")
        if not broker:
            raise AccountError("Укажите брокера.")
        if account_type not in ("broker", "iis"):
            raise AccountError("Тип счёта — брокерский или ИИС.")
        if any(a.name.lower() == name.lower() and a.id != account_id for a in self._repo.list_accounts()):
            raise AccountError(f"Счёт «{name}» уже есть — выберите другое название.")
        return name, broker

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
        operation = self._with_face_value(_normalize(operation))
        check_can_save(self._repo.list_operations(), operation)
        self._register_security(operation)
        return self._repo.add_operation(operation)

    def update_operation(self, operation: Operation) -> None:
        """Проверяет и сохраняет изменённую операцию (по operation.id)."""
        operation = self._with_face_value(_normalize(operation))
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
        operation = self._with_face_value(_normalize(operation))
        existing = self._repo.list_operations()
        check_can_save(existing, operation)
        before = calculate_positions(existing, account_id=operation.account_id)
        after = calculate_positions([*existing, operation], account_id=operation.account_id)
        return _position_of(before, operation.ticker), _position_of(after, operation.ticker)

    def preview_cash(self, operation: Operation) -> tuple[Decimal, Decimal]:
        """Деньги на счёте до и после новой операции — для блока «После сохранения»."""
        operation = self._with_face_value(_normalize(operation))
        before = cash_balance(self._repo.list_operations(), account_id=operation.account_id)
        return before, before + cash_flow(operation)

    def get_cash(self, account_id: int | None = None) -> Decimal:
        return cash_balance(self._repo.list_operations(), account_id=account_id)

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

        instruments = {s.ticker: s for s in self._repo.list_securities()}
        values = value_positions(positions, self._repo.latest_quotes(tickers), instruments)
        without_price = [v.position.ticker for v in values if v.price is None]
        if without_price and warning is None:
            warning = "Нет цены для: " + ", ".join(without_price) + ". Эти бумаги не входят в стоимость портфеля."
        operations = self._repo.list_operations()
        return PortfolioView(
            values, portfolio_totals(values), self._fetched_at(), warning,
            cash=cash_balance(operations, account_id=account_id),
            cash_counted=self._counted_cash(operations, account_id),
        )

    # --- Структура и цели (этап 4) ---------------------------------------

    def get_overview(self, refresh: bool = False) -> Overview:
        """Главная страница: итоги, структура по классам/секторам/счетам, отклонения от целей.

        Цены обновляются так же, как на странице «Портфель» (раз в 15 минут или по кнопке).
        """
        view = self.get_portfolio(refresh=refresh)
        instruments = {s.ticker: s for s in self._repo.list_securities()}
        classes = {t: i.asset_class for t, i in instruments.items()}
        sectors = {t: i.sector for t, i in instruments.items()}
        by_class_values = class_values(view.positions, classes, view.cash_counted)

        rows = rebalance(by_class_values, self.get_targets())
        threshold = self.get_threshold()
        return Overview(
            portfolio=view,
            by_class=breakdown(by_class_values),
            by_sector=breakdown(sector_values(view.positions, classes, sectors)),
            by_account=breakdown(self._account_values(instruments)),
            targets=rows,
            alerts=over_threshold(rows, threshold),
            threshold=threshold,
            share_sectors={
                v.position.ticker: sectors.get(v.position.ticker)
                for v in view.positions if classes.get(v.position.ticker) == "share"
            },
        )

    def _account_values(self, instruments: dict[str, Instrument]) -> dict[str, Decimal]:
        """Название счёта → бумаги по сохранённым ценам + деньги (минус как 0)."""
        operations = self._repo.list_operations()
        result = {}
        for account in self._repo.list_accounts():
            positions = calculate_positions(operations, account_id=account.id)
            values = value_positions(positions, self._repo.latest_quotes([p.ticker for p in positions]), instruments)
            result[account.name] = portfolio_totals(values).value + self._counted_cash(operations, account.id)
        return result

    def get_targets(self) -> dict[str, Decimal]:
        """Целевые доли классов, %. Пустой словарь — цели ещё не заданы."""
        return self._repo.get_targets()

    def get_threshold(self) -> Decimal:
        """Порог предупреждения об отклонении, п.п."""
        value = self._repo.get_setting(THRESHOLD_KEY)
        return Decimal(value) if value else DEFAULT_THRESHOLD

    def save_targets(self, targets: dict[str, Decimal], threshold: Decimal) -> None:
        """Сохраняет целевые доли и порог. Ошибки → TargetsError со всеми сообщениями сразу."""
        targets = {c: targets.get(c, Decimal("0")) for c in TARGET_CLASSES}
        errors = check_targets(targets)
        if not Decimal("0") < threshold <= Decimal("100"):
            errors.append("Порог должен быть больше 0 и не больше 100 п.п.")
        if errors:
            raise TargetsError(errors)
        self._repo.save_targets(targets)
        self._repo.set_setting(THRESHOLD_KEY, f"{threshold.normalize():f}")

    def set_sector(self, ticker: str, sector: str | None) -> None:
        """Сектор акции; None — «не указан»."""
        if sector is not None and sector not in SECTORS:
            raise ValueError(f"Неизвестный сектор: {sector}")
        self._repo.set_sector(ticker, sector)

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

    def _with_face_value(self, operation: Operation) -> Operation:
        """Для облигации подставляет номинал из справочника, если он не указан."""
        if operation.face_value is not None or not operation.ticker:
            return operation
        if operation.op_type not in (OpType.BUY, OpType.SELL):
            return operation
        security = next((s for s in self._repo.list_securities() if s.ticker == operation.ticker), None)
        if security and security.is_bond and security.face_value:
            return replace(operation, face_value=security.face_value)
        return operation

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


__all__ = [
    "AccountError", "AccountSummary", "MarketDataError", "OperationNotFound", "Overview",
    "OversellError", "PortfolioService", "PortfolioView", "TargetsError",
]
