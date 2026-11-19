import asyncio

from grpc import StatusCode
from contracts.grpc.v1 import files_pb2_grpc as rpc
from runtime import reply, serve


class Files(rpc.FilesQueryServiceServicer):
    # Until authorization is implemented, do not disclose even file metadata.
    GetFile = DownloadFile = reply(error=StatusCode.PERMISSION_DENIED)


if __name__ == '__main__':
    asyncio.run(serve('files', rpc.add_FilesQueryServiceServicer_to_server, Files()))
