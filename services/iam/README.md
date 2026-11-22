# IAM

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`iam:50051` регистрирует [IamService](../../contracts/grpc/v1/iam.proto). Тестовый `CheckAccess` всегда запрещает действие; вход, проверка и обновление токена возвращают `UNAUTHENTICATED`, создание гостевой сессии — `UNAVAILABLE`. Не передавайте настоящие токены или пароли.

[Запуск стенда](../../infra/README.md)

## База данных (`iam`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `principals` (гость/сотрудник), `auth_sessions`, `roles`,
`principal_roles`, `role_permissions`, `resource_grants`, `access_audit`, плюс
локальные `outbox_events`/`inbox_messages`.


Запуск: `make up`, затем `make test-iam` (или `cd services/iam && uv sync && uv run pytest -q`).
