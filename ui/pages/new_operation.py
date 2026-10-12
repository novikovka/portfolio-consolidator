"""Страница «Новая операция»: покупка, продажа, пополнение, вывод, дивиденд, купон.

Поля зависят от типа (REQUIREMENTS 3.6):
- покупка и продажа — бумага из списка Мосбиржи (акции, фонды, облигации),
  количество, цена, комиссия; для облигаций цена в % от номинала и поле НКД;
- пополнение и вывод — сумма;
- дивиденд и купон — бумага и сумма.

Поля стоят вне st.form, чтобы сумма и блок «После сохранения»
пересчитывались сразу при вводе.
"""

from datetime import date, datetime

import streamlit as st

from core.calculations import OversellError, cash_flow
from core.models import OpType
from ui.app_state import get_service, load_instruments, quote_for, set_flash, show_flash
from ui.formatting import (
    OP_TYPE_LABELS, fmt_avg_price, fmt_bond_pct, fmt_input, fmt_money, fmt_price, fmt_qty,
    fmt_signed_money, parse_decimal,
)
from ui.operation_form import TICKER_TYPES, TRADE_TYPES, build_operation
from ui.pages_registry import OPERATIONS

TYPES = {OP_TYPE_LABELS[t]: t for t in OpType}
CLEARED_FIELDS = {
    "nf_ticker_text": "", "nf_qty": "", "nf_price": "", "nf_fee": "0",
    "nf_accrued": "", "nf_amount": "", "nf_note": "",
}
NEGATIVE_CASH_HINT = "Внесите пополнения, чтобы видеть реальный остаток."


def fill_field(key: str, value) -> None:
    """Кнопки «Подставить …»: записывают значение в поле до его отрисовки."""
    st.session_state[key] = fmt_input(value)


def quiet_decimal(text: str):
    """Число из поля без ошибок: если не разобралось — None."""
    try:
        return parse_decimal(text)
    except ValueError:
        return None


service = get_service()
default_account = service.get_default_account()
accounts = service.list_accounts()

# --- Начальные значения полей (до создания виджетов) -----------------------
for key, value in CLEARED_FIELDS.items():
    st.session_state.setdefault(key, value)
st.session_state.setdefault("nf_date", date.today())
st.session_state.setdefault("nf_time", datetime.now().time().replace(second=0, microsecond=0))

# «Сохранить и добавить ещё»: очищаем поля, но оставляем тип, счёт, дату и время
if st.session_state.pop("nf_clear", False):
    for key, value in CLEARED_FIELDS.items():
        st.session_state[key] = value
    st.session_state.pop("nf_ticker", None)  # выпадающий список бумаг — снова пустой

show_flash()

st.title("Новая операция")
st.caption("Внесите операцию, которую совершили у брокера, — портфель пересчитается сразу после сохранения.")

form_col, side_col = st.columns([3, 2], gap="large")

