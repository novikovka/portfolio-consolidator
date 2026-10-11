"""Точка входа приложения.

Запуск:  streamlit run app.py
После запуска страница откроется в браузере по адресу http://localhost:8501
"""

import streamlit as st

# Временно обращаемся к хранилищу напрямую. На шаге 1.4 появится фасад
# services/portfolio_service.py, и интерфейс будет работать только через него.
from storage.db import DatabaseUnavailable, apply_schema, list_tables

st.set_page_config(page_title="Мой портфель", layout="wide")


@st.cache_resource
def init_database() -> bool:
    """Применяет схему один раз за запуск приложения.

    Если база недоступна, результат не кэшируется — при следующем
    обновлении страницы Streamlit попробует снова.
    """
    apply_schema()
    return True


st.title("Мой портфель")

try:
    init_database()
    tables = list_tables()
except DatabaseUnavailable as error:
    st.error(str(error), icon="⚠️")
    st.stop()

st.success(f"База подключена · таблиц: {len(tables)}", icon="✅")
st.caption("Дальше — расчёт позиций (шаг 1.3).")
