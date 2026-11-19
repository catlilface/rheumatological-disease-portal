# Screening

Сейчас каркас написан на Python; язык итоговой реализации открыт для обсуждения.
`screening:50051` регистрирует [ScreeningQueryService](../../contracts/grpc/v1/screening.proto) и gRPC Health. `GetSurvey` возвращает анкету из `survey.json`; сессии, результаты и операции возвращают `NOT_FOUND`. FastStream читает тестовые `ScreeningCommand` из `dev.screening.commands.v1`; ответы не сохраняются и результат не рассчитывается.

[Запуск стенда](../../infra/README.md)
