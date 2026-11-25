.PHONY: up down migrate test-db prepare test-kind test-infra

up: migrate
	docker compose up --build -d --wait

prepare:
	@sh infra/db/prepare.sh

migrate: prepare
	docker compose up -d --wait postgres
	docker compose run --rm --no-deps db-bootstrap
	docker compose run --rm --no-deps db-migrate

down:
	docker compose down

test-db:
	bash infra/db/test.sh

test-infra:
	bash infra/tests/smoke-guards.sh
	bash infra/tests/secret-guards.sh

test-kind:
	bash infra/kind/check.sh

.PHONY: test-bff-kafka
test-bff-kafka:
	bash infra/db/test-bff-kafka.sh
