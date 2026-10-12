"""Список страниц приложения для меню слева.

Пункты «Главная» и «Цели» добавятся на этапе 4.
Пути указаны относительно app.py.
"""

import streamlit as st

PORTFOLIO = st.Page("ui/pages/portfolio.py", title="Портфель", icon=":material/pie_chart:", default=True)
OPERATIONS = st.Page("ui/pages/operations.py", title="Операции", icon=":material/swap_vert:")
NEW_OPERATION = st.Page("ui/pages/new_operation.py", title="Новая операция", icon=":material/add_circle:")
ACCOUNTS = st.Page("ui/pages/accounts.py", title="Счета", icon=":material/account_balance_wallet:")

ALL_PAGES = [PORTFOLIO, OPERATIONS, NEW_OPERATION, ACCOUNTS]
