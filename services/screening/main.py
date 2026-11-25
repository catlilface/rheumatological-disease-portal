import asyncio
import json
import os
from pathlib import Path

from grpc import StatusCode
from contracts.commands.v1.screening_pb2 import ScreeningCommand
from contracts.common.v1 import metadata_pb2 as metadata
from contracts.common.v1.screening_pb2 import Survey
from contracts.grpc.v1 import screening_pb2_grpc as rpc
from runtime import reply, serve

from .postgres_store import PostgresScreeningStore, connect_screening
from .rules import RuleRegistry
from .storage import (
    DEMO_DISCLAIMER, DEMO_DISCLAIMER_VERSION, InMemoryScreeningStore, ResultSnapshotUnavailable, StoredOperation,
)
from .workflow import (
    InvalidCommand, ScreeningWorkflow, result_message, session_message,
)


def survey_message(data, disclaimer=DEMO_DISCLAIMER, disclaimer_version=DEMO_DISCLAIMER_VERSION):
    survey = Survey(disclaimer=disclaimer, disclaimer_version=disclaimer_version)
    survey.reference.survey_id = data['id']
    survey.reference.weights_version = data['weights_version']
    survey.definition.update(data)
    return survey


class Screening(rpc.ScreeningQueryServiceServicer):
    _static_rules = json.loads(Path(__file__).with_name('survey.json').read_text(encoding='utf-8'))
    GetSurvey = reply(survey_message(_static_rules), summary='demo_survey')
    GetSession = GetSessionResult = GetResult = GetOperation = reply(error=StatusCode.NOT_FOUND)


class MockScreening(Screening):
    """Read and write synthetic data in the opt-in local environment."""

    def __init__(self, workflow: ScreeningWorkflow, default_survey: str):
        self.workflow = workflow
        self.default_survey = default_survey

    async def handle_command(self, command: ScreeningCommand) -> str:
        try:
            operation = await asyncio.to_thread(self.workflow.execute, command)
        except InvalidCommand:
            return 'invalid'
        return 'succeeded' if operation.state == metadata.OPERATION_STATE_SUCCEEDED else 'rejected'

    async def _read(self, query):
        def read_transaction():
            with self.workflow.storage.transaction() as transaction:
                return query(transaction)

        return await asyncio.to_thread(read_transaction)

    async def _read_result(self, query, subject, context):
        try:
            return await self._read(query)
        except ResultSnapshotUnavailable as error:
            await self._check_owner(error, subject, context)
            await context.abort(StatusCode.FAILED_PRECONDITION, str(error))

    async def GetSurvey(self, request, context):
        survey_id = request.survey_id or self.default_survey
        version = request.weights_version if request.HasField('weights_version') else None
        try:
            questionnaire = await self._read(lambda transaction: transaction.get_questionnaire(survey_id, version))
        except KeyError:
            await context.abort(StatusCode.NOT_FOUND, 'Survey version was not found.')
        return survey_message(questionnaire.rules, questionnaire.disclaimer, questionnaire.disclaimer_version)

    async def GetSession(self, request, context):
        subject = await self._subject(request.context, context)
        session = await self._read(lambda transaction: transaction.get_session(request.session_id))
        await self._check_owner(session, subject, context)
        return session_message(session)

    async def GetSessionResult(self, request, context):
        subject = await self._subject(request.context, context)
        session, result = await self._read_result(lambda transaction: (
            transaction.get_session(request.session_id),
            transaction.get_latest_result(request.session_id),
        ), subject, context)
        await self._check_owner(session, subject, context)
        if result is None:
            await context.abort(StatusCode.FAILED_PRECONDITION, 'Screening result is not ready.')
        return result_message(result)

    async def GetResult(self, request, context):
        subject = await self._subject(request.context, context)
        if not request.result.result_id or not request.result.version:
            await context.abort(StatusCode.INVALID_ARGUMENT, 'An exact result version is required.')
        result = await self._read_result(
            lambda transaction: transaction.get_result(request.result.result_id, request.result.version),
            subject, context,
        )
        await self._check_owner(result, subject, context)
        return result_message(result)

    async def GetOperation(self, request, context):
        subject = await self._subject(request.context, context)
        operation = await self._read(lambda transaction: transaction.get_operation(request.operation_id))
        if not isinstance(operation, StoredOperation):
            await context.abort(StatusCode.NOT_FOUND, 'Screening resource was not found.')
        await self._check_owner(operation, subject, context)
        return metadata.Operation.FromString(operation.response)

    @staticmethod
    async def _subject(request_context, context):
        actor = request_context.actor
        if not actor.subject_id.strip() or not actor.session_id.strip():
            await context.abort(StatusCode.UNAUTHENTICATED, 'Mock actor context is required.')
        return actor.subject_id

    @staticmethod
    async def _check_owner(record, subject, context):
        if record is None:
            await context.abort(StatusCode.NOT_FOUND, 'Screening resource was not found.')
        if record.subject_id != subject:
            await context.abort(StatusCode.PERMISSION_DENIED, 'Screening resource access denied.')


def build_mock_screening() -> MockScreening:
    path = Path(__file__).parent / 'tests' / 'fixtures' / 'example_rules.json'
    backend = os.environ.get('SCREENING_STORAGE', 'memory')
    if backend == 'postgres':
        storage = PostgresScreeningStore(connect_screening)
        storage.publish(path, disclaimer_version=DEMO_DISCLAIMER_VERSION, disclaimer=DEMO_DISCLAIMER)
    elif backend == 'memory':
        rules = RuleRegistry()
        rules.publish(path)
        storage = InMemoryScreeningStore(rules)
    else:
        raise ValueError('SCREENING_STORAGE must be memory or postgres')
    return MockScreening(ScreeningWorkflow(storage), 'example')


async def main():
    mock = os.environ.get('SCREENING_MOCK') == '1'
    screening = build_mock_screening() if mock else Screening()
    await serve(
        'screening', rpc.add_ScreeningQueryServiceServicer_to_server, screening, ScreeningCommand,
        command_handler=screening.handle_command if mock else None,
    )


if __name__ == '__main__':
    asyncio.run(main())
