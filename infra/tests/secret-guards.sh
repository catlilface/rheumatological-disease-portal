#!/usr/bin/env bash
# A Secret read error is not NotFound; the installer must never overwrite it.
set -euo pipefail
cd "$(dirname "$0")/../.."
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
export KUBECONFIG="$tmp/kubeconfig" MIS_SECRET_DIR="$tmp/credentials" WRITES="$tmp/writes"
cat > "$tmp/kubectl" <<'MOCK'
#!/usr/bin/env bash
case "$*" in
  'config current-context') echo kind-guard;;
  *"get secret $DENY_SECRET"*) echo 'Forbidden' >&2; exit 1;;
  *"create secret generic $DENY_SECRET"*) touch "$WRITES"; exit 1;;
  *'apply -f -'*) cat >/dev/null;;
esac
MOCK
chmod +x "$tmp/kubectl"
for secret in postgres-password db-app-iam; do
  if PATH="$tmp:$PATH" DENY_SECRET=$secret bash infra/k8s/up.sh >"$tmp/output" 2>&1 || [[ -e $WRITES ]]; then
    echo "FAIL: installer attempted to write $secret after a read error" >&2; exit 1
  fi
  grep -Fq Forbidden "$tmp/output" || { echo 'FAIL: Secret read error was hidden' >&2; exit 1; }
done
echo 'OK: Secret read errors stop deployment before credential writes'
