#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${KUBECONFIG:?Set an explicit kubeconfig for the test cluster}"
case $(kubectl config current-context) in kind-*|k3d-*) ;; *) echo 'Refusing non-local cluster' >&2; exit 1;; esac
for owner in iam screening content reporting files ai; do
  kubectl -n rdp-mvp exec -i "deploy/$owner" -- python -c "$(<infra/k8s/check-db.py)" "$owner" < "infra/db/tests/$owner.sql"
done
