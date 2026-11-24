#!/usr/bin/env bash
# Fresh disposable cluster. Existing Compose containers and kube-contexts are untouched.
set -euo pipefail
cd "$(dirname "$0")/../.."
for tool in docker kind kubectl python3 openssl; do command -v "$tool" >/dev/null; done
mkdir -p .secrets
work=$(mktemp -d "$PWD/.secrets/kind-check.XXXXXXXX")
export KUBECONFIG="$work/kubeconfig" MIS_SECRET_DIR="$work/credentials"
cluster="rdp-check-$$"
created=0
forward_pid=
cleanup() {
  code=$?
  trap - EXIT
  if [[ $created == 1 ]]; then
    kubectl -n rdp-mvp get pods,pvc >"$work/status.txt" 2>&1 || true
    kubectl -n rdp-mvp get events --sort-by=.lastTimestamp >"$work/events.txt" 2>&1 || true
    if [[ $code != 0 ]]; then
      for workload in $(kubectl -n rdp-mvp get deploy,sts,job -o name 2>/dev/null); do
        kubectl -n rdp-mvp logs "$workload" --all-containers=true --tail=80 >"$work/${workload//\//-}.log" 2>&1 || true
      done
    fi
  fi
  [[ -z $forward_pid ]] || { kill "$forward_pid" 2>/dev/null || true; wait "$forward_pid" 2>/dev/null || true; }
  if [[ $created == 1 && ${KEEP_KIND:-0} != 1 ]]; then kind delete cluster --name "$cluster"; fi
  echo "Check artifacts: $work (exit=$code)"
  exit "$code"
}
trap cleanup EXIT
sh infra/db/prepare.sh
docker compose build
# kind load docker-image can encounter incomplete multi-arch indices on Docker Desktop.
# Export only the node's platform, including infrastructure images for offline node startup.
images=(rdp-bff:mvp rdp-iam:mvp rdp-screening:mvp rdp-content:mvp rdp-reporting:mvp rdp-files:mvp rdp-ai:mvp
  postgres:18.7-alpine3.23 apache/kafka:4.4.0 chrislusf/seaweedfs:4.54 qdrant/qdrant:v1.20.2 ghcr.io/amacneil/dbmate:2.38.2)
for image in "${images[@]}"; do docker image inspect "$image" >/dev/null 2>&1 || docker pull "$image"; done
platform=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
docker save --platform "$platform" -o "$work/images.tar" "${images[@]}"
# Refuse accidental reuse: the script only deletes a cluster it created itself.
clusters=$(kind get clusters)
if grep -Fxq "$cluster" <<< "$clusters"; then echo "Cluster exists: $cluster" >&2; exit 1; fi
kind create cluster --name "$cluster" --image kindest/node:v1.37.0 --kubeconfig "$KUBECONFIG" --wait 120s
created=1
kind load image-archive "$work/images.tar" --name "$cluster"
rm "$work/images.tar"
kubectl apply -f infra/kind/network-policy.yaml
kubectl -n kube-system rollout status daemonset/kube-router --timeout=180s
bash infra/k8s/up.sh
bash infra/k8s/check-db.sh
bash infra/check-transport.sh k8s
kubectl -n rdp-mvp port-forward --address=127.0.0.1 svc/bff 0:8000 >"$work/port-forward.log" 2>&1 &
forward_pid=$!
port=
for _ in {1..30}; do
  port=$(awk '/Forwarding from 127.0.0.1:/ {split($3,p,":"); print p[2]; exit}' "$work/port-forward.log")
  [[ -z $port ]] || break
  sleep 1
done
[[ -n $port ]] || { echo 'Port-forward did not start' >&2; exit 1; }
python3 infra/k8s/check-http.py "http://127.0.0.1:$port"
# Model an old scaffold PVC on the second run; keep its data, not its PUBLIC grants.
admin() { kubectl -n rdp-mvp exec -i postgres-0 -- psql -XqAt -v ON_ERROR_STOP=1 -U postgres -d "$@"; }
admin postgres < infra/k8s/init.sql
admin iam -c 'CREATE TABLE legacy_marker AS SELECT 42 AS v'
history=$(admin mis_screening -c 'SELECT version,xmin FROM migration.schema_migrations ORDER BY version')
bash infra/k8s/up.sh
[[ $(admin iam -c 'SELECT v FROM legacy_marker') == 42 ]] || { echo 'Lost legacy data' >&2; exit 1; }
legacy_access=$(admin postgres -c "SELECT count(*) FROM pg_roles CROSS JOIN pg_database
  WHERE rolname ~ '^mis_.*_(app|migrator)$' AND datname IN ('iam','screening','content','reporting','files','ai')
    AND has_database_privilege(rolname, datname, 'CONNECT')")
[[ $legacy_access == 0 ]] || { echo 'Service roles can connect to legacy databases' >&2; exit 1; }
[[ -n $history && $(admin mis_screening -c 'SELECT version,xmin FROM migration.schema_migrations ORDER BY version') == "$history" ]] || { echo 'Migration history changed on repeated deployment' >&2; exit 1; }
bash infra/smoke.sh k8s
bash infra/k8s/check-db.sh
bash infra/check-transport.sh k8s
echo 'OK: kind, migrations, real app roles, isolation, HTTP/gRPC/Kafka and persistence'
