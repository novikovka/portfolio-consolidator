# Консолидатор инвестиционного портфеля

Личное веб-приложение, которое собирает операции со всех брокерских счетов в один портфель: что у меня есть, сколько это стоит по ценам Московской биржи, сколько я заработала и насколько структура отличается от целевой.

## Документы

| Файл | Что внутри |
|---|---|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Пользовательские и технические требования, модель данных, правила расчётов |
| [PLAN.md](PLAN.md) | Пошаговый план с промптами и проверками |
| [RULES.md](RULES.md) | Правила для ИИ-помощника |

## Стек

Python · Streamlit · PostgreSQL (psycopg) · pandas · requests · MOEX ISS API · pytest
Разработка: Windows 10. Сервер: Raspberry Pi 5 (приложение и база — в Docker).

## Этапы

| # | Этап | Результат |
|---|---|---|
| 0 | Подготовка | Инструменты, GitHub, база данных |
| 1 | Операции и позиции | Ввожу сделки, вижу позиции и среднюю цену |
| 2 | Цены и доходность | Текущая стоимость по данным MOEX |
| 3 | Счета, деньги, облигации, журнал | Весь реальный портфель в приложении |
| 4 | Структура и цели | Диаграммы, отклонения от цели — **MVP** |
| 5 | Raspberry Pi 5 | Приложение доступно с телефона 24/7 |

## Запуск

Нужны Python 3.11+ и запущенный Docker Desktop.

**Первый раз:**
```powershell
copy .env.example .env          # вписать свой пароль вместо change_me
docker compose up -d            # поднять базу PostgreSQL
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py            # откроется http://localhost:8501
```

**В следующие разы:**
```powershell
.venv\Scripts\Activate.ps1
streamlit run app.py
```
База запускается сама вместе с Docker Desktop. Проверить: `docker compose ps`.

## Сервер (Raspberry Pi 5)

На сервере приложение тоже работает в Docker и само поднимается после перезагрузки:
```bash
docker compose --profile app up -d --build   # база + приложение, http://<адрес Pi>:8501
```
Пошаговая установка, перенос данных, бэкапы и обновление — [deploy/RASPBERRY_PI.md](deploy/RASPBERRY_PI.md).
