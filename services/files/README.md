# Files

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`files:50051` регистрирует [FilesQueryService](../../contracts/grpc/v1/files.proto) и gRPC Health. Оба метода возвращают `PERMISSION_DENIED`; файл или ссылка без проверки прав не выдаются. Из предметных сервисов только Files имеет сетевой доступ к filer `seaweedfs:8888`.

[Запуск стенда](../../infra/README.md)

## База данных (`files`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `stored_files` (ключ объекта SeaweedFS, владелец, источник,
размер, контрольная сумма), `download_grants`, плюс локальные
`outbox_events`/`inbox_messages`.

Запуск: `make up`, затем `make test-files`
(или `cd services/files && uv sync && uv run pytest -q`).
