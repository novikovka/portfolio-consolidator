"""Страница «Цели»: целевая структура портфеля и ребалансировка (US-10).

- целевые доли четырёх классов (акции, облигации, фонды, деньги), в сумме 100 %;
- порог: при каком отклонении показывать предупреждение на «Обзоре»;
- таблица факт / цель / отклонение / сколько докупить или продать.

Таблица пересчитывается сразу при вводе — видно, что будет, ещё до сохранения.
"""

from decimal import Decimal

import pandas as pd
import streamlit as st

from core.structure import CLASS_LABELS, TARGET_CLASSES, check_targets, over_threshold, rebalance
from services.portfolio_service import TargetsError
from ui.app_state import get_service, set_flash, show_flash
from ui.formatting import fmt_money, fmt_pct, fmt_pp, fmt_qty

GAIN = "#13804B"
LOSS = "#C23A2B"
WARN = "#B26A00"

service = get_service()
show_flash()

st.title("Цели")
st.caption("Задайте, какой должна быть структура портфеля. Если какой-то класс отклонится больше порога, "
           "на странице «Обзор» появится предупреждение, а здесь — подсказка, что докупить или продать.")

saved = service.get_targets()
saved_threshold = service.get_threshold()

# Начальные значения полей — из сохранённых целей (или нули, если целей ещё нет)
for asset_class in TARGET_CLASSES:
    st.session_state.setdefault(f"goal_{asset_class}", float(saved.get(asset_class, 0)))
st.session_state.setdefault("goal_threshold", float(saved_threshold))

# --- Ввод целей ---------------------------------------------------------------
with st.container(border=True):
    st.subheader("Целевая структура")
    columns = st.columns(len(TARGET_CLASSES))
    targets = {}
    for column, asset_class in zip(columns, TARGET_CLASSES):
        value = column.number_input(f"{CLASS_LABELS[asset_class]}, %", min_value=0.0, max_value=100.0,
                                    step=5.0, format="%.1f", key=f"goal_{asset_class}")
        # number_input отдаёт float; округляем до десятых и переводим в точное Decimal
        targets[asset_class] = Decimal(str(round(value, 1)))

    total = sum(targets.values(), Decimal("0"))
    errors = check_targets(targets)
    left, right = st.columns([2, 1], vertical_alignment="bottom")
    if errors:
        left.markdown(f"Сумма долей: **:red[{fmt_pct(total, 1)}]** — должна быть ровно 100 %.")
    else:
        left.markdown(f"Сумма долей: **:green[{fmt_pct(total, 1)}]** ✓")
    threshold_value = right.number_input(
        "Порог предупреждения, п.п.", min_value=0.5, max_value=100.0, step=0.5, format="%.1f",
        key="goal_threshold",
        help="Если доля класса отличается от цели больше чем на столько процентных пунктов, "
             "на «Обзоре» появится предупреждение.",
    )
    threshold = Decimal(str(round(threshold_value, 1)))

    if st.button("Сохранить цели", type="primary", disabled=bool(errors)):
        try:
            service.save_targets(targets, threshold)
        except TargetsError as error:
            for message in error.errors:
                st.error(message, icon=":material/error:")
        else:
            set_flash("Цели сохранены.")
            st.rerun()

    changed = not saved or any(targets[c] != saved.get(c, Decimal("0")) for c in TARGET_CLASSES) \
        or threshold != saved_threshold
    if not saved:
        st.caption("Цели ещё не сохранены.")
    elif changed:
        st.caption(":orange[Есть несохранённые изменения.]")

# --- Факт и цель ----------------------------------------------------------
st.subheader("Факт и цель")
with st.spinner("Получаю цены с Мосбиржи…"):
    overview = service.get_overview()
class_totals = {s.key: s.value for s in overview.by_class}
portfolio_value = overview.portfolio.total_value

if portfolio_value <= 0:
    st.info("Портфель пока пуст — сравнивать не с чем. Внесите операции, и здесь появится расчёт.",
            icon=":material/info:")
    st.stop()
if errors:
    st.info("Расчёт появится, когда сумма целевых долей будет 100 %.", icon=":material/info:")
    st.stop()

rows = rebalance(class_totals, targets)
alerts = {r.asset_class for r in over_threshold(rows, threshold)}


def action(amount: Decimal) -> str:
    """Сумма ребалансировки словами. Меньше рубля — не считаем."""
    if amount >= 1:
        return f"Докупить на {fmt_money(amount)} ₽"
    if amount <= -1:
        return f"Продать на {fmt_money(-amount)} ₽"
    return "—"


table = pd.DataFrame([{
    "Класс": CLASS_LABELS[r.asset_class],
    "Стоимость, ₽": fmt_money(r.value),
    "Факт": fmt_pct(r.actual, 1),
    "Цель": fmt_pct(r.target, 1),
    "Отклонение": fmt_pp(r.deviation),
    "Что сделать": action(r.rebalance),
} for r in rows])


def highlight(row: pd.Series) -> list[str]:
    """Строки с отклонением больше порога — оранжевым, «докупить» — зелёным, «продать» — красным."""
    over = rows[row.name].asset_class in alerts
    styles = []
    for column in row.index:
        if column == "Отклонение" and over:
            styles.append(f"color: {WARN}; font-weight: 600")
        elif column == "Что сделать" and over:
            styles.append(f"color: {GAIN if rows[row.name].rebalance > 0 else LOSS}; font-weight: 600")
        else:
            styles.append("")
    return styles


st.dataframe(table.style.apply(highlight, axis=1), hide_index=True, width="stretch")

unknown = class_totals.get("unknown")
st.caption(
    f"Стоимость портфеля {fmt_money(portfolio_value)} ₽. Отклонение = факт − цель. "
    f"Сумма = цель × стоимость портфеля − текущая стоимость класса. Порог — {fmt_qty(threshold)} п.п."
    + (f" Бумаги без класса ({fmt_money(unknown)} ₽) входят в стоимость, но цели для них нет." if unknown else "")
)
if alerts:
    st.caption("Подсказка показывает, как вернуться точно к цели. Продавать не обязательно: "
               "можно направить новые пополнения в класс, которого не хватает.")
