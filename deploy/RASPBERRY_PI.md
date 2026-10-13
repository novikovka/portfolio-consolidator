# Сервер на Raspberry Pi 5

Приложение и база работают на Pi в Docker, сами поднимаются после перезагрузки,
открываются с телефона и компьютера в домашней сети. Каждую ночь делается бэкап.

Везде ниже `user` — имя пользователя на Pi; подставьте своё.
Команды с `PS>` выполняются на компьютере (PowerShell), с `pi$` — на Pi по SSH.

---

## 1. Записать систему (на компьютере)

> ⚠️ Запись стирает всё, что есть на карте/SSD. Если на Pi уже стоит система с нужными
> файлами — сначала сохраните их.

1. Скачать и открыть **Raspberry Pi Imager** (raspberrypi.com/software).
2. Устройство: **Raspberry Pi 5**. Система: **Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)**
   — без рабочего стола, монитор не нужен. Носитель: ваша карта или SSD.
3. «Далее» → **«Изменить настройки»**:
   - имя хоста: `portfolio-pi`;
   - имя пользователя и пароль (запишите);
   - Wi-Fi — только если Pi будет без кабеля;
   - часовой пояс: `Asia/Yekaterinburg`;
   - вкладка «Службы»: **включить SSH**, вход по паролю.
4. Записать, вставить в Pi, подключить кабель сети (лучше) и питание. Подождать 2–3 минуты.

## 2. Подключиться по SSH

```
PS> ssh user@portfolio-pi.local
```
Первый раз спросит «Are you sure…» → `yes`, затем пароль.
Если `portfolio-pi.local` не находится — посмотрите IP Pi в веб-интерфейсе роутера
(список подключённых устройств) и используйте его: `ssh user@192.168.1.50`.

> Совет: в роутере закрепите за Pi постоянный IP (DHCP reservation) — пригодится для телефона.

## 3. Обновить систему и поставить Git

```
pi$ sudo apt update && sudo apt full-upgrade -y
pi$ sudo apt install -y git
```

## 4. Установить Docker

```
pi$ curl -fsSL https://get.docker.com | sudo sh     # официальный скрипт установки
pi$ sudo usermod -aG docker $USER                    # разрешить docker без sudo
pi$ sudo systemctl enable docker                     # запускать Docker при старте Pi
```
Зеркало Docker Hub (как на компьютере — без него бывает `TLS handshake timeout`):
```
pi$ echo '{"registry-mirrors": ["https://mirror.gcr.io"]}' | sudo tee /etc/docker/daemon.json
pi$ sudo systemctl restart docker
```
Выйти (`exit`) и зайти по SSH снова — чтобы заработало право на docker без sudo. Проверка:
```
pi$ docker run --rm hello-world        # → «Hello from Docker!»
pi$ docker compose version             # → Docker Compose version v2…
```

## 5. Скачать проект и задать пароль базы

```
pi$ cd ~
pi$ git clone https://github.com/novikovka/portfolio-consolidator.git
pi$ cd portfolio-consolidator
pi$ cp .env.example .env
pi$ nano .env          # вписать свой пароль вместо change_me; Ctrl+O, Enter — сохранить, Ctrl+X — выйти
```
Репозиторий публичный, входить в GitHub на Pi не нужно.

## 6. Запустить

```
pi$ docker compose --profile app up -d --build
```
Первая сборка на Pi — 5–10 минут (скачиваются Python и библиотеки). Затем:
```
pi$ docker compose ps
```
Оба контейнера — `portfolio-db` и `portfolio-app` — должны быть `Up … (healthy)`
(у приложения статус `healthy` появляется примерно через 30 секунд).

Открыть на компьютере: **http://portfolio-pi.local:8501** (или `http://<IP Pi>:8501`).
Приложение пока пустое — данные перенесём на следующем шаге.

Если что-то не так — логи: `docker compose logs app` и `docker compose logs db`.

## 7. Перенести данные с компьютера

На компьютере, в папке проекта (Docker Desktop запущен):
```
PS> docker compose exec db pg_dump -U portfolio_app -d portfolio -Fc -f /tmp/portfolio.dump
PS> docker compose cp db:/tmp/portfolio.dump .\portfolio.dump
PS> scp .\portfolio.dump user@portfolio-pi.local:~/portfolio-consolidator/
```
(`portfolio_app` и `portfolio` — значения `DB_USER` и `DB_NAME` из `.env` на компьютере.
Дамп сначала пишется внутри контейнера, а не через `>` — PowerShell портит двоичные файлы при перенаправлении.)

На Pi:
```
pi$ cd ~/portfolio-consolidator
pi$ deploy/restore.sh portfolio.dump
```
Обновить страницу в браузере → видны все операции и счета. Файл `portfolio.dump` на компьютере и на Pi
можно удалить (в GitHub он не попадёт — `*.dump` в `.gitignore`).

## 8. Ежедневный бэкап

Проверить вручную:
```
pi$ ~/portfolio-consolidator/deploy/backup.sh
```
→ строка «бэкап готов: backups/portfolio_…dump». Затем включить расписание:
```
pi$ crontab -e        # при первом запуске выбрать редактор nano (1)
```
В конец файла добавить строку (каждый день в 03:30) и сохранить:
```
30 3 * * * /home/user/portfolio-consolidator/deploy/backup.sh >> /home/user/portfolio-consolidator/backups/backup.log 2>&1
```
Хранятся 14 последних дампов. Восстановить любой: `deploy/restore.sh backups/<файл>.dump`.

## 9. Проверить автозапуск

```
pi$ sudo reboot
```
Через 1–2 минуты **http://portfolio-pi.local:8501** открывается само, без входа на Pi.
С телефона в домашнем Wi-Fi: `http://<IP Pi>:8501` (телефоны на Android часто не понимают `.local`).

---

## Как обновлять приложение

Разрабатываю и проверяю на компьютере → PR → merge. Затем на Pi:
```
pi$ cd ~/portfolio-consolidator
pi$ git pull
pi$ docker compose --profile app up -d --build
```
Данные не пропадают: база живёт в томе `pgdata`, а схема дополняется сама при запуске.

## Полезные команды

| Что | Команда |
|---|---|
| Состояние | `docker compose ps` |
| Логи приложения | `docker compose logs -f app` (выход — Ctrl+C) |
| Перезапустить приложение | `docker compose --profile app restart app` |
| Остановить всё | `docker compose --profile app stop` |
| Место на диске | `df -h /` |
| Температура процессора | `vcgencmd measure_temp` |
