"""Страница «Портфель»: позиции, пересчитанные из операций.

Текущие цены, стоимость и доходность появятся на этапе 2.
"""

import pandas as pd
import streamlit as st

from ui.app_state import get_service, show_flash
from ui.formatting import fmt_money, fmt_price, fmt_qty
from ui.pages_registry import NEW_OPERATION

service = get_service()
show_flash()

st.title("Портфель")
st.caption("Позиции пересчитываются из операций. Текущие цены и доходность появятся на этапе 2.")

# Переключатель счетов показываем, только когда счетов больше одного (этап 3)
accounts = service.list_accounts()
account_id = None
if len(accounts) > 1:
    names = {"Все счета": None} | {a.name: a.id for a in accounts}
    choice = st.segmented_control("Счёт", list(names), default="Все счета")
    account_id = names.get(choice)

positions = service.get_positions(account_id=account_id)

if not positions:
    st.info("Позиций пока нет. Внесите первую покупку — и она появится здесь.", icon=":material/info:")
    st.page_link(NEW_OPERATION, label="Добавить операцию", icon=":material/add_circle:")
    st.stop()

total_cost = sum(p.cost for p in positions)

col1, col2 = st.columns(2)
col1.metric("Вложено в бумаги", f"{fmt_money(total_cost)} ₽")
col2.metric("Бумаг в портфеле", len(positions))

table = pd.DataFrame(
    [
        {
            "Бумага": p.ticker,
            "Количество": fmt_qty(p.quantity),
            "Средняя цена, ₽": fmt_price(p.avg_price),
            "Вложено, ₽": fmt_money(p.cost),
            "Доля, %": fmt_money(p.cost / total_cost * 100, 1),
        }
        for p in positions
    ]
)
st.dataframe(table, hide_index=True, width="stretch")

st.caption("Средняя цена включает комиссии. Доля считается от вложенной суммы.")
