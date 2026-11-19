# Reporting

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`reporting:50051` регистрирует [ReportingQueryService](../../contracts/grpc/v1/reporting.proto) и gRPC Health. `GetReport` и `GetOperation` возвращают фиксированный `NOT_FOUND`: на этом стенде отчётов нет. FastStream читает тестовые `ReportingCommand` из `dev.reporting.commands.v1`; PDF не создаётся.

[Запуск стенда](../../infra/README.md)
