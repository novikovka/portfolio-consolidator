"""Цены и справочник бумаг с Московской биржи (MOEX ISS, бесплатно, без регистрации).

Формат ответа ISS: каждый блок — это {"columns": [...], "data": [[...], ...]}.
Образец настоящего ответа — tests/fixtures/moex_sber_tqbr.json.

Какую цену берём (REQUIREMENTS 3.5):
1. LAST — цена последней сделки;
2. если сегодня сделок не было — LCURRENTPRICE (официальная текущая цена);
3. если нет и её — PREVPRICE (цена закрытия прошлого торгового дня).
Время цены — SYSTIME (московское время).
"""

from datetime import datetime
from decimal import Decimal

import requests

from core.models import Instrument, Quote
from market.price_provider import MarketDataError

BASE_URL = "https://iss.moex.com/iss/engines/stock/markets/shares/boards/{board}/securities.json"
TIMEOUT_SECONDS = 10

# Режимы торгов, которые поддерживаем на этапе 2, и класс актива для каждого.
# Облигации (TQOB, TQCB) — на этапе 3.
BOARDS = {
    "TQBR": "share",  # акции
    "TQTF": "etf",    # биржевые фонды
}


class MoexPriceProvider:
    """Источник данных — публичный API Мосбиржи."""

    def list_instruments(self) -> list[Instrument]:
        instruments: list[Instrument] = []
        for board in BOARDS:
            payload = _get(board, {
                "iss.only": "securities",
                "securities.columns": "SECID,BOARDID,SHORTNAME,ISIN,STATUS",
            })
            instruments += parse_instruments(payload)
        return sorted(instruments, key=lambda i: i.ticker)

    def get_quotes(self, tickers_by_board: dict[str, list[str]]) -> dict[str, Quote]:
        quotes: dict[str, Quote] = {}
        for board, tickers in tickers_by_board.items():
            if not tickers:
                continue
            payload = _get(board, {
                "iss.only": "securities,marketdata",
                "securities": ",".join(tickers),
                "securities.columns": "SECID,PREVPRICE",
                "marketdata.columns": "SECID,LAST,LCURRENTPRICE,SYSTIME",
            })
            quotes.update(parse_quotes(payload))
        return quotes


# --- Разбор ответа (отдельные функции — их проверяют тесты на настоящем ответе) ---

def parse_quotes(payload: dict) -> dict[str, Quote]:
    """Ответ ISS с блоками securities и marketdata → {тикер: цена}."""
    prev_price = {row["SECID"]: row.get("PREVPRICE") for row in _rows(payload, "securities")}
    quotes: dict[str, Quote] = {}
    for row in _rows(payload, "marketdata"):
        ticker = row["SECID"]
        price = row.get("LAST") or row.get("LCURRENTPRICE") or prev_price.get(ticker)
        if not price:
            continue  # по бумаге нет ни одной цены
        quotes[ticker] = Quote(ticker=ticker, price=Decimal(str(price)), time=_parse_time(row.get("SYSTIME")))
    return quotes


def parse_instruments(payload: dict) -> list[Instrument]:
    """Блок securities → список бумаг. Берём только активные (STATUS = "A")."""
    instruments = []
    for row in _rows(payload, "securities"):
        if row.get("STATUS", "A") != "A":
            continue
        board = row.get("BOARDID")
        instruments.append(Instrument(
            ticker=row["SECID"],
            name=row.get("SHORTNAME"),
            isin=row.get("ISIN"),
            board=board,
            asset_class=BOARDS.get(board),
        ))
    return instruments


def _rows(payload: dict, block: str) -> list[dict]:
    """Блок ISS {"columns": [...], "data": [[...]]} → список словарей."""
    table = payload.get(block) or {}
    columns = table.get("columns", [])
    return [dict(zip(columns, values)) for values in table.get("data", [])]


def _parse_time(text: str | None) -> datetime:
    if text:
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
    return datetime.now().replace(microsecond=0)


def _get(board: str, params: dict) -> dict:
    """Запрос к ISS. Любая сетевая ошибка → MarketDataError с понятным текстом."""
    try:
        response = requests.get(
            BASE_URL.format(board=board),
            params={"iss.meta": "off", **params},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        # parse_float=Decimal: цены сразу точными числами, без погрешностей float
        return response.json(parse_float=Decimal)
    except requests.Timeout:
        raise MarketDataError("Мосбиржа не ответила за 10 секунд. Показаны последние сохранённые цены.") from None
    except requests.RequestException:
        raise MarketDataError("Нет связи с Мосбиржей. Показаны последние сохранённые цены.") from None
    except ValueError:
        raise MarketDataError("Мосбиржа прислала непонятный ответ. Показаны последние сохранённые цены.") from None
