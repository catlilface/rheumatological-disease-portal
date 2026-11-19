# Files

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`files:50051` регистрирует [FilesQueryService](../../contracts/grpc/v1/files.proto) и gRPC Health. Оба метода возвращают `PERMISSION_DENIED`; файл или ссылка без проверки прав не выдаются. Из предметных сервисов только Files имеет сетевой доступ к filer `seaweedfs:8888`.

[Запуск стенда](../../infra/README.md)
