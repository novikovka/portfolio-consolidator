"""Страница «Операции»: журнал с фильтрами, правкой и удалением.

Streamlit не умеет кнопки внутри строк таблицы, поэтому строку выбирают
кликом, а под таблицей — кнопки «Изменить» и «Удалить».
"""

import pandas as pd
import streamlit as st

from core.calculations import OversellError, cash_flow
from core.models import Operation, OpType
from services.portfolio_service import OperationNotFound
from ui.app_state import get_service, set_flash, show_flash
from ui.formatting import (
    OP_TYPE_LABELS, fmt_bond_pct, fmt_datetime, fmt_input, fmt_money, fmt_price, fmt_qty, fmt_signed_money,
)
from ui.operation_form import TICKER_TYPES, TRADE_TYPES, build_operation
from ui.pages_registry import NEW_OPERATION

service = get_service()
accounts = service.list_accounts()
account_names = {a.id: a.name for a in accounts}


def price_label(op: Operation) -> str:
    """Цена для журнала: облигации — в % от номинала, остальное — в рублях."""
    return fmt_bond_pct(op.price) if op.is_bond else f"{fmt_price(op.price)} ₽"


def describe(op: Operation) -> str:
    """Короткое описание операции для окон подтверждения."""
    parts = [OP_TYPE_LABELS[op.op_type], op.ticker or ""]
    if op.quantity is not None:
        parts.append(f"{fmt_qty(op.quantity)} шт. по {price_label(op)}")
    elif op.amount is not None:
        parts.append(f"{fmt_money(op.amount)} ₽")
    parts.append(fmt_datetime(op.op_datetime))
    return " · ".join(p for p in parts if p)


@st.dialog("Изменить операцию")
def edit_dialog(op: Operation) -> None:
    """Правка операции. Тип не меняется — чтобы сменить тип, удалите операцию и внесите заново."""
    is_trade = op.op_type in TRADE_TYPES
    with st.form("edit_operation"):
        st.caption(f"Тип: **{OP_TYPE_LABELS[op.op_type]}**")
        account = st.selectbox(
            "Счёт", accounts, format_func=lambda a: a.name,
            index=next(i for i, a in enumerate(accounts) if a.id == op.account_id),
        )
        c1, c2 = st.columns(2)
        trade_date = c1.date_input("Дата", value=op.op_datetime.date(), format="DD.MM.YYYY")
        trade_time = c2.time_input("Время", value=op.op_datetime.time(), step=60)
        ticker = st.text_input("Тикер", value=op.ticker or "") if op.op_type in TICKER_TYPES else ""
        quantity_text = price_text = fee_text = accrued_text = amount_text = ""
        if is_trade:
            c3, c4, c5 = st.columns(3)
            quantity_text = c3.text_input("Количество, шт.", value=fmt_input(op.quantity))
            price_text = c4.text_input(
                "Цена, % от номинала" if op.is_bond else "Цена за 1 шт., ₽", value=fmt_input(op.price),
            )
            fee_text = c5.text_input("Комиссия, ₽", value=fmt_input(op.fee))
            if op.is_bond:
                accrued_text = st.text_input("НКД за всю сделку, ₽", value=fmt_input(op.accrued_interest))
        else:
            amount_text = st.text_input("Сумма, ₽", value=fmt_input(op.amount))
        note = st.text_area("Заметка", value=op.note or "", max_chars=1000, height=80)
        submitted = st.form_submit_button("Сохранить изменения", type="primary")

    if submitted:
        updated, errors = build_operation(
            account_id=account.id, op_type=op.op_type, trade_date=trade_date, trade_time=trade_time,
            ticker=ticker, quantity_text=quantity_text, price_text=price_text, fee_text=fee_text,
            amount_text=amount_text, accrued_text=accrued_text, face_value=op.face_value,
            note=note, operation_id=op.id,
        )
        for message in errors:
            st.error(message, icon=":material/error:")
        if updated is not None:
            try:
                service.update_operation(updated)
            except (OversellError, OperationNotFound) as error:
                st.error(str(error), icon=":material/error:")
            else:
                set_flash("Операция изменена, позиции пересчитаны.")
                st.rerun()


