.PHONY: up up-full secrets build down restart reset migrate test ps logs
# migrate-% and test-% are intentionally not listed here: GNU Make treats a
# literal name in .PHONY with no explicit rule as trivially satisfied, which
# would shadow the pattern rules below instead of running them.

SERVICES := iam screening content reporting files ai
COMPOSE := docker compose

## Generate the two dev-stand secrets if they don't exist yet (see infra/README.md).
secrets:
	@umask 077; mkdir -p .secrets
	@test -s .secrets/postgres-password || openssl rand -hex 32 > .secrets/postgres-password
	@test -s .secrets/service-db-password || openssl rand -hex 32 > .secrets/service-db-password
	@# docker compose bind-mounts file secrets as-is (unlike Swarm); the
	@# postgres image reads this one as its unprivileged "postgres" OS user
	@# (uid 70), not the host user who created it - init.sql hard-fails
	@# startup if it still can't read the password after this.
	@chmod 644 .secrets/service-db-password

build: secrets
	$(COMPOSE) build

## From a clean checkout: generate secrets, build every image, bring Postgres
## up, apply every service's migrations, then start bff/kafka.
up: build
	$(COMPOSE) up -d --no-build --wait postgres kafka
	$(MAKE) migrate
	$(COMPOSE) up -d --no-build --wait bff iam files screening content reporting

## Same as `up`, plus the object/vector stores (see infra/README.md) for the
## full stand, matching `docker compose up -d --no-build --wait`.
up-full: build
	$(COMPOSE) up -d --no-build --wait postgres kafka seaweedfs qdrant
	$(MAKE) migrate
	$(COMPOSE) up -d --no-build --wait bff iam files screening content reporting

## Apply migrations for every service, as the postgres superuser (the schema
## owner - not the app_<service> role). Safe to re-run: alembic skips
## revisions already applied to that database.
migrate: $(addprefix migrate-,$(SERVICES))

migrate-%:
	$(COMPOSE) run --rm $*-db

## Run one service's isolation/integrity/schema-contract tests, connecting
## as its least-privilege app_<service> role (not the migration superuser).
test-%:
	$(COMPOSE) run --rm -e DATABASE__USER=app_$* --entrypoint sh $*-db -c '\
		export $(shell echo $* | tr a-z A-Z)_DB_PASSWORD="$$(cat /run/secrets/service-db-password)"; \
		pytest -q'

test: $(addprefix test-,$(SERVICES))

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

restart:
	$(COMPOSE) restart postgres
	$(COMPOSE) up -d --wait postgres

down:
	$(COMPOSE) down

## Wipe every volume: next `make up` bootstraps roles/databases from scratch.
reset:
	$(COMPOSE) down -v
