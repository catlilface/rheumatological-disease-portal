# Reporting

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`reporting:50051` регистрирует [ReportingQueryService](../../contracts/grpc/v1/reporting.proto) и gRPC Health. `GetReport` и `GetOperation` возвращают фиксированный `NOT_FOUND`: на этом стенде отчётов нет. FastStream читает тестовые `ReportingCommand` из `dev.reporting.commands.v1`; PDF не создаётся.

[Запуск стенда](../../infra/README.md)

## База данных (`reporting`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `report_jobs` (`operation_id UNIQUE`), `report_snapshots` (один
снимок на задание), плюс локальные `outbox_events`/`inbox_messages`.

Уточнение по MIS-23 (миграция `0002_mis23_access_model`): `report_jobs`
дополнен `owner_subject_id` (субъект IAM, без FK) — `fileId`/`operationId`
сами по себе не являются полномочием, владелец задания фиксируется явно.

Запуск: `make up`, затем `make test-reporting`
(или `cd services/reporting && uv sync && uv run pytest -q`).
