"""Главная страница «Обзор»: итоги, структура портфеля и отклонения от целей (US-9, US-10).

- плашки — те же, что на «Портфеле»;
- три кольцевые диаграммы: по классам активов, по секторам (бумаги без денег), по счетам;
- крупнейшие позиции;
- предупреждение, если класс отклонился от цели больше порога.
"""

from datetime import datetime

import pandas as pd
import streamlit as st

from core.structure import CLASS_LABELS, SECTORS, UNKNOWN_SECTOR
from services.portfolio_service import QUOTES_MAX_AGE
from ui.app_state import get_service, set_flash, show_flash
from ui.formatting import fmt_datetime, fmt_money, fmt_pct, fmt_pp, fmt_qty, fmt_signed_pct
from ui.pages_registry import GOALS, NEW_OPERATION, PORTFOLIO
from ui.widgets import CLASS_COLORS, donut, show_totals

TOP_POSITIONS = 5

service = get_service()
show_flash()

head, add, action = st.columns([3, 1, 1], vertical_alignment="bottom")
head.title("Обзор")
add.page_link(NEW_OPERATION, label="Новая операция", icon=":material/add_circle:")
refresh = action.button("Обновить цены", icon=":material/refresh:", key="ov_refresh")

with st.spinner("Получаю цены с Мосбиржи…"):
    overview = service.get_overview(refresh=refresh)
view = overview.portfolio

if not view.positions and view.cash == 0:
    st.info("Портфель пока пуст. Внесите первую покупку или пополнение — и здесь появится его структура.",
            icon=":material/info:")
    st.page_link(NEW_OPERATION, label="Добавить операцию", icon=":material/add_circle:")
    st.stop()

# --- Предупреждение об отклонении от целей --------------------------------
if overview.alerts:
    details = "; ".join(
        f"{CLASS_LABELS[r.asset_class]}: {fmt_pct(r.actual, 1)} при цели {fmt_pct(r.target, 0)} ({fmt_pp(r.deviation)})"
        for r in overview.alerts
    )
    with st.container(border=True):
        st.warning(f"**Структура отклонилась от цели больше чем на {fmt_qty(overview.threshold)} п.п.** "
                   f"{details}.", icon=":material/balance:")
        st.page_link(GOALS, label="Посмотреть, что докупить или продать", icon=":material/arrow_forward:")
elif not overview.targets:
    st.caption("Целевая структура ещё не задана — задайте её на странице «Цели», "
               "и здесь появится предупреждение, когда портфель отклонится от плана.")

# --- Свежесть цен ---------------------------------------------------------
latest_price_time = max((v.price_time for v in view.positions if v.price_time), default=None)
if latest_price_time:
    st.caption(f"Цены MOEX на {fmt_datetime(latest_price_time)} (мск) · данные могут приходить с задержкой")
if view.warning:
    st.warning(view.warning, icon=":material/warning:")
elif view.fetched_at and datetime.now() - view.fetched_at > QUOTES_MAX_AGE:
    st.warning("Цены давно не обновлялись. Нажмите «Обновить цены».", icon=":material/schedule:")

show_totals(view)

# --- Структура: три диаграммы --------------------------------------------
c1, c2, c3 = st.columns(3, gap="medium")
with c1.container(border=True):
    st.subheader("Классы активов")
    st.caption("Доли от стоимости портфеля, включая деньги")
    if overview.by_class:
        donut(overview.by_class, CLASS_LABELS, CLASS_COLORS)
    else:
        st.caption("Нет данных.")
with c2.container(border=True):
    st.subheader("Сектора")
    st.caption("Доли от стоимости бумаг; облигации и фонды — одной группой")
    if overview.by_sector:
        donut(overview.by_sector, fixed_colors={CLASS_LABELS["bond"]: CLASS_COLORS["bond"],
                                                CLASS_LABELS["etf"]: CLASS_COLORS["etf"],
                                                UNKNOWN_SECTOR: "#D5DAE1"})
    else:
        st.caption("Нет бумаг с ценой.")
with c3.container(border=True):
    st.subheader("Счета")
    st.caption("Бумаги по последним ценам + деньги на счёте")
    if overview.by_account:
        donut(overview.by_account)
    else:
        st.caption("Нет данных.")

# --- Сектора акций: указываются вручную ---------------------------------------
if overview.share_sectors:
    missing = [t for t, s in overview.share_sectors.items() if not s]
    title = "Указать сектора акций" + (f" · не указано: {len(missing)}" if missing else "")
    with st.expander(title, icon=":material/category:", expanded=bool(missing)):
        st.caption("Мосбиржа не присылает сектор бумаги, поэтому он задаётся вручную — один раз для каждой акции.")
        names = service.security_names()
        options = [UNKNOWN_SECTOR, *SECTORS]
        with st.form("sectors"):
            chosen = {}
            columns = st.columns(2)
            for i, (ticker, sector) in enumerate(sorted(overview.share_sectors.items())):
                label = f"{ticker} — {names[ticker]}" if names.get(ticker) else ticker
                chosen[ticker] = columns[i % 2].selectbox(label, options, index=options.index(sector or UNKNOWN_SECTOR),
                                                          key=f"sector_{ticker}")
            if st.form_submit_button("Сохранить сектора", type="primary"):
                for ticker, sector in chosen.items():
                    new = None if sector == UNKNOWN_SECTOR else sector
                    if new != overview.share_sectors[ticker]:
                        service.set_sector(ticker, new)
                set_flash("Сектора сохранены.")
                st.rerun()

# --- Крупнейшие позиции -------------------------------------------------------
priced = sorted((v for v in view.positions if v.value is not None), key=lambda v: v.value, reverse=True)
if priced:
    st.subheader("Крупнейшие позиции")
    names = service.security_names()
    rows = [{
        "Бумага": v.position.ticker,
        "Название": names.get(v.position.ticker, ""),
        "Стоимость, ₽": fmt_money(v.value),
        "Доля": fmt_pct(v.value / view.total_value * 100, 1) if view.total_value > 0 else "—",
        "Доходность, %": fmt_signed_pct(v.pnl_pct) if v.pnl_pct is not None else "—",
    } for v in priced[:TOP_POSITIONS]]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if len(priced) > TOP_POSITIONS:
        st.page_link(PORTFOLIO, label=f"Все позиции ({len(view.positions)})", icon=":material/arrow_forward:")
