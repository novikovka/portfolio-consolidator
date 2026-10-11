"""Страница «Портфель»: позиции с текущими ценами Мосбиржи, стоимость и доходность."""

from datetime import datetime

import pandas as pd
import streamlit as st

from services.portfolio_service import QUOTES_MAX_AGE
from ui.app_state import get_service, show_flash
from ui.formatting import fmt_datetime, fmt_money, fmt_pct, fmt_price, fmt_qty, fmt_signed_money, fmt_signed_pct
from ui.pages_registry import NEW_OPERATION

GAIN = "#13804B"
LOSS = "#C23A2B"

service = get_service()
show_flash()

# --- Заголовок с кнопкой справа, как в макете -----------------------------
head, action = st.columns([4, 1], vertical_alignment="bottom")
head.title("Портфель")
refresh = action.button("Обновить цены", icon=":material/refresh:", key="refresh_prices")

# Переключатель счетов — только когда счетов больше одного (этап 3)
accounts = service.list_accounts()
account_id = None
if len(accounts) > 1:
    names = {"Все счета": None} | {a.name: a.id for a in accounts}
    choice = st.segmented_control("Счёт", list(names), default="Все счета")
    account_id = names.get(choice)

with st.spinner("Получаю цены с Мосбиржи…"):
    view = service.get_portfolio(account_id=account_id, refresh=refresh)

if not view.positions:
    st.caption("Позиции пересчитываются из операций.")
    st.info("Позиций пока нет. Внесите первую покупку — и она появится здесь.", icon=":material/info:")
    st.page_link(NEW_OPERATION, label="Добавить операцию", icon=":material/add_circle:")
    st.stop()

# --- Откуда цены и насколько свежие --------------------------------------
latest_price_time = max((v.price_time for v in view.positions if v.price_time), default=None)
if latest_price_time:
    st.caption(
        f"Цены MOEX на {fmt_datetime(latest_price_time)} (мск)"
        + (f" · обновлено {view.fetched_at:%H:%M}" if view.fetched_at else "")
        + " · данные могут приходить с задержкой"
    )
if view.warning:
    st.warning(view.warning, icon=":material/warning:")
elif view.fetched_at and datetime.now() - view.fetched_at > QUOTES_MAX_AGE:
    st.warning("Цены давно не обновлялись. Нажмите «Обновить цены».", icon=":material/schedule:")

# --- Плашки с итогами -----------------------------------------------------
totals = view.totals
c1, c2, c3, c4 = st.columns(4)
c1.metric("Стоимость бумаг", f"{fmt_money(totals.value)} ₽", border=True)
c2.metric("Вложено", f"{fmt_money(totals.cost)} ₽", border=True)
if totals.pnl_pct is not None:
    # Streamlit красит стрелку по обычному знаку «-» в начале delta: «-» — красная вниз, иначе зелёная вверх
    delta = ("-" if totals.pnl < 0 else "+") + fmt_pct(abs(totals.pnl_pct))
    c3.metric("Доходность", f"{fmt_signed_money(totals.pnl)} ₽", delta=delta, border=True)
else:
    c3.metric("Доходность", "—", border=True)
c4.metric("Бумаг в портфеле", len(view.positions), border=True)

# --- Таблица позиций ------------------------------------------------------
names = service.security_names()
total_value = totals.value


def color_sign(text: str) -> str:
    """Зелёный для «+», красный для «−» — как в макете."""
    if text.startswith("+"):
        return f"color: {GAIN}; font-weight: 600"
    if text.startswith("−"):
        return f"color: {LOSS}; font-weight: 600"
    return ""


rows = []
for v in view.positions:
    p = v.position
    rows.append({
        "Бумага": p.ticker,
        "Название": names.get(p.ticker, ""),
        "Кол-во": fmt_qty(p.quantity),
        "Средняя цена, ₽": fmt_price(p.avg_price),
        "Текущая цена, ₽": fmt_price(v.price) if v.price is not None else "нет цены",
        "Стоимость, ₽": fmt_money(v.value) if v.value is not None else "—",
        "Доходность, ₽": fmt_signed_money(v.pnl) if v.pnl is not None else "—",
        "Доходность, %": fmt_signed_pct(v.pnl_pct) if v.pnl_pct is not None else "—",
        "Доля": fmt_pct(v.value / total_value * 100, 1) if v.value is not None and total_value else "—",
    })

table = pd.DataFrame(rows).style.map(color_sign, subset=["Доходность, ₽", "Доходность, %"])
st.dataframe(table, hide_index=True, width="stretch")

st.caption(
    "Средняя цена включает комиссии. Доля — от стоимости бумаг. "
    "Облигации и деньги на счёте появятся на этапе 3."
)
