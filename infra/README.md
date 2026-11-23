# Стенд MVP: Compose и тестовый Kubernetes

Для разработки на **синтетических данных**. Один экземпляр каждого компонента; это не production и не резервная копия. Снаружи доступен только BFF. Его существующие маршруты пока используют собственные фикстуры; доступность стенда не означает, что BFF переведён на удалённые сервисы.

| Компонент | Внутренний адрес | Что сохраняется |
|---|---|---|
| PostgreSQL 18.7 | `postgres:5432` | Один сервер, шесть пустых прикладных БД: `iam`, `content`, `screening`, `reporting`, `files`, `ai` |
| Apache Kafka 4.4.0 (KRaft) | `kafka:19092` | Журналы, метаданные и смещения |
| SeaweedFS 4.54 | `seaweedfs:8888` | Содержимое и индекс filer на одном томе `/data`; клиент — Files |
| Qdrant 1.20.2 | `qdrant:6333` | Коллекции и векторы; будущий клиент — AI |
| Python-каркасы | `{iam,content,screening,reporting,files}:50051` | gRPC-серверы по [`contracts/grpc/v1`](../contracts/grpc/v1), без бизнес-данных |

Qdrant выбран как отдельный векторный индекс, чтобы не добавлять таблицы и расширения в пустые предметные БД. Для AI пока нет gRPC-контракта: подготовлены БД и индекс, сам сервис не симулируется. В SQL нет пользовательских таблиц; миграции и роли с правами на конкретную БД появятся у владельцев сервисов. Пароль администратора в приложения не передаётся. Пока у сервисов со статическими ответами нет необходимости в SQL, сетевой доступ к PostgreSQL закрыт.

## Локальный запуск

Из корня репозитория, с Docker и Compose v2.24+ (или v5). На машине для одновременного запуска обоих стендов использовано 8 GiB памяти Docker. Для начальной сборки и загрузки образов нужен интернет.

```sh
umask 077
mkdir -p .secrets
test -s .secrets/postgres-password || openssl rand -hex 32 > .secrets/postgres-password
test -s .secrets/service-db-password || openssl rand -hex 32 > .secrets/service-db-password
# docker compose (unlike Swarm) bind-mounts file secrets as-is, so this one
# must be readable by the postgres image's unprivileged "postgres" OS user
# (uid 70), not just the host user who created it. init.sql hard-fails
# startup if it still can't read the password, so this step isn't optional.
chmod 644 .secrets/service-db-password
export COMPOSE_PROJECT_NAME=rdp-mvp
docker compose build  # отдельный образ каждого приложения
cp .env.example .env  # заполнить своими значениями
docker compose up -d --no-build --wait
docker compose ps
curl -fsS http://127.0.0.1:8000/health
```

Только `127.0.0.1:8000` опубликован на хосте. Остальные соединения идут по внутренним сетям Compose. `infra/k8s/kafka.env` и `infra/k8s/init.sql` общие для двух окружений. Файл `.env` необязателен и относится к BFF. Секреты не отправляются в контекст сборки. Обычная остановка — `docker compose down`; `down -v` **удаляет данные**. SQL-инициализация выполняется на новом томе, не при каждом старте; смена файла пароля не меняет пароль уже созданной БД.

**Почему два секрета, а не один.** `postgres-password` — суперпользователь
`postgres`: имеет право создавать таблицы, роли и т.д., используется только
для накатывания миграций (`docker compose run --rm <сервис> alembic upgrade
head`), никогда не передаётся работающим сервисам. `service-db-password` —
общий пароль шести ролей `app_<сервис>` (по одной наименее privileged роли
на свою БД, см. `infra/k8s/init.sql`): они не могут создавать таблицы и не
могут подключиться к пяти чужим БД (изоляция на уровне ролей Postgres, а не
только сети). Если использовать один и тот же пароль для суперпользователя
и для прикладных ролей, утечка пароля приложения означала бы утечку
суперпользователя Postgres — отдельный секрет убирает этот риск, даже
несмотря на то что для шести ролей сам пароль один и тот же (см. комментарий
в `infra/k8s/init.sql`: изоляция обеспечивается *именем роли и правами*, а
не секретностью пароля).

## Тестовый Kubernetes с нуля

Проверено с Docker, **k3d 5.9.0**, **K3s v1.37.2+k3s1** и `kubectl`. У K3s по умолчанию есть local-path StorageClass и контроллер NetworkPolicy. Не отключайте его: одни YAML-политики без enforcement не защищают данные. Для другого кластера нужны динамические RWO PVC, соответствующий CNI и доступ узлов к образам. Gateway, LoadBalancer и HPA для этой задачи не нужны.

Сначала создайте секретный файл и соберите образы приложений как выше (запуск Compose не обязателен). Создайте **отдельный** кластер, не меняя текущий kube-context:

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
kubectl -n rdp-mvp create secret generic service-db-password --from-file=password=.secrets/service-db-password
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

У каждого предметного сервиса свой `services/<имя>/main.py` и собственный образ. В `packages/service-runtime` общие только сборка и транспорт. Для изменения ответа правьте файл владельца. Обращения к бизнес-RPC, HTTP и Kafka логируются через Loguru: `*.received` и `*.response` (у Kafka — `kafka.result`) связаны полем `call`. В логах видны тип запроса, тип ответа или код отказа; содержимое анкет, тела сообщений, токены и байты файлов не записываются. Смотреть: `docker compose logs -f screening` или `kubectl -n rdp-mvp logs -f deploy/screening`.

## Приёмочные проверки

Эти скрипты не нужны для запуска сервисов. Запускайте их из корня репозитория, когда все компоненты тестового стенда готовы.

| Когда запускать | Что проверяет скрипт |
| --- | --- |
| После изменения gRPC-ответов, обработки команд или сетевых правил | [`check-transport.sh`](check-transport.sh) проверяет статические ответы и ожидаемые отказы gRPC, отправляет тестовую команду через FastStream и по логам подтверждает её обработку сервисом Content. Также проверяет, что BFF не может напрямую подключиться к PostgreSQL, Kafka, SeaweedFS и Qdrant. Сервисы не перезапускает. |
| После изменения томов или конфигурации хранилищ | [`smoke.sh`](smoke.sh) проверяет наличие шести прикладных БД, записывает и читает SQL-строку, Kafka-сообщение, файл в SeaweedFS и точку в Qdrant. Затем пересоздаёт контейнеры или Pod этих четырёх компонентов и повторяет чтение. При успехе удаляет созданные тестовые объекты, сохраняя тома. |

**`smoke.sh` временно прерывает доступ к брокеру и хранилищам.** Используйте его только на тестовом стенде; перед запуском проверьте имя Compose-проекта или текущий контекст Kubernetes. При ошибке тестовые объекты могут остаться для диагностики.

### Docker Compose

```sh
export COMPOSE_PROJECT_NAME=rdp-mvp
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
