.PHONY: up down migrate test-db prepare

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
