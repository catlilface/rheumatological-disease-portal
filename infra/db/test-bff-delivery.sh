#!/usr/bin/env bash
set -euo pipefail
postgres=
kafka=
cleanup() {
    if [[ -n $kafka ]]; then docker rm -f -v "$kafka" >/dev/null || true; fi
    if [[ -n $postgres ]]; then docker rm -f -v "$postgres" >/dev/null || true; fi
}
trap cleanup EXIT

TEST_PGPASSWORD=$(openssl rand -hex 24)
port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')
postgres=$(docker run -d --rm -p 127.0.0.1::5432 -e POSTGRES_PASSWORD="$TEST_PGPASSWORD" postgres:18.7-alpine3.23)
kafka=$(docker run -d --rm -p "127.0.0.1:$port:$port" \
    -e KAFKA_NODE_ID=1 -e KAFKA_PROCESS_ROLES=broker,controller \
    -e "KAFKA_LISTENERS=CLIENT://:$port,CONTROLLER://:9093" \
    -e "KAFKA_ADVERTISED_LISTENERS=CLIENT://127.0.0.1:$port" \
    -e KAFKA_LISTENER_SECURITY_PROTOCOL_MAP=CLIENT:PLAINTEXT,CONTROLLER:PLAINTEXT \
    -e KAFKA_INTER_BROKER_LISTENER_NAME=CLIENT -e KAFKA_CONTROLLER_LISTENER_NAMES=CONTROLLER \
    -e KAFKA_CONTROLLER_QUORUM_VOTERS=1@localhost:9093 \
    -e KAFKA_HEAP_OPTS="-Xms128m -Xmx256m" \
    -e KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR=1 -e KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS=0 \
    "${TEST_KAFKA_IMAGE:-apache/kafka:4.4.0}")

for i in {1..60}; do
    if docker exec "$postgres" pg_isready -h 127.0.0.1 >/dev/null &&
       docker exec "$kafka" /opt/kafka/bin/kafka-topics.sh --bootstrap-server "127.0.0.1:$port" --list >/dev/null 2>&1; then
        break
    fi
    if [[ $i == 60 ]]; then docker logs "$kafka"; docker logs "$postgres"; exit 1; fi
    sleep 1
done

export TEST_PGPASSWORD TEST_PGHOST=127.0.0.1
export TEST_PGPORT TEST_KAFKA_BROKERS="127.0.0.1:$port"
TEST_PGPORT=$(docker port "$postgres" 5432/tcp)
TEST_PGPORT=${TEST_PGPORT##*:}

docker exec -i "$postgres" psql -X -U postgres -v ON_ERROR_STOP=1 <<'SQL'
CREATE ROLE migrator;
CREATE ROLE app LOGIN;
SQL
docker exec -i "$postgres" psql -X -U postgres -v ON_ERROR_STOP=1 -v password="$TEST_PGPASSWORD" <<'SQL'
ALTER ROLE app PASSWORD :'password';
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE, CREATE ON SCHEMA public TO migrator;
SET ROLE migrator;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO app;
SQL
for migration in services/bff/migrations/*.sql; do
    {
        printf 'BEGIN;\nSET ROLE migrator;\n'
        sed '/^-- migrate:down/,$d' "$migration"
        printf 'COMMIT;\n'
    } | docker exec -i "$postgres" psql -X -U postgres -v ON_ERROR_STOP=1
done

export TEST_DELIVERY_DSN="postgres://app:$TEST_PGPASSWORD@$TEST_PGHOST:$TEST_PGPORT/postgres?sslmode=disable"
(cd services/bff && go test -race -count=1 -v ./pkg/delivery && go test -race -count=1 -v ./app -run TestDeliveryHTTPRecovery)
