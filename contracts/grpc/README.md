# gRPC-контракты

В `v1/` находятся `.proto`-файлы синхронного взаимодействия сервисов:

- Запросы данных и статусов операций, включая агрегацию через BFF.
- Операции IAM: аутентификация, обновление токенов и проверка доступа.
- Типы сообщений, метаданные авторизации и правила обработки ошибок.

### Привязка к HTTP-контракту BFF

- **До старта скрининга** BFF читает `GetSurvey` и отдаёт клиенту `survey_id`, `weights_version`, текст `disclaimer` и `disclaimer_version`. Запрос старта должен вернуть обе показанные версии и явное JSON-значение `disclaimer_accepted: true`. Одного `survey_id` недостаточно. BFF передаёт эти значения в `StartScreening` и ставит время получения подтверждения; при смене текста нужно показать его снова.
- **Редактирование сессии:** клиент отправляет `expected_session_version` той сессии, которую редактировал. После `SESSION_VERSION_CONFLICT` клиент перечитывает состояние; нельзя автоматически подставить новую версию и повторить старый ответ.
- **Результат:** при `RED_FLAG` JSON содержит `risk_level: "red_flag"` и `red_flag: true`, в том числе после продолжения анкеты. Отсутствующий `total_score` передаётся как `score: null`, посчитанный ноль — как `score: 0`.
- **Список статей:** HTTP-параметры `limit` и `offset` передаются как `page.page_size` и `page.offset`. `total` берётся из ответа Content, не из длины текущей страницы.

Это требования к подключению реальных сервисов. BFF вызывает `IamService` по mTLS; IAM хранит сессии и решения аудита в `mis_iam`. Предметные ресурсы демонстрационного BFF по-прежнему в памяти. [Контракт и проверка сессий](../../services/iam/README.md).

Python-stubs генерируются при сборке образов. Для обновления Go-stubs IAM из корня checkout (в `PATH` нужны `protoc-gen-go` v1.36.11 и `protoc-gen-go-grpc` v1.6.1):

```sh
uv run --project packages/service-runtime --locked python -m grpc_tools.protoc -I. \
  --go_out=services/bff --go_opt=module=portal/bff \
  --go-grpc_out=services/bff --go-grpc_opt=module=portal/bff \
  contracts/common/v1/metadata.proto contracts/grpc/v1/iam.proto
```
