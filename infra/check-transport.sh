#!/usr/bin/env bash
# Check real gRPC calls, Kafka consumption and denied sockets from the BFF.
set -euo pipefail
case ${1:?usage: bash infra/check-transport.sh compose|k8s} in
 compose) run() { docker compose exec -T "$@"; }; logs() { docker compose logs --since "$1" content; };;
 k8s) run() { local s=$1; shift; kubectl -n rdp-mvp exec -i "deploy/$s" -- "$@"; }; logs() { kubectl -n rdp-mvp logs deploy/content --since-time="$1"; };;
 *) exit 2;;
esac
run bff sh -eu <<'SH'
# First prove that the probe itself works from this container.
nc -z -w 2 127.0.0.1 8000
for endpoint in postgres:5432 qdrant:6333 seaweedfs:8888 kafka:19092; do
    if nc -z -w 2 "${endpoint%:*}" "${endpoint#*:}"; then
        echo "unexpected direct access: $endpoint" >&2
        exit 1
    fi
done
SH
run files python - <<'PY'
import grpc
from contracts.grpc.v1 import iam_pb2 as p, iam_pb2_grpc as g
with grpc.insecure_channel('iam:50051') as channel:
    decision=g.IamServiceStub(channel).CheckAccess(p.CheckAccessRequest(), timeout=5)
    assert not decision.allowed and decision.reason_code=='ACCESS_DENIED'
PY
run content python - <<'PY'
import grpc
from contracts.grpc.v1 import content_pb2 as p, content_pb2_grpc as g
with grpc.insecure_channel('localhost:50051') as channel:
    page = g.ContentQueryServiceStub(channel).ListPublishedArticles(p.ListPublishedArticlesRequest(), timeout=5)
    assert page.HasField('total') and page.total == 0 and not page.articles
PY
run screening python - <<'PY'
import grpc
from contracts.grpc.v1 import screening_pb2 as p, screening_pb2_grpc as g
with grpc.insecure_channel('localhost:50051') as channel:
    survey = g.ScreeningQueryServiceStub(channel).GetSurvey(p.GetSurveyRequest(), timeout=5)
    assert survey.definition['id'] == survey.reference.survey_id and survey.disclaimer
PY
run reporting python - <<'PY'
import grpc
from contracts.grpc.v1 import files_pb2, files_pb2_grpc, reporting_pb2, reporting_pb2_grpc
for host, expected in [('files',grpc.StatusCode.PERMISSION_DENIED), ('localhost',grpc.StatusCode.NOT_FOUND)]:
    with grpc.insecure_channel(host+':50051') as channel:
        try:
            if host=='files': list(files_pb2_grpc.FilesQueryServiceStub(channel).DownloadFile(files_pb2.DownloadFileRequest(), timeout=5))
            else: reporting_pb2_grpc.ReportingQueryServiceStub(channel).GetReport(reporting_pb2.GetReportRequest(), timeout=5)
        except grpc.RpcError as exc: assert exc.code()==expected, exc.code()
        else: raise AssertionError('expected fixed denial or not-found response')
PY
start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
run content python - <<'PY'
import asyncio, uuid
from faststream.confluent import KafkaBroker
from contracts.commands.v1.content_pb2 import ContentCommand
async def send():
    cmd=ContentCommand(); cmd.metadata.command_id=str(uuid.uuid4()); cmd.create.SetInParent()
    async with KafkaBroker('kafka:19092') as broker:
        await broker.publish(cmd.SerializeToString(), topic='dev.content.commands.v1')
asyncio.run(send())
PY
for _ in {1..20}; do
  if logs "$start" | grep 'topic=dev.content.commands.v1 action=create outcome=accepted_static' >/dev/null; then echo 'OK: isolation, gRPC, FastStream'; exit 0; fi
  sleep 1
done
echo 'Timed out waiting for Content consumer' >&2; exit 1
