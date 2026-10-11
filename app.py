"""Точка входа приложения.

Запуск:  streamlit run app.py
После запуска страница откроется в браузере по адресу http://localhost:8501

Здесь: настройка страницы, подготовка базы, логотип и меню. Сами страницы — в ui/pages/.
Цвета и скругления — в .streamlit/config.toml.
"""

import streamlit as st

from storage.db import DatabaseUnavailable, apply_schema
from ui.app_state import get_service
from ui.formatting import plural
from ui.pages_registry import ALL_PAGES

st.set_page_config(page_title="Мой портфель", page_icon=":material/trending_up:", layout="wide")
st.logo("ui/assets/logo.svg", icon_image="ui/assets/icon.svg", size="large")


@st.cache_resource
def init_database() -> bool:
    """Применяет схему один раз за запуск приложения.

    Если база недоступна, результат не кэшируется — при следующем
    обновлении страницы Streamlit попробует снова.
    """
    apply_schema()
    return True


def show_database_error(error: DatabaseUnavailable) -> None:
    st.title("Мой портфель")
    st.error(str(error), icon=":material/warning:")


try:
    init_database()
except DatabaseUnavailable as error:
    show_database_error(error)
    st.stop()

page = st.navigation(ALL_PAGES)

try:
    service = get_service()
    accounts = len(service.list_accounts())
    securities = len(service.get_positions())
    with st.sidebar:
        st.caption(f"{plural(accounts, 'счёт', 'счёта', 'счетов')} · {plural(securities, 'бумага', 'бумаги', 'бумаг')}")
    page.run()
except DatabaseUnavailable as error:
    # База остановилась уже во время работы приложения
    show_database_error(error)
