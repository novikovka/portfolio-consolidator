"""Заглушки для тестов: хранилище в памяти и «биржа» без интернета.

Реализуют те же методы, что PostgresRepository и MoexPriceProvider,
поэтому фасад работает с ними так же, как с настоящими.
"""

from dataclasses import replace

from core.models import Account, Instrument, Operation, Quote
from market.price_provider import MarketDataError


class InMemoryRepository:
    """Хранилище в памяти вместо PostgreSQL."""

    def __init__(self):
        self.accounts: list[Account] = []
        self.securities: dict[str, Instrument] = {}
        self.operations: dict[int, Operation] = {}
        self.quotes: list[Quote] = []
        self.settings: dict[str, str] = {}
        self._next_id = 1

    # Счета
    def list_accounts(self):
        return list(self.accounts)

    def add_account(self, name, broker, account_type="broker"):
        account = Account(id=len(self.accounts) + 1, name=name, broker=broker, account_type=account_type)
        self.accounts.append(account)
        return account

    # Справочник
    def ensure_security(self, ticker):
        self.securities.setdefault(ticker, Instrument(ticker=ticker))

    def list_securities(self):
        return list(self.securities.values())

    def update_security(self, instrument):
        self.securities[instrument.ticker] = instrument

    # Цены
    def save_quotes(self, quotes):
        known = {(q.ticker, q.time) for q in self.quotes}
        self.quotes += [q for q in quotes if (q.ticker, q.time) not in known]

    def latest_quotes(self, tickers):
        latest = {}
        for q in self.quotes:
            if q.ticker in tickers and (q.ticker not in latest or q.time > latest[q.ticker].time):
                latest[q.ticker] = q
        return latest

    # Настройки
    def get_setting(self, key):
        return self.settings.get(key)

    def set_setting(self, key, value):
        self.settings[key] = value

    # Операции
    def list_operations(self):
        return list(self.operations.values())

    def add_operation(self, operation):
        saved = replace(operation, id=self._next_id)
        self.operations[saved.id] = saved
        self._next_id += 1
        return saved

    def update_operation(self, operation):
        self.operations[operation.id] = operation

    def delete_operation(self, operation_id):
        del self.operations[operation_id]


class FakeMarket:
    """«Биржа» для тестов: отдаёт заранее заданные цены и считает запросы."""

    def __init__(self, instruments=(), prices=None, quote_time=None):
        self.instruments = list(instruments)
        self.prices = dict(prices or {})  # тикер → Decimal
        self.quote_time = quote_time
        self.offline = False
        self.quote_requests: list[dict] = []
        self.instrument_requests = 0

    def list_instruments(self):
        self.instrument_requests += 1
        if self.offline:
            raise MarketDataError("Нет связи с Мосбиржей. Показаны последние сохранённые цены.")
        return list(self.instruments)

    def get_quotes(self, tickers_by_board):
        self.quote_requests.append(tickers_by_board)
        if self.offline:
            raise MarketDataError("Нет связи с Мосбиржей. Показаны последние сохранённые цены.")
        return {
            t: Quote(ticker=t, price=self.prices[t], time=self.quote_time)
            for tickers in tickers_by_board.values() for t in tickers if t in self.prices
        }
