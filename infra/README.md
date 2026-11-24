# Стенд MVP: Compose и тестовый Kubernetes

Для разработки на **синтетических данных**. Один экземпляр каждого компонента; это не production и не резервная копия. Снаружи доступен только BFF. Его существующие маршруты пока используют собственные фикстуры; доступность стенда не означает, что BFF переведён на удалённые сервисы.

| Компонент | Внутренний адрес | Что сохраняется |
|---|---|---|
| PostgreSQL 18.7 | `postgres:5432` | В Compose один сервер и шесть отдельных баз: `mis_iam`, `mis_content`, `mis_screening`, `mis_reporting`, `mis_files`, `mis_ai` |
| Apache Kafka 4.4.0 (KRaft) | `kafka:19092` | Журналы, метаданные и смещения |
| SeaweedFS 4.54 | `seaweedfs:8888` | Содержимое и индекс filer на одном томе `/data`; клиент — Files |
| Qdrant 1.20.2 | `qdrant:6333` | Коллекции и векторы; будущий клиент — AI |
| Python-каркасы | `{iam,content,screening,reporting,files}:50051` | gRPC-серверы по [`contracts/grpc/v1`](../contracts/grpc/v1), без бизнес-данных |


## Локальный запуск

Из корня полного checkout, с Make, OpenSSL, запущенным Docker и Compose v2.24+ (или v5). Для первой сборки и загрузки образов нужен интернет. Устанавливать PostgreSQL или dbmate на хост не нужно.

```sh
make up              # секреты → PostgreSQL → роли и БД → dbmate → backend-стенд
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

`make migrate` поднимает только PostgreSQL и применяет недостающие миграции. `make down` останавливает стенд **без удаления** именованных томов. При следующем `make up` используйте то же имя Compose-проекта и те же файлы `.secrets/`. Старые БД без префикса не переименовываются, их данные не переносятся. Для чистой проверки не удаляйте рабочий том: `make test-db` создаёт отдельный временный проект и удаляет только его том.

### Подключение и миграции

Пример: Screening подключается к `postgres:5432/mis_screening` как `mis_screening_app`; пароль доступен внутри этого контейнера в `/run/secrets/db-password`. Проверить реальное подключение: `docker compose exec screening python database.py screening`. Остальные владельцы используют тот же шаблон имени. BFF не подключён к сети БД, порт 5432 не опубликован. В `.env` копируются настройки из `.env.example`, но пароли БД туда не записываются. Храните сгенерированные секреты отдельно от Git; замена файла не меняет пароль уже существующей роли.

`db-bootstrap` создаёт роли и базы с отдельными владельцами. `db-migrate` подключается к каждой базе под `mis_<сервис>_migrator` и запускает [`dbmate migrate`](https://github.com/amacneil/dbmate) в строгом порядке; административный пароль ему не нужен. Прикладная роль не владеет БД и не может ни выполнять DDL, ни менять историю `migration.schema_migrations`. Прикладные таблицы находятся в `public`. Файлы dbmate `-- migrate:up` / `-- migrate:down` лежат в `services/<сервис>/migrations/`; общий технический слой UUIDv7 и inbox/outbox — в `infra/db/common/`. Номера в этих двух каталогах для каждой БД не должны пересекаться. Новая миграция задаёт `SET LOCAL search_path = public;` в обеих секциях, чтобы DDL не попал в схему журнала. **Применённый SQL не редактируют:** dbmate хранит версии, не контрольные суммы. Для исправления добавляют следующий файл. `dbmate drop` и откат миграций не входят в обычный запуск.

## Тестовый Kubernetes с нуля

Проверено с Docker, **k3d 5.9.0**, **K3s v1.37.2+k3s1** и `kubectl`. У K3s по умолчанию есть local-path StorageClass и контроллер NetworkPolicy. Не отключайте его: одни YAML-политики без enforcement не защищают данные. Для другого кластера нужны динамические RWO PVC, соответствующий CNI и доступ узлов к образам. Gateway, LoadBalancer и HPA для этой задачи не нужны.

Kubernetes пока использует отдельный `infra/k8s/init.sql`: там шесть пустых БД без префикса, без dbmate и прикладного SQL-доступа. Для него выполните `make prepare && docker compose build` (запуск Compose не обязателен). Создайте **отдельный** кластер, не меняя текущий kube-context:

```sh
k3d cluster create rdp-mvp --image rancher/k3s:v1.37.2-k3s1 \
  --kubeconfig-update-default=false --kubeconfig-switch-context=false
k3d kubeconfig get rdp-mvp > .secrets/kubeconfig
export KUBECONFIG="$PWD/.secrets/kubeconfig"
kubectl get nodes

