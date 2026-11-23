# rheuma-db

Общая инфраструктура доступа к Postgres для сервисов-владельцев данных
(`services/iam`, `services/screening`, `services/content`,
`services/reporting`, `services/files`, `services/ai`). Каждый сервис
подключает этот пакет локальным path-зависимостью через `uv`:

```toml
[project]
dependencies = ["rheuma-db"]

[tool.uv.sources]
rheuma-db = { path = "../../packages/db", editable = true }
```

## Что внутри

- `rheuma_db.Base` — общий `DeclarativeBase` с единой naming convention для
  индексов/ограничений. Каждый сервис работает в своём процессе и venv, так
  что общий класс не смешивает таблицы разных сервисов в одной `MetaData`.
- `rheuma_db.DatabaseSettings` — pydantic-модель подключения
  (`host`/`port`/`name`/`user`/`password`/`connect_timeout`). `name` и `user`
  без дефолта: сервис обязан явно указать свою БД и свою роль с наименьшими
  привилегиями.
- `rheuma_db.create_database_engine` — синхронный SQLAlchemy `Engine`
  (используется и приложением, и Alembic).
- `rheuma_db.outbox` — зафиксированный DDL (`OUTBOX_EVENTS_DDL`,
  `INBOX_MESSAGES_DDL`) для локальных `outbox_events`/`inbox_messages` в
  каждой БД, плюс `register_outbox_model`/`register_inbox_model` —
  ORM-отображение для контрактных тестов схемы.

## Почему без FK между сервисами

У каждого сервиса — своя БД. `screening_sessions.owner_id` хранит
идентификатор субъекта из IAM без внешнего ключа: FK между базами в Postgres
невозможен технически, а owned-данные другого сервиса синхронизируются через
события (контракты в `contracts/events`) или gRPC-запрос, а не прямым join.
