"""Список страниц приложения для меню слева.

Пути указаны относительно app.py. Первая страница с default=True открывается при запуске.
"""

import streamlit as st

OVERVIEW = st.Page("ui/pages/overview.py", title="Обзор", icon=":material/dashboard:", default=True)
PORTFOLIO = st.Page("ui/pages/portfolio.py", title="Портфель", icon=":material/pie_chart:")
OPERATIONS = st.Page("ui/pages/operations.py", title="Операции", icon=":material/swap_vert:")
NEW_OPERATION = st.Page("ui/pages/new_operation.py", title="Новая операция", icon=":material/add_circle:")
ACCOUNTS = st.Page("ui/pages/accounts.py", title="Счета", icon=":material/account_balance_wallet:")
GOALS = st.Page("ui/pages/goals.py", title="Цели", icon=":material/track_changes:")

ALL_PAGES = [OVERVIEW, PORTFOLIO, OPERATIONS, NEW_OPERATION, ACCOUNTS, GOALS]
