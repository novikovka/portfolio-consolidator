#!/usr/bin/env bash
# Восстановить базу из дампа (например, перенести данные с компьютера на Pi).
#
#   deploy/restore.sh backups/portfolio.dump
#
# ВНИМАНИЕ: текущие данные в базе заменяются данными из дампа.

set -euo pipefail
cd "$(dirname "$0")/.."
dump="${1:?Укажите файл дампа: deploy/restore.sh backups/<файл>.dump}"
[ -f "$dump" ] || { echo "Файл $dump не найден"; exit 1; }

set -a; source .env; set +a

echo "Останавливаю приложение, чтобы оно не писало в базу во время восстановления…"
docker compose --profile app stop app

echo "Восстанавливаю базу из $dump…"
# --clean --if-exists: сначала удалить существующие таблицы, затем создать из дампа.
# --no-owner: владельцем станет пользователь из .env, даже если на компьютере он назывался иначе.
docker compose exec -T db pg_restore -U "$DB_USER" -d "$DB_NAME" --clean --if-exists --no-owner < "$dump"

echo "Запускаю приложение…"
docker compose --profile app up -d app
echo "Готово."
