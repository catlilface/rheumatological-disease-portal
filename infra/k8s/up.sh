#!/usr/bin/env bash
# Disposable local clusters only. Never replaces existing database passwords or PVCs.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${KUBECONFIG:?Set an explicit kubeconfig for the local test cluster}"
context=$(kubectl config current-context)
case "$context" in kind-*|k3d-*) ;; *) echo "Refusing non-local context: $context" >&2; exit 1;; esac
export MIS_SECRET_DIR=${MIS_SECRET_DIR:-"$PWD/.secrets/k8s/$context"}
k=(kubectl -n rdp-mvp)
kubectl create namespace rdp-mvp --dry-run=client -o yaml | kubectl apply -f -
# Serialize config changes and Job recreation across installer processes.
"${k[@]}" create configmap db-deploy-lock
trap '"${k[@]}" delete configmap db-deploy-lock' EXIT
for job in db-bootstrap db-migrate; do
  state=$("${k[@]}" get job "$job" --ignore-not-found -o 'jsonpath={.metadata.name}:{.spec.suspend}:{.status.conditions[?(@.status=="True")].type}')
  case $state in ''|*:true:*|*Complete*|*Failed*) ;; *) echo "Job $job is not finished" >&2; exit 1;; esac
done
# A retained PVC still needs the old admin password, even if its Secret is missing.
admin_secret=$("${k[@]}" get secret postgres-password --ignore-not-found -o name)
pvc=$("${k[@]}" get pvc data-postgres-0 --ignore-not-found -o name)
if [[ -n $admin_secret$pvc && ! -s $MIS_SECRET_DIR/postgres-password ]]; then
  echo "Existing cluster requires its original MIS_SECRET_DIR; refusing new credentials" >&2; exit 1
fi
sh infra/db/prepare.sh
secret() {
  local current desired
  current=$("${k[@]}" get secret "$1" --ignore-not-found -o jsonpath='{.data}')
  if [[ -n $current ]]; then
    desired=$("${k[@]}" create secret generic "$@" --dry-run=client -o jsonpath='{.data}')
    [[ $current == "$desired" ]] || { echo "Credential mismatch for Secret $1; refusing rotation" >&2; exit 1; }
  else
    "${k[@]}" create secret generic "$@"
  fi
}
config() { "${k[@]}" create configmap "$@" --dry-run=client -o yaml | "${k[@]}" apply -f -; }
secret postgres-password --from-file="password=$MIS_SECRET_DIR/postgres-password"
secret iam-key --from-file="iam-key=$MIS_SECRET_DIR/iam-key"
for name in iam bff; do
  secret "iam-tls-$name" --from-file="$MIS_SECRET_DIR/iam-tls/$name"
done
bootstrap=(); migrators=()
for owner in iam screening content reporting files ai; do
  secret "db-app-$owner" --from-file="password=$MIS_SECRET_DIR/db/apps/$owner"
  bootstrap+=(--from-file="app-$owner=$MIS_SECRET_DIR/db/apps/$owner" --from-file="migrator-$owner=$MIS_SECRET_DIR/db/migrators/$owner")
  migrators+=(--from-file="$owner=$MIS_SECRET_DIR/db/migrators/$owner")
  config "db-migrations-$owner" --from-file="services/$owner/migrations"
done
secret db-bootstrap-passwords "${bootstrap[@]}"
secret db-migrator-passwords "${migrators[@]}"
config db-scripts --from-file=infra/db/bootstrap.sh --from-file=infra/db/migrate.sh
config db-common --from-file=infra/db/common
"${k[@]}" apply -f infra/k8s/postgres.yaml
"${k[@]}" rollout status statefulset/postgres --timeout=180s
"${k[@]}" delete job db-bootstrap db-migrate --ignore-not-found --wait=true
"${k[@]}" apply -f infra/k8s/db-jobs.yaml
wait_job() {
  local job=$1
  for _ in {1..150}; do
    [[ $("${k[@]}" get job "$job" -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}') == True ]] && return
    if [[ $("${k[@]}" get job "$job" -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}') == True ]]; then break; fi
    sleep 2
  done
  "${k[@]}" logs "job/$job" --all-containers=true || true
  echo "Job $job failed or timed out" >&2
  exit 1
}
wait_job db-bootstrap
"${k[@]}" patch job db-migrate --type=merge -p '{"spec":{"suspend":false}}'
wait_job db-migrate
"${k[@]}" apply -k infra/k8s
workloads=$("${k[@]}" get deploy,sts -o name)
for workload in $workloads; do
  "${k[@]}" rollout status "$workload" --timeout=300s
done
"${k[@]}" get pods,pvc
echo "OK: $context, six migrated databases and backend workloads are ready"
