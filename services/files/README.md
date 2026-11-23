# Files

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`files:50051` регистрирует [FilesQueryService](../../contracts/grpc/v1/files.proto) и gRPC Health. Оба метода возвращают `PERMISSION_DENIED`; файл или ссылка без проверки прав не выдаются. Из предметных сервисов только Files имеет сетевой доступ к filer `seaweedfs:8888`.

[Запуск стенда](../../infra/README.md)

## База данных (`files`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `stored_files` (ключ объекта SeaweedFS, владелец, источник,
размер, контрольная сумма), `download_grants`, плюс локальные
`outbox_events`/`inbox_messages`.

Уточнение по MIS-23 (миграция `0002_mis23_access_model`): `stored_files`
переименован в `owner_subject_id` (консистентно с остальными сервисами).
`download_grants` разделяет владельца файла (`owner_subject_id`, пациент) и
получателя разрешения (`recipient_subject_id`, переименован из `issued_to`,
например врач); добавлены `version` (ревизия в цепочке продлений — продление
создаёт новую запись и отзывает старую) и `source_reference` (что запросило
разрешение, например задание Reporting, без FK). `created_at` переименован
в `issued_at` — TTL отсчитывается от выдачи.

Запуск: `make up`, затем `make test-files`
(или `cd services/files && uv sync && uv run pytest -q`).
