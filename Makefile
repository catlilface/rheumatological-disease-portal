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

BFF_DELIVERY_COMPOSE := docker compose -f compose.yaml -f infra/bff-delivery.compose.yaml

.PHONY: up-bff-delivery test-bff-delivery

up-bff-delivery:
	@MIS_BFF_DB=true sh infra/db/prepare.sh
	$(BFF_DELIVERY_COMPOSE) up -d --wait postgres kafka
	$(BFF_DELIVERY_COMPOSE) run --rm --no-deps db-bootstrap
	$(BFF_DELIVERY_COMPOSE) run --rm --no-deps db-migrate
	$(BFF_DELIVERY_COMPOSE) up --build -d --wait bff

test-bff-delivery:
	bash infra/db/test-bff-delivery.sh
