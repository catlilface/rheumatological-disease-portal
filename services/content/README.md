# Content

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`content:50051` возвращает для `ListPublishedArticles` пустой список и `total=0`, для `GetDoctorRoute` — демонстрационный маршрут. Через FastStream принимает тестовые `ContentCommand` в `dev.content.commands.v1`, не меняя состояние публикаций.

[Контракт gRPC](../../contracts/grpc/v1/content.proto) · [Запуск стенда](../../infra/README.md)
