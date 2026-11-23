# IAM

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`iam:50051` регистрирует [IamService](../../contracts/grpc/v1/iam.proto). Тестовый `CheckAccess` всегда запрещает действие; вход, проверка и обновление токена возвращают `UNAUTHENTICATED`, создание гостевой сессии — `UNAVAILABLE`. Не передавайте настоящие токены или пароли.

[Запуск стенда](../../infra/README.md)

## База данных (`iam`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `principals` (гость/сотрудник), `auth_sessions`, `roles`,
`principal_roles`, `role_permissions`, `resource_grants`, `access_audit`, плюс
локальные `outbox_events`/`inbox_messages`.

Уточнения по [MIS-23](../../ARCHITECTURE.md) (миграция `0002_mis23_access_model`):

- Ровно одна активная роль на субъекта из `patient`/`editor`/`admin`
  (`roles.code` ограничен CHECK, `principal_roles` — частичным уникальным
  индексом по `principal_id WHERE revoked_at IS NULL`; совмещение
  запрещено, но история отозванных ролей сохраняется).
- `auth_sessions` хранит `refresh_token_hash`/`refresh_family_id` (ротация
  refresh-токена) и `role_version`/`locked_at` для инвалидации при смене
  роли или блокировке. Срок access-токена (168 часов) и блокировки по
  времени реакции (≤5 с) — ответственность сервиса, не схемы.
  `access_audit` дополнен `session_id`/`operation_id`/`reason`.
- `principal_id` в `access_audit` намеренно без FK (аудит переживает
  удаление учётной записи — см. комментарий в модели).

Запуск: `make up`, затем `make test-iam` (или `cd services/iam && uv sync && uv run pytest -q`).
