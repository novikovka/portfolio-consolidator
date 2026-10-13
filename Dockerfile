# Образ приложения (Streamlit) для сервера — Raspberry Pi 5 или любого компьютера с Docker.
# Собирается командой: docker compose --profile app up -d --build
#
# python:3.11-slim есть и для обычных компьютеров (amd64), и для Raspberry Pi (arm64):
# Docker сам скачает нужный вариант.
FROM python:3.11-slim

# Не создавать .pyc-файлы и сразу выводить логи (их видно в docker compose logs app)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости: этот слой кэшируется, и при правке кода
# пересборка не скачивает библиотеки заново
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код приложения (что не копируется — в .dockerignore)
COPY . .

EXPOSE 8501

# Docker раз в 30 с проверяет, что Streamlit отвечает; статус виден в docker compose ps
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

# 0.0.0.0 — принимать подключения не только с самой машины, но и с телефона/ноутбука в сети
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
