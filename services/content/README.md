# Content

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`content:50051` возвращает для `ListPublishedArticles` пустой список и `total=0`, для `GetDoctorRoute` — демонстрационный маршрут. Через FastStream принимает тестовые `ContentCommand` в `dev.content.commands.v1`, не меняя состояние публикаций.

[Контракт gRPC](../../contracts/grpc/v1/content.proto) · [Запуск стенда](../../infra/README.md)

## База данных (`content`)

Миграции и схема — отдельно от gRPC-каркаса выше: `alembic/`, `app/database/models.py`.
Таблицы: `materials`, `material_versions`, `material_sources`, плюс
локальные `outbox_events`/`inbox_messages`. Не более одной опубликованной
версии на материал — частичный уникальный индекс
`material_versions_one_published_idx ... WHERE status = 'published'`.

Уточнение по MIS-23 (миграция `0002_mis23_access_model`): `materials`
дополнен `approved_by`/`approved_version` — кто и какую версию одобрил,
отдельно от `material_versions.reviewer_id` (рецензент конкретной версии).
`approved_version` — FK на `material_versions(material_id, version)`: нельзя
одобрить версию, которой не существует. Изменение текста требует нового
одобрения — обеспечивается приложением (новая версия стартует не с
`approved`), а не этой миграцией.

Запуск: `make up`, затем `make test-content`
(или `cd services/content && uv sync && uv run pytest -q`).
