"""Общие объекты интерфейса: фасад и «вспышки» — сообщения после действия.

Здесь фасад собирается вместе с хранилищем PostgreSQL. Страницы получают
его через get_service() и ничего не знают о базе.
"""

import streamlit as st

from services.portfolio_service import PortfolioService
from storage.postgres_repository import PostgresRepository

_FLASH_KEY = "flash_message"


@st.cache_resource
def get_service() -> PortfolioService:
    """Один фасад на всё приложение."""
    return PortfolioService(PostgresRepository())


def set_flash(message: str) -> None:
    """Запомнить сообщение, чтобы показать его после перехода или перезагрузки страницы."""
    st.session_state[_FLASH_KEY] = message


def show_flash() -> None:
    """Показать сохранённое сообщение один раз."""
    message = st.session_state.pop(_FLASH_KEY, None)
    if message:
        st.success(message, icon=":material/check_circle:")
