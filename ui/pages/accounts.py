"""Страница «Счета»: брокерские счета и ИИС, которые собираются в общий портфель.

Создать, переименовать, удалить пустой счёт. Стоимость бумаг — по последним
сохранённым ценам (обновить их можно на странице «Портфель»).
"""

from decimal import Decimal

import streamlit as st

from core.models import Account
from core.structure import counted_cash
from services.portfolio_service import AccountError
from ui.app_state import get_service, set_flash, show_flash
from ui.formatting import fmt_money, fmt_pct, fmt_signed_money, plural

TYPES = {"broker": "Брокерский", "iis": "ИИС"}

service = get_service()
service.get_default_account()  # при первом запуске появится «Основной счёт»


@st.dialog("Изменить счёт")
def edit_dialog(account: Account) -> None:
    with st.form("edit_account"):
        name = st.text_input("Название", value=account.name)
        broker = st.text_input("Брокер", value=account.broker)
        account_type = st.radio(
            "Тип счёта", list(TYPES), index=list(TYPES).index(account.account_type),
            format_func=TYPES.get, horizontal=True,
        )
        submitted = st.form_submit_button("Сохранить", type="primary")
    if submitted:
        try:
            service.update_account(Account(account.id, name, broker, account_type))
        except AccountError as error:
            st.error(str(error), icon=":material/error:")
        else:
            set_flash("Счёт изменён.")
            st.rerun()


@st.dialog("Удалить счёт?")
def delete_dialog(account: Account) -> None:
    st.write(f"«{account.name}» · {account.broker}")
    c1, c2 = st.columns(2)
    if c1.button("Да, удалить", type="primary", key="confirm_delete_account"):
        try:
            service.delete_account(account.id)
        except AccountError as error:
            st.error(str(error), icon=":material/error:")
        else:
            set_flash("Счёт удалён.")
            st.rerun()
    if c2.button("Отмена", key="cancel_delete_account"):
        st.rerun()


show_flash()
st.title("Счета")
st.caption("Брокерские счета и ИИС, которые собираются в общий портфель. Стоимость — по последним сохранённым ценам.")

summaries = service.account_summaries()


def counted(summary) -> Decimal:
    """Стоимость счёта: бумаги + деньги; минус на счёте в стоимость не входит (как на «Портфеле»)."""
    return summary.value + counted_cash(summary.cash)


total = sum((counted(s) for s in summaries), Decimal("0"))

cards = st.columns(min(3, len(summaries) + 1))
for i, summary in enumerate(summaries):
    account = summary.account
    with cards[i % len(cards)].container(border=True):
        head, badge = st.columns([3, 1])
        head.subheader(account.name)
        badge.caption(fmt_pct(counted(summary) / total * 100, 1) if total > 0 else "—")
        st.caption(f"{account.broker} · {TYPES.get(account.account_type, account.account_type)}")
        st.metric("Стоимость", f"{fmt_money(counted(summary))} ₽", label_visibility="collapsed")
        a, b, c = st.columns(3)
        a.caption(f"Бумаг\n\n**{summary.securities}**")
        b.caption(f"Деньги\n\n**{fmt_signed_money(summary.cash) if summary.cash < 0 else fmt_money(summary.cash)} ₽**")
        c.caption(f"Операций\n\n**{summary.operations}**")
        e, d = st.columns(2)
        if e.button("Изменить", icon=":material/edit:", key=f"edit_acc_{account.id}"):
            edit_dialog(account)
        if d.button(
            "Удалить", icon=":material/delete:", key=f"del_acc_{account.id}",
            disabled=summary.operations > 0 or len(summaries) == 1,
            help="Удалить можно только пустой счёт" if summary.operations else None,
        ):
            delete_dialog(account)

# --- Новый счёт -----------------------------------------------------------
with cards[len(summaries) % len(cards)].container(border=True):
    st.subheader("Новый счёт")
    with st.form("new_account", clear_on_submit=True):
        name = st.text_input("Название", placeholder="Например, ВТБ брокерский")
        broker = st.text_input("Брокер", placeholder="ВТБ")
        account_type = st.radio("Тип счёта", list(TYPES), format_func=TYPES.get, horizontal=True)
        submitted = st.form_submit_button("Добавить счёт", type="primary")
    if submitted:
        try:
            created = service.add_account(name, broker, account_type)
        except AccountError as error:
            st.error(str(error), icon=":material/error:")
        else:
            set_flash(f"Счёт «{created.name}» добавлен.")
            st.rerun()

st.caption(f"Всего: {plural(len(summaries), 'счёт', 'счёта', 'счетов')}.")
