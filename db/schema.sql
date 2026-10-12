-- Схема базы данных «Мой портфель».
--
-- Файл применяется автоматически при каждом запуске приложения
-- (storage/db.py → apply_schema). Поэтому все команды написаны так,
-- чтобы повторный запуск ничего не ломал: CREATE TABLE IF NOT EXISTS,
-- INSERT ... ON CONFLICT DO NOTHING.
--
-- Деньги и количества хранятся в NUMERIC (точные числа), а не во float,
-- чтобы не было ошибок округления. Модель данных — REQUIREMENTS.md, 3.3.


-- Счета у брокеров ----------------------------------------------------------
CREATE TABLE IF NOT EXISTS accounts (
    id           SERIAL PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,                  -- «Т-Банк брокерский»
    broker       TEXT NOT NULL,                         -- «Т-Банк»
    account_type TEXT NOT NULL DEFAULT 'broker'
                 CHECK (account_type IN ('broker', 'iis')),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Справочник ценных бумаг ---------------------------------------------------
-- Строка появляется при первой операции с тикером. На этапе 1 известен
-- только тикер; название, класс и номинал заполнятся с MOEX на этапе 2.
CREATE TABLE IF NOT EXISTS securities (
    ticker      TEXT PRIMARY KEY,                       -- SECID на MOEX: SBER
    name        TEXT,
    asset_class TEXT CHECK (asset_class IN ('share', 'bond', 'etf')),
    sector      TEXT,
    isin        TEXT,
    board       TEXT,                                   -- TQBR, TQTF, TQOB…
    face_value  NUMERIC(18, 2) CHECK (face_value > 0)   -- номинал облигации
);


-- Операции — источник истины ------------------------------------------------
-- Позиции не хранятся, а каждый раз пересчитываются из этой таблицы.
CREATE TABLE IF NOT EXISTS operations (
    id               SERIAL PRIMARY KEY,
    account_id       INTEGER NOT NULL REFERENCES accounts (id),
    op_datetime      TIMESTAMP NOT NULL DEFAULT now(),
    op_type          TEXT NOT NULL CHECK (op_type IN
                         ('buy', 'sell', 'deposit', 'withdraw', 'dividend', 'coupon')),
    ticker           TEXT REFERENCES securities (ticker),
    quantity         NUMERIC(18, 6),                    -- штук
    price            NUMERIC(18, 6),                    -- за 1 шт.; облигации — % номинала
    fee              NUMERIC(18, 2) NOT NULL DEFAULT 0 CHECK (fee >= 0),
    amount           NUMERIC(18, 2),                    -- сумма денежной операции
    accrued_interest NUMERIC(18, 2) CHECK (accrued_interest >= 0),  -- НКД
    note             TEXT CHECK (char_length(note) <= 1000),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Какие поля обязательны для каждого типа операции (REQUIREMENTS 3.6).
    -- COALESCE(..., false): если поле пустое, сравнение «NULL > 0» даёт NULL,
    -- и без COALESCE PostgreSQL пропустил бы такую строку.
    CONSTRAINT operations_fields_by_type CHECK (COALESCE(
        CASE op_type
            -- покупка и продажа: бумага, количество и цена
            WHEN 'buy'      THEN ticker IS NOT NULL AND quantity > 0 AND price > 0
            WHEN 'sell'     THEN ticker IS NOT NULL AND quantity > 0 AND price > 0
            -- пополнение и вывод: только сумма, без бумаги
            WHEN 'deposit'  THEN ticker IS NULL AND amount > 0
            WHEN 'withdraw' THEN ticker IS NULL AND amount > 0
            -- дивиденд и купон: бумага и сумма
            WHEN 'dividend' THEN ticker IS NOT NULL AND amount > 0
            WHEN 'coupon'   THEN ticker IS NOT NULL AND amount > 0
        END,
    false))
);

-- Ускоряет выборку операций по счёту и по бумаге в хронологическом порядке
CREATE INDEX IF NOT EXISTS operations_account_datetime_idx
    ON operations (account_id, op_datetime);
CREATE INDEX IF NOT EXISTS operations_ticker_datetime_idx
    ON operations (ticker, op_datetime);


-- Кэш цен с Московской биржи ------------------------------------------------
CREATE TABLE IF NOT EXISTS quotes (
    ticker     TEXT NOT NULL REFERENCES securities (ticker),
    quote_time TIMESTAMPTZ NOT NULL,
    price      NUMERIC(18, 6) NOT NULL CHECK (price > 0),
    PRIMARY KEY (ticker, quote_time)
);


-- Целевая структура портфеля ------------------------------------------------
-- Проверку «сумма долей = 100%» делает приложение при сохранении.
CREATE TABLE IF NOT EXISTS target_allocation (
    asset_class  TEXT PRIMARY KEY
                 CHECK (asset_class IN ('share', 'bond', 'etf', 'cash')),
    target_share NUMERIC(5, 2) NOT NULL
                 CHECK (target_share >= 0 AND target_share <= 100)
);


-- Настройки приложения (ключ → значение) ------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Значения по умолчанию (не перезаписывают уже изменённые)
INSERT INTO settings (key, value) VALUES
    ('deviation_threshold_pp', '5')                     -- порог предупреждения, п.п.
ON CONFLICT (key) DO NOTHING;


-- Изменения схемы (этап 3) ---------------------------------------------------
-- ADD COLUMN IF NOT EXISTS: у кого база уже создана, колонки добавятся,
-- данные не пропадут; повторный запуск ничего не меняет.

-- Номинал облигации на дату сделки (цена облигации — в % от номинала)
ALTER TABLE operations ADD COLUMN IF NOT EXISTS face_value NUMERIC(18, 2)
    CHECK (face_value > 0);

-- НКД на одну облигацию в момент цены
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS accrued_interest NUMERIC(18, 2);