# --- Форма ----------------------------------------------------------------
with form_col:
    type_label = st.radio("Тип операции", list(TYPES), horizontal=True, key="nf_type")
    op_type = TYPES[type_label]
    is_trade = op_type in TRADE_TYPES

    c1, c2, c3 = st.columns([2, 2, 1])
    account = c1.selectbox(
        "Счёт", accounts, format_func=lambda a: a.name,
        index=accounts.index(default_account), key="nf_account",
    )
    trade_date = c2.date_input("Дата", format="DD.MM.YYYY", max_value=date.today(), key="nf_date")
    trade_time = c3.time_input("Время", step=60, key="nf_time")

    # --- Бумага: список Мосбиржи или ручной ввод ---
    ticker, instrument, quote = "", None, None
    if op_type in TICKER_TYPES:
        instruments = {i.ticker: i for i in load_instruments()}
        manual = not instruments or st.session_state.get("nf_manual", False)
        if manual:
            ticker = st.text_input("Тикер", key="nf_ticker_text", placeholder="Например, SBER или SU26238RMFS4")
            if not instruments:
                st.caption("Список бумаг с Мосбиржи сейчас недоступен — введите тикер вручную.")
        else:
            ticker = st.selectbox(
                "Бумага", list(instruments), key="nf_ticker", index=None,
                format_func=lambda t: f"{t} — {instruments[t].name}" if instruments[t].name else t,
                placeholder="Начните вводить тикер или название, например «сбер» или «ОФЗ 26238»",
            ) or ""
        if instruments:
            st.toggle("Нет в списке — ввести тикер вручную", key="nf_manual")
        instrument = instruments.get(ticker.strip().upper()) if ticker else None
        quote = quote_for(instrument) if instrument and is_trade else None

    is_bond = bool(instrument and instrument.is_bond and instrument.face_value)
    face_value = instrument.face_value if is_bond else None

    if instrument:
        info, button = st.columns([3, 1], vertical_alignment="center")
        details = f":green[✓] {instrument.name}"
        if is_bond:
            details += f" · облигация, номинал {fmt_money(face_value)} ₽"
        if quote:
            price_text_now = fmt_bond_pct(quote.price) if is_bond else f"{fmt_price(quote.price)} ₽"
            details += f" · текущая цена **{price_text_now}** (MOEX, {quote.time:%d.%m %H:%M} мск)"
            button.button("Подставить текущую", on_click=fill_field, args=("nf_price", quote.price), key="nf_put_price")
        elif is_trade:
            details += " · цена сейчас недоступна"
        info.caption(details)

    # --- Числа ---
    quantity_text = price_text = fee_text = accrued_text = amount_text = ""
    if is_trade:
        c4, c5, c6 = st.columns(3)
        quantity_text = c4.text_input("Количество, шт.", key="nf_qty", placeholder="10")
        price_text = c5.text_input(
            "Цена, % от номинала" if is_bond else "Цена за 1 шт., ₽", key="nf_price",
            placeholder="95,5" if is_bond else "298,50",
        )
        fee_text = c6.text_input("Комиссия, ₽", key="nf_fee")
        if is_bond:
            c7, c8 = st.columns([2, 1], vertical_alignment="bottom")
            accrued_text = c7.text_input(
                "НКД за всю сделку, ₽", key="nf_accrued", placeholder="0",
                help="Накопленный купонный доход: при покупке вы его платите, при продаже — получаете. "
                     "В стоимость облигации не входит.",
            )
            qty_now = quiet_decimal(quantity_text)
            if quote and quote.accrued_interest is not None and qty_now:
                c8.button(
                    "Подставить НКД", key="nf_put_accrued",
                    on_click=fill_field, args=("nf_accrued", quote.accrued_interest * qty_now),
                    help=f"Текущий НКД {fmt_money(quote.accrued_interest)} ₽ × {fmt_qty(qty_now)} шт.",
                )
    else:
        amount_text = st.text_input(
            "Сумма, ₽", key="nf_amount", placeholder="10 000",
            help="Для дивидендов и купонов — сумма, которая пришла на счёт (после налога).",
        )

    operation, errors = build_operation(
        account_id=account.id, op_type=op_type, trade_date=trade_date, trade_time=trade_time,
        ticker=ticker, quantity_text=quantity_text, price_text=price_text, fee_text=fee_text,
        amount_text=amount_text, accrued_text=accrued_text, face_value=face_value,
        note=st.session_state["nf_note"],
    )

    # --- Сумма — сразу, как только заполнены поля ---
    with st.container(border=True):
        if operation is None:
            st.metric("Сумма операции", "—")
            st.caption("Появится, когда заполните поля выше.")
        elif is_trade:
            sign = "+" if op_type == OpType.BUY else "−"
            st.metric("Сумма сделки", f"{fmt_money(abs(cash_flow(operation)))} ₽")
            if is_bond:
                breakdown = (f"{fmt_qty(operation.quantity)} × {fmt_money(face_value)} ₽ × "
                             f"{fmt_bond_pct(operation.price)}")
            else:
                breakdown = f"{fmt_qty(operation.quantity)} × {fmt_price(operation.price)} ₽"
            breakdown += f" {sign} комиссия {fmt_money(operation.fee)} ₽"
            if operation.accrued_interest:
                breakdown += f" + НКД {fmt_money(operation.accrued_interest)} ₽"
            st.caption(breakdown)
        else:
            st.metric("Сумма операции", f"{fmt_signed_money(cash_flow(operation))} ₽")

    st.text_area(
        "Заметка (необязательно)", key="nf_note", max_chars=1000, height=90,
        placeholder="Почему купили или продали — пригодится, когда будете пересматривать портфель",
    )

    b1, b2, _ = st.columns([1.3, 1.5, 2])
    save = b1.button("Сохранить операцию", type="primary")
    save_more = b2.button("Сохранить и добавить ещё")

    if save or save_more:
        if errors:
            for message in errors:
                st.error(message, icon=":material/error:")
        else:
            try:
                saved = service.add_operation(operation)
            except OversellError as error:
                st.error(str(error), icon=":material/error:")
            else:
                label = OP_TYPE_LABELS[saved.op_type].lower()
                if saved.op_type in TRADE_TYPES:
                    price = fmt_bond_pct(saved.price) if saved.is_bond else f"{fmt_price(saved.price)} ₽"
                    set_flash(f"Сохранено: {label} {saved.ticker}, {fmt_qty(saved.quantity)} шт. по {price}.")
                else:
                    about = f" {saved.ticker}" if saved.ticker else ""
                    set_flash(f"Сохранено: {label}{about}, {fmt_money(saved.amount)} ₽.")
                st.session_state["nf_clear"] = True
                if save_more:
                    st.rerun()
                else:
                    st.switch_page(OPERATIONS)

# --- Блок «После сохранения» ---------------------------------------------
with side_col:
    with st.container(border=True):
        st.subheader("После сохранения")
        if operation is None:
            st.caption("Заполните поля — здесь появится, как изменятся позиция и деньги на счёте.")
        else:
            rows = []
            if is_trade:
                st.caption(f"{operation.ticker} на счёте «{account.name}»")
                try:
                    before, after = service.preview_position(operation)
                except OversellError as error:
                    st.warning(str(error), icon=":material/warning:")
                    before = after = None
                    rows = None
                else:
                    rows.append(("Количество, шт.",
                                 fmt_qty(before.quantity) if before else "0",
                                 fmt_qty(after.quantity) if after else "0"))
                    def avg(position):
                        if position is None:
                            return "—"
                        if is_bond:  # у облигаций — в % от номинала, как в портфеле
                            return fmt_bond_pct(position.avg_price / face_value * 100)
                        return f"{fmt_avg_price(position.avg_price)} ₽"

                    rows.append(("Средняя цена", avg(before), avg(after)))
            else:
                st.caption(f"Счёт «{account.name}»")

            if rows is not None:
                cash_before, cash_after = service.preview_cash(operation)
                rows.append(("Деньги на счёте", f"{fmt_signed_money(cash_before)} ₽", f"{fmt_signed_money(cash_after)} ₽"))
                table = "| | Сейчас | После |\n|---|---:|---:|\n" + "\n".join(
                    f"| {name} | {was} | **{will}** |" for name, was, will in rows
                )
                st.markdown(table)
                if is_trade and after is None:
                    st.caption("Позиция будет закрыта полностью.")
                if cash_after < 0:
                    st.caption(f":orange[{NEGATIVE_CASH_HINT}]")