# Импорт только платформы узла: Docker Desktop может хранить неполный multi-arch index.
platform=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
for service in bff content files iam reporting screening; do
  image="rdp-$service:mvp"
  docker save --platform "$platform" "$image" | docker exec -i k3d-rdp-mvp-server-0 ctr -n k8s.io images import - || exit 1
done
kubectl create namespace rdp-mvp
kubectl -n rdp-mvp create secret generic postgres-password --from-file=password=.secrets/postgres-password
kubectl apply -k infra/k8s
for w in $(kubectl -n rdp-mvp get deploy,sts -o name); do
  kubectl -n rdp-mvp rollout status "$w" --timeout=5m || exit 1
done
kubectl -n rdp-mvp get pod,pvc,svc,networkpolicy
kubectl -n rdp-mvp port-forward svc/bff 8001:8000
# В другом терминале: curl -fsS http://localhost:8001/health
```

`port-forward` — административный доступ через kubeconfig, не публичный маршрут. StatefulSet повторно использует свой PVC при пересоздании Pod. Обновление конфигурации — `kubectl apply -k infra/k8s`. При пересборке локального образа с тем же тегом повторите импорт и `kubectl rollout restart` нужных Deployment. Удаление namespace, PVC или `k3d cluster delete rdp-mvp` может уничтожить данные. Настройки рассчитаны на доверенного администратора: права `exec`, `port-forward`, создания и разметки Pod нельзя выдавать конечным пользователям. Не передавайте настоящие токены, пароли пользователей или медицинские данные в тестовые RPC/топики.

## Статические ответы и логи

У каждого предметного сервиса свой `services/<имя>/main.py` и собственный образ. В `packages/service-runtime` общие сборка, транспорт и техническая проверка подключения к БД. Для изменения ответа правьте файл владельца. Обращения к бизнес-RPC, HTTP и Kafka логируются через Loguru: `*.received` и `*.response` (у Kafka — `kafka.result`) связаны полем `call`. В логах видны тип запроса, тип ответа или код отказа; содержимое анкет, тела сообщений, токены и байты файлов не записываются. Смотреть: `docker compose logs -f screening` или `kubectl -n rdp-mvp logs -f deploy/screening`.

## Приёмочные проверки

`make test-db` можно выполнить даже при остановленном стенде. Проверка сопоставляет 36 прикладных таблиц с владельцами, использует шесть настоящих логинов по TCP, проверяет запрет DDL и все 30 чужих подключений. Доменным тестам передаются только синтетические данные. После пересоздания контейнера на том же томе проверяются строки, UUID и неизменность истории миграций. Следующие скрипты проверяют уже запущенный стенд:

| Когда запускать | Что проверяет скрипт |
| --- | --- |
| После изменения gRPC-ответов, обработки команд или сетевых правил | [`check-transport.sh`](check-transport.sh) проверяет статические ответы и ожидаемые отказы gRPC, отправляет тестовую команду через FastStream и по логам подтверждает её обработку сервисом Content. Также проверяет, что BFF не может напрямую подключиться к PostgreSQL, Kafka, SeaweedFS и Qdrant. Сервисы не перезапускает. |
| После изменения томов или конфигурации хранилищ | [`smoke.sh`](smoke.sh) проверяет наличие шести прикладных БД, записывает и читает SQL-строку, Kafka-сообщение, файл в SeaweedFS и точку в Qdrant. Затем пересоздаёт контейнеры или Pod этих четырёх компонентов и повторяет чтение. При успехе удаляет созданные тестовые объекты, сохраняя тома. |

**`smoke.sh` временно прерывает доступ к брокеру и хранилищам.** Используйте его только на тестовом стенде; перед запуском проверьте имя Compose-проекта или текущий контекст Kubernetes. При ошибке тестовые объекты могут остаться для диагностики.

### Docker Compose

```sh
# Используйте то же имя Compose-проекта, что и при make up.
bash infra/check-transport.sh compose
bash infra/smoke.sh compose
```

### Kubernetes

```sh
export KUBECONFIG="$PWD/.secrets/kubeconfig"
kubectl config current-context  # ожидается k3d-rdp-mvp; скрипты используют namespace rdp-mvp
bash infra/check-transport.sh k8s
bash infra/smoke.sh k8s
```

Проверки независимы: можно выполнить только нужную команду. При успехе каждый скрипт выводит `OK: …`; при ошибке завершается с ненулевым кодом.

Проверка транспорта использует тестовый топик `dev.content.commands.v1`: приём команды не подтверждает выполнение бизнес-операции. При ошибке смотрите `docker compose logs <имя>` или `kubectl -n rdp-mvp describe pod <имя>` и `kubectl -n rdp-mvp logs <имя>`.
