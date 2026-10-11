"""Общие объекты интерфейса: фасад, список бумаг и «вспышки» — сообщения после действия.

Здесь фасад собирается вместе с хранилищем PostgreSQL и источником цен MOEX.
Страницы получают его через get_service() и ничего не знают о базе и бирже.
"""

import streamlit as st

from core.models import Instrument, Quote
from market.moex_provider import MoexPriceProvider
from market.price_provider import MarketDataError
from services.portfolio_service import PortfolioService
from storage.postgres_repository import PostgresRepository

_FLASH_KEY = "flash_message"


@st.cache_resource
def get_service() -> PortfolioService:
    """Один фасад на всё приложение."""
    return PortfolioService(PostgresRepository(), MoexPriceProvider())


@st.cache_data(ttl="1d", show_spinner="Загружаю список бумаг с Мосбиржи…")
def _cached_instruments() -> list[Instrument]:
    return get_service().list_instruments()


def load_instruments() -> list[Instrument]:
    """Список акций и фондов для выпадающего списка. Хранится сутки.

    Если биржа недоступна, возвращает пустой список (ошибка не кэшируется,
    поэтому при следующем открытии страницы будет новая попытка).
    """
    try:
        return _cached_instruments()
    except MarketDataError:
        return []


@st.cache_data(ttl=60, show_spinner=False)
def quote_for(instrument: Instrument) -> Quote | None:
    """Текущая цена бумаги для формы. Запоминается на минуту, чтобы не ходить
    на биржу при каждом нажатии клавиши в форме."""
    return get_service().get_quote(instrument)


def set_flash(message: str) -> None:
    """Запомнить сообщение, чтобы показать его после перехода или перезагрузки страницы."""
    st.session_state[_FLASH_KEY] = message


def show_flash() -> None:
    """Показать сохранённое сообщение один раз."""
    message = st.session_state.pop(_FLASH_KEY, None)
    if message:
        st.success(message, icon=":material/check_circle:")
