"""Хранилище на PostgreSQL: реализация интерфейса Repository через SQL.

Каждый метод открывает короткое соединение и сразу его закрывает.
Изменения фиксируются (commit) автоматически при выходе из блока with.
"""

from dataclasses import replace

from core.models import Account, Operation, OpType
from storage.db import connect

# Порядок колонок, в котором читаем операции из базы
_OPERATION_COLUMNS = "id, account_id, op_datetime, op_type, ticker, quantity, price, fee, amount, note"


class PostgresRepository:
    """Хранилище данных в PostgreSQL."""

    # --- Счета -----------------------------------------------------------

    def list_accounts(self) -> list[Account]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT id, name, broker, account_type FROM accounts ORDER BY id"
            ).fetchall()
        return [Account(id=r[0], name=r[1], broker=r[2], account_type=r[3]) for r in rows]

    def add_account(self, name: str, broker: str, account_type: str = "broker") -> Account:
        with connect() as conn:
            (new_id,) = conn.execute(
                "INSERT INTO accounts (name, broker, account_type) VALUES (%s, %s, %s) RETURNING id",
                (name, broker, account_type),
            ).fetchone()
        return Account(id=new_id, name=name, broker=broker, account_type=account_type)

    # --- Справочник бумаг -----------------------------------------------

    def ensure_security(self, ticker: str) -> None:
        with connect() as conn:
            conn.execute(
                "INSERT INTO securities (ticker) VALUES (%s) ON CONFLICT (ticker) DO NOTHING",
                (ticker,),
            )

    # --- Операции ---------------------------------------------------------

    def list_operations(self) -> list[Operation]:
        with connect() as conn:
            rows = conn.execute(f"SELECT {_OPERATION_COLUMNS} FROM operations").fetchall()
        return [_row_to_operation(row) for row in rows]

    def add_operation(self, operation: Operation) -> Operation:
        with connect() as conn:
            (new_id,) = conn.execute(
                """
                INSERT INTO operations
                    (account_id, op_datetime, op_type, ticker, quantity, price, fee, amount, note)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                _operation_values(operation),
            ).fetchone()
        return replace(operation, id=new_id)

    def update_operation(self, operation: Operation) -> None:
        with connect() as conn:
            conn.execute(
                """
                UPDATE operations
                SET account_id = %s, op_datetime = %s, op_type = %s, ticker = %s,
                    quantity = %s, price = %s, fee = %s, amount = %s, note = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (*_operation_values(operation), operation.id),
            )

    def delete_operation(self, operation_id: int) -> None:
        with connect() as conn:
            conn.execute("DELETE FROM operations WHERE id = %s", (operation_id,))


def _operation_values(op: Operation) -> tuple:
    """Значения полей операции в порядке колонок INSERT/UPDATE."""
    return (
        op.account_id, op.op_datetime, op.op_type.value, op.ticker,
        op.quantity, op.price, op.fee, op.amount, op.note,
    )


def _row_to_operation(row: tuple) -> Operation:
    """Строка из базы → Operation. NUMERIC приходит из psycopg сразу как Decimal."""
    return Operation(
        id=row[0], account_id=row[1], op_datetime=row[2], op_type=OpType(row[3]),
        ticker=row[4], quantity=row[5], price=row[6], fee=row[7], amount=row[8], note=row[9],
    )
