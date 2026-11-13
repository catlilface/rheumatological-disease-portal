# Server Service

Проект организован по принципу **монорепы**. Все сервисы хранятся в одном Git-репозитории, но для разработки рекомендуется загружать только необходимые компоненты.

## 1. Клонирование репозитория

Для оптимизации загрузки используется **Git Partial Clone + Sparse Checkout**.

```bash
git clone \
    --filter=blob:none \
    --sparse \
    https://github.com/catlilface/rheumatological-disease-portal.git
cd rheumatological-disease-portal
git sparse-checkout set server
```

После выполнения команд в рабочей директории будут доступны файлы сервиса `server` и файлы из корня репозитория.

`--filter=blob:none` позволяет не загружать содержимое всех файлов заранее, а `git sparse-checkout set server` ограничивает набор файлов в рабочей директории.

## 2. Правила работы с Git

### Ветки

Разработка ведётся в отдельных ветках. Название ветки должно соответствовать идентификатору задачи в трекере. Например: `MIS-123`.

### Коммиты

Сообщения коммитов должны:

- Быть написаны на английском языке.
- Кратко и однозначно описывать внесённые изменения.
- Соответствовать формату Conventional Commits (`feat:`, `chores:`, и тд).

## 3. Процесс разработки

Перед началом новой задачи необходимо обновить локальную ветку `main` и создать рабочую ветку.

```bash
# Переключиться на основную ветку
git switch main

# Получить последние изменения
git pull --ff-only origin main

# Создать ветку для задачи
git switch -c MIS-123
```

После внесения изменений:

```bash
# Проверить изменённые файлы
git status

# Добавить необходимые файлы
git add server/path/to/file

# Создать коммит
git commit -m "feat: implement awesome feature"

# Отправить ветку в GitHub
git push -u origin MIS-123
```

## 4. Pull Request и Code Review

После завершения разработки необходимо создать Pull Request в ветку `main` на GitHub.

Порядок действий:

1. Создать Pull Request с описанием изменений.
2. Убедиться, что все обязательные проверки CI успешно пройдены.
3. Добавить тимлида в ревью.
4. При необходимости внести исправления по результатам ревью.

**Тимлид приступает к Code Review только после успешного завершения обязательных проверок CI.**

## 5. Структура backend

Backend использует Python 3.15, FastAPI, Uvicorn и `pydantic-settings`. Окружением и зависимостями управляет `uv`.

```text
server/
├── app/
│   ├── main.py          # Приложение и GET /health
│   ├── settings.py      # Настройки из окружения и корневого .env
│   ├── database/        # Настройки, engine, Base и модели таблиц
│   └── domain/          # Заглушка для моделей и правил предметной области
├── tests/               # Проверки HTTP и настроек
├── pyproject.toml       # Зависимости приложения и тестов
├── uv.lock              # Зафиксированные версии зависимостей
├── .python-version      # Python 3.15 для uv
├── Dockerfile
├── alembic.ini
├── alembic/             # Окружение Alembic и версии миграций
└── README.md
```

PostgreSQL запускается через корневой Docker Compose. Схема описана моделями SQLAlchemy и миграцией Alembic; пока она применяется вручную командами ниже. Автоматическое применение перед запуском backend будет добавлено следующим этапом. Пакет `domain` пока остаётся заглушкой.

## 6. PostgreSQL: настройки и запуск

Настройки БД выделены в `DatabaseSettings`, доступный через `settings.database`. Корневой `.env` читается существующим `Settings` с разделителем `__`:

```dotenv
DATABASE__HOST=localhost
DATABASE__PORT=5432
DATABASE__NAME=rheumatology
DATABASE__USER=rheumatology
DATABASE__PASSWORD=local_dev_password
DATABASE__CONNECT_TIMEOUT=5
BACKEND_PORT=8000
```

Пароль в примере предназначен только для локальной разработки. Задайте свой пароль в `.env`; существующий файл не перезаписывайте. Пароль скрывается в представлении настроек и URL, а отсутствие пароля обнаруживается перед созданием engine. Спецсимволы экранируются при построении URL средствами SQLAlchemy.

