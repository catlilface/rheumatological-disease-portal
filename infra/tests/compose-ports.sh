#!/usr/bin/env bash
# Check the merged configs, including tools profiles, without starting containers.
set -euo pipefail
cd "$(dirname "$0")/../.."

check() {
  local ports
  ports=$(TAG_NAME=port-check docker compose --env-file .env.example --profile '*' "$@" config --format json | jq -r '
    .services | to_entries[] | .key as $service | .value |
    (select(.network_mode == "host") | "\($service) uses host networking"),
    (.ports[]? | "\($service) \(.published):\(.target)/\(.protocol)")')
  if [[ $ports != 'frontend 8080:80/tcp' ]]; then
    printf 'Unexpected host exposure (%s):\n%s\n' "$*" "$ports" >&2
    return 1
  fi
}

check -f compose.yaml
check -f compose.yaml -f infra/bff-delivery.compose.yaml
check -f deploy.yml
