#!/usr/bin/env bash
# Regression: Bash 3.2 does not apply errexit to a bare [[ ... ]] failure.
set -euo pipefail
cd "$(dirname "$0")/../.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/kubectl" <<'MOCK'
#!/usr/bin/env bash
set -eu
for arg; do last=$arg; done
case "$*" in
  'config current-context') echo kind-smoke-test;;
  *'SELECT datname'*)
    [[ $GUARD_CASE != missing-db ]] || exit 0
    db=${last#*datname=\'}; db=${db%\'}
    printf '%s\n' "$db"
    ;;
  *'CREATE TABLE'*) touch "$TEST_WRITES";;
  *'SELECT v FROM'*)
    [[ $GUARD_CASE != missing-sql ]] || exit 0
    printf '%s\n' "${last##*FROM }"
    ;;
  *kafka-console-consumer.sh*)
    [[ $GUARD_CASE != wrong-kafka ]] || { echo wrong-message; exit 0; }
    for arg; do case "$arg" in infra.smoke_*) printf '%s\n' "${arg#infra.}";; esac; done
    ;;
  *'delete pod postgres-0'*) touch "$TEST_RESTARTS";;
esac
MOCK
chmod +x "$tmp/kubectl"
for scenario in missing-db missing-sql wrong-kafka; do
  export GUARD_CASE=$scenario TEST_WRITES="$tmp/$scenario-writes" TEST_RESTARTS="$tmp/$scenario-restarts"
  if PATH="$tmp:$PATH" KUBECONFIG="$tmp/test-kubeconfig" bash infra/smoke.sh k8s >"$tmp/output" 2>&1; then
    echo "FAIL: $scenario was reported as successful" >&2; exit 1
  fi
  case $scenario in
    missing-db) reason='Missing database:';;
    missing-sql) reason='SQL marker missing';;
    wrong-kafka) reason='Kafka marker missing';;
  esac
  grep -Fq "$reason" "$tmp/output" || { echo "FAIL: $scenario failed for the wrong reason" >&2; exit 1; }
  if [[ -e $TEST_RESTARTS || ( $scenario == missing-db && -e $TEST_WRITES ) ]]; then
    echo "FAIL: $scenario continued after a failed assertion" >&2; exit 1
  fi
done
echo 'OK: smoke guards reject missing databases, lost SQL data and wrong Kafka messages'
