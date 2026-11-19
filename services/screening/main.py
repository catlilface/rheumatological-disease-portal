import asyncio
import json
from pathlib import Path

from grpc import StatusCode
from contracts.commands.v1.screening_pb2 import ScreeningCommand
from contracts.common.v1.screening_pb2 import Survey
from contracts.grpc.v1 import screening_pb2_grpc as rpc
from runtime import reply, serve


def static_survey():
    data = json.loads(Path(__file__).with_name('survey.json').read_text())
    survey = Survey(disclaimer='Демонстрационная анкета, не медицинская рекомендация.',
                    disclaimer_version='demo-v1')
    survey.reference.survey_id = data['id']
    survey.reference.weights_version = data['weights_version']
    survey.definition.update(data)
    return survey


class Screening(rpc.ScreeningQueryServiceServicer):
    GetSurvey = reply(static_survey(), summary='demo_survey')
    GetSession = GetSessionResult = GetResult = GetOperation = reply(error=StatusCode.NOT_FOUND)


if __name__ == '__main__':
    asyncio.run(serve('screening', rpc.add_ScreeningQueryServiceServicer_to_server, Screening(), ScreeningCommand))