@st.dialog("Удалить операцию?")
def delete_dialog(op: Operation) -> None:
    st.write(describe(op))
    st.caption("Позиции пересчитаются автоматически. Удаление нельзя отменить.")
    c1, c2 = st.columns(2)
    if c1.button("Да, удалить", type="primary", key="confirm_delete"):
        try:
            service.delete_operation(op.id)
        except (OversellError, OperationNotFound) as error:
            st.error(str(error), icon=":material/error:")
        else:
            set_flash("Операция удалена, позиции пересчитаны.")
            st.rerun()
    if c2.button("Отмена", key="cancel_delete"):
        st.rerun()


# --- Заголовок ------------------------------------------------------------
show_flash()
head, action = st.columns([4, 1], vertical_alignment="bottom")
head.title("Операции")
action.page_link(NEW_OPERATION, label="Новая операция", icon=":material/add_circle:")
st.caption("Журнал сделок: новые сверху.")

all_operations = service.list_operations()
if not all_operations:
    st.info("Операций пока нет.", icon=":material/info:")
    st.page_link(NEW_OPERATION, label="Добавить первую операцию", icon=":material/add_circle:")
    st.stop()

# --- Фильтры --------------------------------------------------------------
f1, f2, f3 = st.columns([2, 2, 3])
account_options = {"Все счета": None} | {a.name: a.id for a in accounts}
account_choice = f1.selectbox("Счёт", list(account_options))
type_options = {"Все типы": None} | {OP_TYPE_LABELS[t]: t for t in OpType}
type_choice = f2.selectbox("Тип", list(type_options))
search = f3.text_input("Поиск", placeholder="Тикер или слово из заметки").strip().lower()

operations = service.list_operations(account_id=account_options[account_choice])
if type_options[type_choice] is not None:
    operations = [op for op in operations if op.op_type == type_options[type_choice]]
if search:
    operations = [
        op for op in operations
        if search in (op.ticker or "").lower() or search in (op.note or "").lower()
    ]

if not operations:
    st.info("Под фильтры ничего не подходит.", icon=":material/filter_alt_off:")
    st.stop()

# --- Таблица --------------------------------------------------------------
table = pd.DataFrame(
    [
        {
            "Дата и время": fmt_datetime(op.op_datetime),
            "Счёт": account_names.get(op.account_id, "—"),
            "Тип": OP_TYPE_LABELS[op.op_type],
            "Бумага": op.ticker or "—",
            "Кол-во": fmt_qty(op.quantity) if op.quantity is not None else "—",
            "Цена": price_label(op) if op.price is not None else "—",
            "Комиссия, ₽": fmt_money(op.fee) if op.op_type in TRADE_TYPES else "—",
            "НКД, ₽": fmt_money(op.accrued_interest) if op.accrued_interest else "—",
            "Сумма, ₽": fmt_signed_money(cash_flow(op)),
            "Заметка": op.note or "",
        }
        for op in operations
    ]
)
event = st.dataframe(
    table, hide_index=True, width="stretch",
    on_select="rerun", selection_mode="single-row", key="journal_table",
)

rows = event.selection.rows
selected = operations[rows[0]] if rows and rows[0] < len(operations) else None

b1, b2, hint = st.columns([1, 1, 4], vertical_alignment="center")
if b1.button("Изменить", icon=":material/edit:", disabled=selected is None, key="edit_selected"):
    edit_dialog(selected)
if b2.button("Удалить", icon=":material/delete:", disabled=selected is None, key="delete_selected"):
    delete_dialog(selected)
hint.caption(
    f"Выбрано: {describe(selected)}" if selected
    else f"Операций: {len(operations)}. Кликните по строке, чтобы изменить или удалить её."
)
