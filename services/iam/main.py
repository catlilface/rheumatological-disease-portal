from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from pathlib import Path
import signal
import threading

import grpc
from google.protobuf.empty_pb2 import Empty
from grpc_health.v1 import health, health_pb2_grpc
from loguru import logger
from pg8000.exceptions import Error as DatabaseError

from contracts.grpc.v1 import iam_pb2_grpc as rpc
from .sessions import Authority, Denied, connect_db


def authority():
    return Authority(connect_db, bytes.fromhex(Path('/run/secrets/iam-key').read_text().strip()))


def bff_only(method):
    @wraps(method)
    def call(self, request, context):
        if context.auth_context().get('x509_common_name') != [b'bff']:
            context.abort(grpc.StatusCode.PERMISSION_DENIED, 'Service not authorized')
        try:
            return method(self, request)
        except Denied as error:
            context.abort(error.status, error.status.name)
        except (DatabaseError, OSError):
            # Driver errors may include statement parameters. Do not log them.
            logger.error('IAM database unavailable: {}', method.__name__)
            context.abort(grpc.StatusCode.UNAVAILABLE, 'AUTHORIZATION_UNAVAILABLE')
    return call


class IAM(rpc.IamServiceServicer):
    def __init__(self, sessions):
        self.sessions = sessions

    @bff_only
    def CreateGuestSession(self, req):
        return self.sessions.guest(req.request_id, req.access_token)

    @bff_only
    def SignInStaff(self, req):
        return self.sessions.sign_in(req.email, req.password)

    @bff_only
    def RefreshTokens(self, req):
        return self.sessions.rotate(req.refresh_token)

    @bff_only
    def Authenticate(self, req):
        return self.sessions.authenticate(req.access_token)

    @bff_only
    def EndSession(self, req):
        self.sessions.end(req.access_token)
        return Empty()

    @bff_only
    def CheckAccess(self, req):
        return self.sessions.check(req)


def main():
    tls = Path('/run/iam-tls')
    creds = grpc.ssl_server_credentials([((tls/'tls.key').read_bytes(), (tls/'tls.crt').read_bytes())],
                                        root_certificates=(tls/'ca.crt').read_bytes(), require_client_auth=True)
    sessions = authority()
    with sessions.transaction() as cur:
        cur.execute('SELECT token_hash FROM session_refresh_tokens LIMIT 0')
    server = grpc.server(ThreadPoolExecutor(max_workers=8), maximum_concurrent_rpcs=32,
                         options=[('grpc.max_receive_message_length', 16384)])
    rpc.add_IamServiceServicer_to_server(IAM(sessions), server)
    health_pb2_grpc.add_HealthServicer_to_server(health.HealthServicer(), server)
    server.add_secure_port('[::]:50051', creds)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    server.start()
    stop.wait()
    server.stop(3).wait()


if __name__ == '__main__':
    main()
