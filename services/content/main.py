import asyncio

from grpc import StatusCode
from contracts.commands.v1.content_pb2 import ContentCommand
from contracts.common.v1.content_pb2 import DoctorRoute
from contracts.grpc.v1 import content_pb2 as api, content_pb2_grpc as rpc
from runtime import reply, serve


class Content(rpc.ContentQueryServiceServicer):
    ListPublishedArticles = reply(api.ListPublishedArticlesResponse(total=0), summary='empty_page')
    GetPublishedArticle = GetOperation = reply(error=StatusCode.NOT_FOUND)
    GetArticle = GetCurrentArticle = reply(error=StatusCode.PERMISSION_DENIED)
    GetDoctorRoute = reply(DoctorRoute(route_id='demo', version=1, title='Демонстрационный маршрут'), summary='demo_route')


if __name__ == '__main__':
    asyncio.run(serve('content', rpc.add_ContentQueryServiceServicer_to_server, Content(), ContentCommand))
