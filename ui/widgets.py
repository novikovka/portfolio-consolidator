"""Общие куски интерфейса для страниц «Обзор» и «Портфель».

- show_totals — четыре плашки с итогами (как в макете);
- donut — кольцевая диаграмма долей (Altair; ставится вместе со Streamlit);
- legend — подписи к диаграмме: цвет, название, сумма и доля.
"""

from html import escape

import altair as alt
import pandas as pd
import streamlit as st

from core.structure import Slice
from services.portfolio_service import PortfolioView
from ui.formatting import fmt_money, fmt_pct, fmt_signed_money

# Цвета классов активов — одинаковые на всех диаграммах; синий — фирменный из макетов
CLASS_COLORS = {
    "share": "#2A5BD7",    # акции
    "bond": "#F2A93B",     # облигации
    "etf": "#13804B",      # фонды
    "cash": "#AEB6C2",     # деньги
    "unknown": "#6B7280",  # класс не определён
}
# Для секторов и счетов — по кругу из этого набора
PALETTE = ["#2A5BD7", "#7FA3F0", "#F2A93B", "#13804B", "#9B6BD8", "#E05D5D", "#4FB3BF", "#C9A227",
           "#1C3F94", "#AEB6C2"]
NEGATIVE_CASH_HINT = "Внесите пополнения, чтобы видеть реальный остаток."


def show_totals(view: PortfolioView) -> None:
    """Плашки: стоимость портфеля, вложено, доходность бумаг, свободные деньги."""
    totals = view.totals
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Стоимость портфеля", f"{fmt_money(view.total_value)} ₽", border=True,
              help="Бумаги по текущим ценам + свободные деньги")
    c2.metric("Вложено в бумаги", f"{fmt_money(totals.cost)} ₽", border=True)
    if totals.pnl_pct is not None and view.positions:
        # Streamlit красит стрелку по обычному знаку «-» в начале delta: «-» — красная вниз, иначе зелёная вверх
        delta = ("-" if totals.pnl < 0 else "+") + fmt_pct(abs(totals.pnl_pct))
        c3.metric("Доходность бумаг", f"{fmt_signed_money(totals.pnl)} ₽", delta=delta, border=True)
    else:
        c3.metric("Доходность бумаг", "—", border=True)
    # Если где-то деньги в минусе, а где-то нет — показываем только то, что входит в стоимость
    cash = view.cash_counted if view.cash_counted > 0 else view.cash
    c4.metric("Свободные деньги", f"{fmt_signed_money(cash) if cash < 0 else fmt_money(cash)} ₽", border=True)
    if view.cash < view.cash_counted or view.cash < 0:
        st.caption(":orange[Деньги на счёте ушли в минус: покупки внесены, а пополнения — нет. "
                   f"Минус в стоимость портфеля не входит. {NEGATIVE_CASH_HINT}]")


def colors_for(slices: list[Slice], fixed: dict[str, str] | None = None) -> list[str]:
    """Цвет каждого куска: из fixed по ключу, иначе по кругу из PALETTE."""
    fixed = fixed or {}
    return [fixed.get(s.key, PALETTE[i % len(PALETTE)]) for i, s in enumerate(slices)]


def donut(slices: list[Slice], labels: dict[str, str] | None = None,
          fixed_colors: dict[str, str] | None = None) -> None:
    """Кольцевая диаграмма и подписи к ней. labels — как показывать ключи (share → «Акции»)."""
    labels = labels or {}
    names = [labels.get(s.key, s.key) for s in slices]
    colors = colors_for(slices, fixed_colors)
    # Altair не умеет Decimal — переводим в обычные числа только для рисования.
    # Имена колонок латиницей: так Vega-Lite точно не споткнётся о запятые и «₽»; русские — в title.
    data = pd.DataFrame({
        "group": names,
        "value": [float(s.value) for s in slices],
        "money": [f"{fmt_money(s.value)} ₽" for s in slices],
        "share": [fmt_pct(s.share, 1) for s in slices],
        "order": list(range(len(slices))),
    })
    chart = (
        alt.Chart(data)
        .mark_arc(innerRadius=58, outerRadius=100, stroke="#FFFFFF", strokeWidth=2)
        .encode(
            theta=alt.Theta("value:Q", stack=True),
            color=alt.Color("group:N", scale=alt.Scale(domain=names, range=colors), legend=None),
            order=alt.Order("order:Q"),
            tooltip=[
                alt.Tooltip("group:N", title="Группа"),
                alt.Tooltip("money:N", title="Сумма"),
                alt.Tooltip("share:N", title="Доля"),
            ],
        )
        .properties(height=220)
    )
    st.altair_chart(chart)
    legend(slices, names, colors)


def legend(slices: list[Slice], names: list[str], colors: list[str]) -> None:
    """Подписи под диаграммой: ● Акции — 7 000,00 ₽ · 70,0 %."""
    lines = [
        f'<div style="display:flex;justify-content:space-between;gap:8px;font-size:0.9rem;line-height:1.8">'
        f'<span><span style="color:{color}">●</span> {escape(name)}</span>'
        f'<span style="color:#5B6474">{fmt_money(s.value)} ₽ · <b style="color:#1C2230">{fmt_pct(s.share, 1)}</b></span>'
        f'</div>'
        for s, name, color in zip(slices, names, colors)
    ]
    st.markdown("".join(lines), unsafe_allow_html=True)
