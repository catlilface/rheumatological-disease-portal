import asyncio

from grpc import StatusCode
from contracts.commands.v1.reporting_pb2 import ReportingCommand
from contracts.grpc.v1 import reporting_pb2_grpc as rpc
from runtime import reply, serve


class Reporting(rpc.ReportingQueryServiceServicer):
    # No reports or operations have been generated on the static stand.
    GetReport = GetOperation = reply(error=StatusCode.NOT_FOUND)


if __name__ == '__main__':
    asyncio.run(serve('reporting', rpc.add_ReportingQueryServiceServicer_to_server, Reporting(), ReportingCommand))
