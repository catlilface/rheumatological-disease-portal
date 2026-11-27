"""Verify the forwarded access cookie with IAM; never use caller-supplied actor IDs as credentials."""
from pathlib import Path
from uuid import uuid4
import grpc
from contracts.grpc.v1 import iam_pb2, iam_pb2_grpc

TLS = Path('/run/iam-tls')

async def principal_for(context):
    if context.auth_context().get('x509_common_name') != [b'bff']:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, 'BFF certificate required')
    cookies = [v for k, v in context.invocation_metadata() if k == 'cookie']
    # BFF forwards only the access cookie, never refresh or the whole browser header.
    if len(cookies) != 1 or not cookies[0].startswith('portal_session=') or ';' in cookies[0]:
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Session required')
    token = cookies[0].removeprefix('portal_session=')
    credentials = grpc.ssl_channel_credentials((TLS/'ca.crt').read_bytes(), (TLS/'tls.key').read_bytes(), (TLS/'tls.crt').read_bytes())
    async with grpc.aio.secure_channel('iam:50051', credentials) as channel:
        try:
            principal = await iam_pb2_grpc.IamServiceStub(channel).Authenticate(iam_pb2.AuthenticateRequest(request_id=str(uuid4()), access_token=token), timeout=3)
        except grpc.aio.AioRpcError as exc:
            code = grpc.StatusCode.UNAUTHENTICATED if exc.code() == grpc.StatusCode.UNAUTHENTICATED else grpc.StatusCode.UNAVAILABLE
            await context.abort(code, 'Session verification failed')
    if not principal.is_guest and list(principal.roles) != [iam_pb2.USER_ROLE_PATIENT]:
        await context.abort(grpc.StatusCode.PERMISSION_DENIED, 'Patient or guest required')
    return principal.actor
