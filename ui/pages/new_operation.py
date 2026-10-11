"""Страница «Новая операция»: форма покупки или продажи.

Тикер выбирается из списка акций и фондов Мосбиржи (поиск по тикеру и названию);
рядом — текущая цена и кнопка «Подставить текущую». Если бумаги нет в списке
или биржа недоступна — тикер можно ввести вручную.
Пополнения, выводы, дивиденды и купоны — этап 3.

Поля стоят вне st.form, чтобы сумма сделки и блок «После сохранения»
пересчитывались сразу при вводе.
"""

from datetime import date, datetime

import streamlit as st

from core.calculations import OversellError, cash_flow
from core.models import OpType
from ui.app_state import get_service, load_instruments, quote_for, set_flash, show_flash
from ui.formatting import OP_TYPE_LABELS, fmt_input, fmt_money, fmt_price, fmt_qty
from ui.operation_form import build_trade
from ui.pages_registry import OPERATIONS

TYPES = {"Покупка": OpType.BUY, "Продажа": OpType.SELL}
CLEARED_FIELDS = {"nf_ticker_text": "", "nf_qty": "", "nf_price": "", "nf_fee": "0", "nf_note": ""}


def put_current_price(price) -> None:
    """Кнопка «Подставить текущую»: записывает цену в поле до его отрисовки."""
    st.session_state["nf_price"] = fmt_input(price)

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
st.caption("Внесите сделку, которую совершили у брокера, — портфель пересчитается сразу после сохранения.")

form_col, side_col = st.columns([3, 2], gap="large")

# --- Форма ----------------------------------------------------------------
with form_col:
    type_label = st.radio("Тип операции", list(TYPES), horizontal=True, key="nf_type")
    op_type = TYPES[type_label]

    c1, c2, c3 = st.columns([2, 2, 1])
    account = c1.selectbox(
        "Счёт", accounts, format_func=lambda a: a.name,
        index=accounts.index(default_account), key="nf_account",
    )
    trade_date = c2.date_input("Дата сделки", format="DD.MM.YYYY", max_value=date.today(), key="nf_date")
    trade_time = c3.time_input("Время", step=60, key="nf_time")

    # --- Бумага: список Мосбиржи или ручной ввод ---
    instruments = {i.ticker: i for i in load_instruments()}
    manual = not instruments or st.session_state.get("nf_manual", False)
    if manual:
        ticker = st.text_input("Тикер", key="nf_ticker_text", placeholder="Например, SBER")
        if not instruments:
            st.caption("Список бумаг с Мосбиржи сейчас недоступен — введите тикер вручную.")
    else:
        ticker = st.selectbox(
            "Бумага", list(instruments), key="nf_ticker", index=None,
            format_func=lambda t: f"{t} — {instruments[t].name}" if instruments[t].name else t,
            placeholder="Начните вводить тикер или название, например «сбер»",
        ) or ""
    if instruments:
        st.toggle("Нет в списке — ввести тикер вручную", key="nf_manual")

    # Текущая цена выбранной бумаги
    instrument = instruments.get(ticker.strip().upper()) if ticker else None
    quote = quote_for(instrument) if instrument else None
    if instrument:
        info, button = st.columns([3, 1], vertical_alignment="center")
        if quote:
            info.caption(
                f":green[✓] {instrument.name} · текущая цена **{fmt_price(quote.price)} ₽** "
                f"(MOEX, {quote.time:%d.%m %H:%M} мск)"
            )
            button.button("Подставить текущую", on_click=put_current_price, args=(quote.price,), key="nf_put_price")
        else:
            info.caption(f":green[✓] {instrument.name} · цена сейчас недоступна")

    c4, c5, c6 = st.columns(3)
    quantity_text = c4.text_input("Количество, шт.", key="nf_qty", placeholder="10")
    price_text = c5.text_input("Цена за 1 шт., ₽", key="nf_price", placeholder="298,50")
    fee_text = c6.text_input("Комиссия, ₽", key="nf_fee")

    operation, errors = build_trade(
        account_id=account.id, op_type=op_type, trade_date=trade_date, trade_time=trade_time,
        ticker=ticker, quantity_text=quantity_text, price_text=price_text, fee_text=fee_text,
        note=st.session_state["nf_note"],
    )

    # Сумма сделки — сразу, как только заполнены количество и цена
    with st.container(border=True):
        if operation is not None:
            sign = "+" if op_type == OpType.BUY else "−"
            st.metric("Сумма сделки", f"{fmt_money(abs(cash_flow(operation)))} ₽")
            st.caption(
                f"{fmt_qty(operation.quantity)} × {fmt_price(operation.price)} ₽ "
                f"{sign} комиссия {fmt_money(operation.fee)} ₽"
            )
        else:
            st.metric("Сумма сделки", "—")
            st.caption("Появится, когда заполните тикер, количество и цену.")

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
                set_flash(
                    f"Сохранено: {OP_TYPE_LABELS[saved.op_type].lower()} {saved.ticker}, "
                    f"{fmt_qty(saved.quantity)} шт. по {fmt_price(saved.price)} ₽."
                )
                if save_more:
                    st.session_state["nf_clear"] = True
                    st.rerun()
                else:
                    st.session_state["nf_clear"] = True
                    st.switch_page(OPERATIONS)

# --- Блок «После сохранения» ---------------------------------------------
with side_col:
    with st.container(border=True):
        st.subheader("После сохранения")
        if operation is None:
            st.caption("Заполните тикер, количество и цену — здесь появится, как изменится позиция.")
        else:
            st.caption(f"{operation.ticker} на счёте «{account.name}»")
            try:
                before, after = service.preview_position(operation)
            except OversellError as error:
                st.warning(str(error), icon=":material/warning:")
            else:
                qty_before = fmt_qty(before.quantity) if before else "0"
                qty_after = fmt_qty(after.quantity) if after else "0"
                avg_before = f"{fmt_price(before.avg_price)} ₽" if before else "—"
                avg_after = f"{fmt_price(after.avg_price)} ₽" if after else "—"
                st.markdown(
                    f"| | Сейчас | После |\n|---|---:|---:|\n"
                    f"| Количество, шт. | {qty_before} | **{qty_after}** |\n"
                    f"| Средняя цена | {avg_before} | **{avg_after}** |"
                )
                if after is None:
                    st.caption("Позиция будет закрыта полностью.")
            st.caption("Деньги на счёте появятся в этом блоке на этапе 3.")