Находясь в корне репозитория, установите зависимости и подготовьте `.env`, если он ещё не существует:

```powershell
uv sync --project server --locked
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Если `.env` уже есть, добавьте новые переменные из `.env.example` вручную. После этого:

```bash
# Проверить Compose без вывода пароля
docker compose config --quiet

# Запустить БД и backend
docker compose up --build -d

# Проверить состояние сервисов
docker compose ps
```

Сервис `server` ждёт успешного healthcheck PostgreSQL. В контейнере он подключается к `postgres:5432`, а локальные команды используют `localhost` и `DATABASE__PORT`. Изменение хостового порта БД не меняет внутренний порт контейнера. PostgreSQL 18 сохраняет данные в именованный том, смонтированный в `/var/lib/postgresql`.

Backend доступен на `http://localhost:8000/health` (или порту `BACKEND_PORT`). Этот endpoint проверяет доступность приложения и пока не обращается к БД. Для проверки реального подключения выполните из корня:

```bash
docker compose exec server python -c "from app.settings import Settings; from app.database.connection import create_database_engine; from sqlalchemy import text; engine = create_database_engine(Settings().database); connection = engine.connect(); print(connection.scalar(text('SELECT 1'))); connection.close(); engine.dispose()"
```

Ожидаемый результат — `1`. Создание engine само по себе соединение не открывает; подключение выполняется при `engine.connect()`.

Остановка без удаления данных: `docker compose down`. Не добавляйте `--volumes`, если хотите сохранить БД. Изменение `POSTGRES_USER`/пароля через `.env` не изменяет уже созданные роли и данные существующего тома.

Проверки без работающей PostgreSQL:

```bash
uv run --project server --locked python -m pytest -c server/pyproject.toml server/tests
```

## 7. Схема и Alembic

Модели разделены на пользователей, скрининг, кабинет и контент в `app/database/models/`. `Base.metadata` объединяет их для Alembic. Первая миграция `0001_initial_schema` содержит фиксированный DDL раздела 2 дополнения №1: 14 таблиц, 110 полей, 9 enum-типов и обязательные индексы. Изменение моделей не меняет уже созданную миграцию.

Перед применением установите зависимости, заполните `.env` и запустите PostgreSQL. Все команды ниже выполняются **из корня репозитория** и используют локальное подключение `DATABASE__HOST`/`DATABASE__PORT`:

```bash
uv sync --project server --locked
docker compose up -d postgres
uv run --project server --locked alembic -c server/alembic.ini upgrade head
uv run --project server --locked alembic -c server/alembic.ini current
uv run --project server --locked alembic -c server/alembic.ini check
```

`current` должен показать `0001_initial_schema (head)`, а `check` — отсутствие новых операций миграции относительно моделей. Повторный `upgrade head` сохраняет данные и не создаёт таблицы повторно.

Внутри директории `server` можно использовать `uv run --locked alembic upgrade head`; конфигурация и миграции находятся рядом. Пароль не записывается в `alembic.ini`: онлайн-команды получают `Settings().database` из окружения/корневого `.env`.

Чтобы просмотреть SQL без подключения к БД и без пароля:

```bash
uv run --project server --locked alembic -c server/alembic.ini upgrade head --sql
```

Для следующего изменения схемы создавайте новую миграцию, проверяйте сгенерированные операции и добавляйте её в Git вместе с моделями:

```bash
uv run --project server --locked alembic -c server/alembic.ini revision --autogenerate -m "describe schema change"
```

Откат первоначальной миграции удаляет таблицы и их данные, поэтому он проверяется только на изолированной тестовой PostgreSQL. Unit-тесты сверяют модели с независимым эталоном `tests/fixtures/required_schema.sql`, проверяют отсутствие полной даты рождения и генерацию upgrade/downgrade SQL без БД. Полный тест штатного запуска с автоматическими миграциями будет добавлен после команды запуска backend.

На текущем этапе Alembic запускается локально через `uv`. Копирование миграций в Docker-образ и автоматический запуск перед Uvicorn относятся к следующему этапу.
