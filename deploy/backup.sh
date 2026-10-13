#!/usr/bin/env bash
# Бэкап базы: дамп в папку backups/, хранятся последние 14 штук (REQUIREMENTS NF-5).
#
# Запуск вручную (из любой папки):   ~/portfolio-consolidator/deploy/backup.sh
# Каждый день — через cron, см. deploy/RASPBERRY_PI.md.
# Восстановить из дампа:             deploy/restore.sh backups/<файл>.dump

set -euo pipefail               # остановиться при первой ошибке

cd "$(dirname "$0")/.."         # в корень проекта — там docker-compose.yml и .env
KEEP="${KEEP:-14}"              # сколько последних дампов хранить

set -a; source .env; set +a     # DB_USER и DB_NAME из .env

mkdir -p backups
file="backups/portfolio_$(date +%Y-%m-%d_%H%M).dump"

# -Fc — сжатый формат pg_dump, из него восстанавливает pg_restore.
# Пишем во временный файл и переименовываем, только если дамп прошёл успешно,
# чтобы оборванный дамп не выглядел как нормальный бэкап.
docker compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc > "$file.tmp"
mv "$file.tmp" "$file"

# Удаляем всё старше KEEP последних дампов
ls -1t backups/portfolio_*.dump | tail -n +"$((KEEP + 1))" | xargs -r rm --

echo "$(date '+%Y-%m-%d %H:%M') бэкап готов: $file ($(du -h "$file" | cut -f1)), всего: $(ls backups/portfolio_*.dump | wc -l)"
