"""Страница «Портфель»: позиции с текущими ценами Мосбиржи, стоимость и доходность."""

from datetime import datetime

import pandas as pd
import streamlit as st

from services.portfolio_service import QUOTES_MAX_AGE
from ui.app_state import get_service, show_flash
from ui.formatting import (
    fmt_avg_price, fmt_bond_pct, fmt_datetime, fmt_money, fmt_pct, fmt_price, fmt_qty,
    fmt_signed_money, fmt_signed_pct,
)
from ui.pages_registry import NEW_OPERATION
from ui.widgets import show_totals

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

if not view.positions and view.cash == 0:
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

# --- Плашки с итогами (как в макете) -------------------------------------
totals = view.totals
cash_counted = view.cash_counted  # отрицательный остаток счёта в стоимость не входит
show_totals(view)

# --- Таблица позиций ------------------------------------------------------
names = service.security_names()
share_base = totals.value + cash_counted


def color_sign(text: str) -> str:
    """Зелёный для «+», красный для «−» — как в макете."""
    if text.startswith("+"):
        return f"color: {GAIN}; font-weight: 600"
    if text.startswith("\u2212"):
        return f"color: {LOSS}; font-weight: 600"
    return ""


def share(value) -> str:
    return fmt_pct(value / share_base * 100, 1) if value is not None and share_base > 0 else "—"


rows = []
for v in view.positions:
    p = v.position
    if v.is_bond:
        avg = fmt_bond_pct(p.avg_price / v.face_value * 100)
        current = fmt_bond_pct(v.price) if v.price is not None else "нет цены"
    else:
        avg = f"{fmt_avg_price(p.avg_price)} ₽"
        current = f"{fmt_price(v.price)} ₽" if v.price is not None else "нет цены"
    rows.append({
        "Бумага": p.ticker,
        "Название": names.get(p.ticker, ""),
        "Кол-во": fmt_qty(p.quantity),
        "Средняя цена": avg,
        "Текущая цена": current,
        "Стоимость, ₽": fmt_money(v.value) if v.value is not None else "—",
        "Доходность, ₽": fmt_signed_money(v.pnl) if v.pnl is not None else "—",
        "Доходность, %": fmt_signed_pct(v.pnl_pct) if v.pnl_pct is not None else "—",
        "НКД, ₽": fmt_money(v.accrued) if v.accrued is not None else "",
        "Доля": share(v.value),
    })

# Строка «Деньги» и итог — как в макете
empty = {key: "" for key in rows[0]} if rows else {}
if view.cash != 0:
    rows.append(empty | {
        "Бумага": "Деньги", "Название": "рубли на счетах",
        "Стоимость, ₽": fmt_money(cash_counted) if cash_counted > 0 else fmt_signed_money(view.cash),
        "Доля": share(cash_counted) if cash_counted > 0 else "—",
    })
if view.positions:
    rows.append(empty | {
        "Бумага": "Итого",
        "Стоимость, ₽": fmt_money(view.total_value),
        "Доходность, ₽": fmt_signed_money(totals.pnl),
        "Доходность, %": fmt_signed_pct(totals.pnl_pct) if totals.pnl_pct is not None else "—",
        "НКД, ₽": fmt_money(sum(v.accrued for v in view.positions if v.accrued is not None))
                  if any(v.accrued is not None for v in view.positions) else "",
        "Доля": "100 %" if share_base > 0 else "—",
    })

table = pd.DataFrame(rows)
if not any(v.is_bond for v in view.positions):
    table = table.drop(columns=["НКД, ₽"], errors="ignore")
colored = [c for c in ("Доходность, ₽", "Доходность, %") if c in table.columns]
styled = table.style.map(color_sign, subset=colored) if colored else table
st.dataframe(styled, hide_index=True, width="stretch")

st.caption(
    "Средняя цена включает комиссии; у облигаций цены — в % от номинала, "
    "НКД показан отдельно и в стоимость не входит. Доля — от стоимости портфеля."
)
