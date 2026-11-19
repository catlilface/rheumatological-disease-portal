import asyncio

from grpc import StatusCode
from contracts.grpc.v1 import iam_pb2 as api, iam_pb2_grpc as rpc
from runtime import reply, serve


class IAM(rpc.IamServiceServicer):
    CheckAccess = reply(api.AccessDecision(allowed=False, reason_code='ACCESS_DENIED'), summary='access_denied')
    Authenticate = SignInStaff = RefreshTokens = reply(error=StatusCode.UNAUTHENTICATED)
    CreateGuestSession = reply(error=StatusCode.UNAVAILABLE)


if __name__ == '__main__':
    asyncio.run(serve('iam', rpc.add_IamServiceServicer_to_server, IAM()))
