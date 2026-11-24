"""Transport support only. Domain responses are defined by the owning service."""
import asyncio
import os
import signal
from uuid import uuid4

import grpc
from faststream.confluent import KafkaBroker
from google.protobuf.message import DecodeError
from grpc_health.v1 import health, health_pb2_grpc
from loguru import logger

from database import check_database


def reply(response=None, *, error=None, summary=''):
    """Static gRPC outcome. Log types and status, never payloads or credentials."""
    async def handle(self, request, context):
        call = uuid4().hex
        method = request.DESCRIPTOR.full_name
        logger.info('grpc.received call={} request={}', call, method)
        if error is not None:
            logger.info('grpc.response call={} request={} status={}', call, method, error.name)
            await context.abort(error, 'Static development response')
        logger.info('grpc.response call={} request={} status=OK response={} result={}',
                    call, method, response.DESCRIPTOR.full_name, summary)
        return response
    return handle


async def serve(name, register, handlers, command_type=None):
    if 'PGHOST' in os.environ:  # Both local Compose and Kubernetes verify owner migrations.
        check_database(name)
    server = grpc.aio.server()
    register(handlers, server)
    health_pb2_grpc.add_HealthServicer_to_server(health.aio.HealthServicer(), server)
    server.add_insecure_port('[::]:50051')
    stopped = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stopped.set)

    broker = None
    if command_type is not None:
        topic = f'dev.{name}.commands.v1'
        broker = KafkaBroker(os.environ['KAFKA_BOOTSTRAP_SERVERS'], logger=None)

        @broker.subscriber(topic, group_id=f'dev-{name}', auto_offset_reset='earliest')
        async def receive(body: bytes):
            call = uuid4().hex
            logger.info('kafka.received call={} topic={} type={}', call, topic, command_type.DESCRIPTOR.name)
            try:
                cmd = command_type.FromString(body)
                action = cmd.WhichOneof('payload')
                if not cmd.HasField('metadata') or not action:
                    raise ValueError('Missing command metadata or payload')
            except (DecodeError, ValueError):
                logger.warning('kafka.result call={} topic={} outcome=invalid', call, topic)
                raise
            logger.info('kafka.result call={} topic={} action={} outcome=accepted_static', call, topic, action)

        await broker.start()
    try:
        await server.start()
        await stopped.wait()
    finally:
        await server.stop(3)
        if broker is not None:
            await broker.stop()
