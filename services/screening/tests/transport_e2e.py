"""Disposable Compose runner ONLY: two distinct service identities and the real IAM database."""
import unittest
from pathlib import Path
from uuid import uuid4
import grpc
from contracts.common.v1 import metadata_pb2
from contracts.grpc.v1 import iam_pb2, iam_pb2_grpc, screening_pb2_grpc
from ..main import build_mock_screening


class AccessCookieTransport(unittest.IsolatedAsyncioTestCase):
    async def test_private_rpc_validates_cookie_not_actor_ids(self):
        tls = Path('/run/iam-tls')
        client = Path('/run/test-bff-tls')
        def credentials(directory):
            return grpc.ssl_channel_credentials((directory/'ca.crt').read_bytes(), (directory/'tls.key').read_bytes(), (directory/'tls.crt').read_bytes())
        async with grpc.aio.secure_channel('iam:50051', credentials(client)) as iam_channel:
            iam = iam_pb2_grpc.IamServiceStub(iam_channel)
            pair = await iam.CreateGuestSession(iam_pb2.CreateGuestSessionRequest(request_id=str(uuid4())), timeout=5)
            session = iam_pb2.AuthenticateRequest(access_token=pair.access_token)
            async with grpc.aio.secure_channel('iam:50051', credentials(tls)) as read_channel:
                restricted = iam_pb2_grpc.IamServiceStub(read_channel)
                self.assertEqual(await restricted.Authenticate(session, timeout=5), pair.principal)
                with self.assertRaises(grpc.aio.AioRpcError) as denied:
                    await restricted.EndSession(session, timeout=5)
                self.assertEqual(denied.exception.code(), grpc.StatusCode.PERMISSION_DENIED)
            server = grpc.aio.server()
            screening_pb2_grpc.add_ScreeningQueryServiceServicer_to_server(build_mock_screening(), server)
            port = server.add_secure_port('127.0.0.1:0', grpc.ssl_server_credentials([((tls/'tls.key').read_bytes(), (tls/'tls.crt').read_bytes())], (tls/'ca.crt').read_bytes(), require_client_auth=True))
            await server.start()
            self.addAsyncCleanup(server.stop, 0)
            async with grpc.aio.secure_channel(f'127.0.0.1:{port}', credentials(client), options=[('grpc.ssl_target_name_override', 'screening')]) as channel:
                rpc = screening_pb2_grpc.ScreeningQueryServiceStub(channel)
                request = metadata_pb2.GetOperationRequest(operation_id=str(uuid4()))
                request.context.actor.CopyFrom(pair.principal.actor)
                cookie = [('cookie', 'portal_session=' + pair.access_token)]
                async def expect(code, metadata):
                    with self.assertRaises(grpc.aio.AioRpcError) as denied:
                        await rpc.GetOperation(request, metadata=metadata, timeout=5)
                    self.assertEqual(denied.exception.code(), code)
                await expect(grpc.StatusCode.UNAUTHENTICATED, [])
                # A valid cookie reaches the real owner-scoped storage lookup.
                await expect(grpc.StatusCode.NOT_FOUND, cookie)
                request.context.actor.subject_id = str(uuid4())
                await expect(grpc.StatusCode.PERMISSION_DENIED, cookie)
                request.context.actor.CopyFrom(pair.principal.actor)
                await iam.EndSession(session, timeout=5)
                await expect(grpc.StatusCode.UNAUTHENTICATED, cookie)
