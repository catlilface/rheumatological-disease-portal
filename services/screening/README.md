# Screening

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`screening:50051` регистрирует [ScreeningQueryService](../../contracts/grpc/v1/screening.proto) и gRPC Health. `GetSurvey` возвращает анкету из `survey.json`; сессии, результаты и операции возвращают `NOT_FOUND`. FastStream читает тестовые `ScreeningCommand` из `dev.screening.commands.v1`; ответы не сохраняются и результат не рассчитывается.

[Запуск стенда](../../infra/README.md)

## База данных (`screening`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `questionnaire_versions`, `screening_sessions`, `screening_answers`,
`screening_results`, плюс локальные `outbox_events`/`inbox_messages`.

Запуск: `make up`, затем `make test-screening`
(или `cd services/screening && uv sync && uv run pytest -q`).
