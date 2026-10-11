"""Точка входа приложения.

Запуск:  streamlit run app.py
После запуска страница откроется в браузере по адресу http://localhost:8501
"""

import streamlit as st

st.set_page_config(page_title="Мой портфель", layout="wide")

st.title("Мой портфель")
st.caption("Каркас приложения готов. Дальше — схема базы данных (шаг 1.2).")
