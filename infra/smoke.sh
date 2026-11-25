#!/usr/bin/env bash
# Run only on the disposable MVP stack: recreates all four data containers/pods.
set -euo pipefail
mode=${1:?usage: bash infra/smoke.sh compose|k8s}
id="smoke_$(date +%s)_$$"
stores=(postgres kafka seaweedfs qdrant)
k=(kubectl -n rdp-mvp)
case $mode in
 compose)
   dc=(docker compose)
   run() { "${dc[@]}" exec -T "$@"; }
   vector() { run ai python - "$@"; }
   ;;
 k8s)
   : "${KUBECONFIG:?Set an explicit kubeconfig for the disposable test cluster}"
   case $(kubectl config current-context) in kind-*|k3d-*) ;; *) echo 'Refusing non-local cluster' >&2; exit 1;; esac
   run() { local s=$1; shift; "${k[@]}" exec -i "svc/$s" -- "$@"; }
   vector() { "${k[@]}" exec -i deploy/ai -- python - "$@"; }
   ;;
 *) exit 2;;
esac
sql() { run postgres psql -U postgres -d postgres -v ON_ERROR_STOP=1 -Atc "$1"; }
for db in content screening reporting files iam ai; do
  db=mis_$db
  [[ $(sql "SELECT datname FROM pg_database WHERE datname='$db'") == "$db" ]] || { echo "Missing database: $db" >&2; exit 1; }
done
sql "CREATE TABLE $id (v text); INSERT INTO $id VALUES ('$id')"
topic="infra.$id"
kbin=/opt/kafka/bin
run kafka "$kbin/kafka-topics.sh" --bootstrap-server localhost:19092 --create --topic "$topic" --partitions 1 --replication-factor 1
printf '%s\n' "$id" | run kafka "$kbin/kafka-console-producer.sh" --bootstrap-server localhost:19092 --topic "$topic"
object() { run files python - "$1" "$id" <<'PY'
import sys, urllib.request as u
op, marker = sys.argv[1:]
url = 'http://seaweedfs:8888/infra-smoke/' + marker
req = u.Request(url, method=op, data=marker.encode() if op=='PUT' else None)
with u.urlopen(req, timeout=10) as response:
    if op=='GET': assert response.read()==marker.encode()
PY
}
point() { vector "$1" "$id" <<'PY'
import json, sys, urllib.request as u
op, marker = sys.argv[1:]
url = 'http://qdrant:6333/collections/' + marker
def request(method, path='', body=None):
    data = None if body is None else json.dumps(body).encode()
    with u.urlopen(u.Request(url+path, data=data, method=method, headers={'Content-Type':'application/json'}), timeout=10) as r: return json.load(r)['result']
if op=='PUT':
    request('PUT', body={'vectors':{'size':2,'distance':'Dot'}})
    request('PUT','/points?wait=true',{'points':[{'id':1,'vector':[1,0],'payload':{'marker':marker}}]})
elif op=='GET': assert request('GET','/points/1')['payload']['marker']==marker
else: request('DELETE')
PY
}
object PUT; point PUT
verify() {
  [[ $(sql "SELECT v FROM $id") == "$id" ]] || { echo 'SQL marker missing' >&2; exit 1; }
  [[ $(run kafka "$kbin/kafka-console-consumer.sh" --bootstrap-server localhost:19092 --topic "$topic" --from-beginning --max-messages 1 --timeout-ms 15000) == "$id" ]] || { echo 'Kafka marker missing' >&2; exit 1; }
  object GET; point GET
}
verify
if [[ $mode == compose ]]; then
  "${dc[@]}" up -d --no-deps --force-recreate --wait "${stores[@]}"
else
  for s in "${stores[@]}"; do "${k[@]}" delete pod "$s-0"; done
  for s in "${stores[@]}"; do "${k[@]}" rollout status "statefulset/$s" --timeout=180s; done
fi
verify
sql "DROP TABLE $id"; object DELETE; point DELETE
run kafka "$kbin/kafka-topics.sh" --bootstrap-server localhost:19092 --delete --topic "$topic"
echo "OK: $mode, all four markers survived recreation"
