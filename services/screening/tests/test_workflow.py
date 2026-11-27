import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import grpc
from contracts.commands.v1.screening_pb2 import ScreeningCommand
from contracts.common.v1 import metadata_pb2 as metadata
from contracts.common.v1 import screening_pb2 as screening
from contracts.events.v1.screening_pb2 import ScreeningEvent
from contracts.grpc.v1 import screening_pb2 as queries
from contracts.grpc.v1 import screening_pb2_grpc as rpc

from services.screening.registry import LocalRegistry
from services.screening.storage import InMemoryScreeningStore
from services.screening.workflow import ScreeningWorkflow


EXAMPLE = Path(__file__).with_name("fixtures") / "example_rules.json"


def command(subject="guest"):
    message = ScreeningCommand()
    message.metadata.command_id = str(uuid4())
    message.metadata.operation_id = str(uuid4())
    message.metadata.correlation_id = "test-correlation"
    message.metadata.schema_version = 1
    message.metadata.actor.subject_id = subject
    message.metadata.actor.session_id = f"iam-{subject}"
    message.metadata.issued_at.FromDatetime(datetime.now(UTC))
    return message


def start_command():
    message = command()
    message.start.survey.survey_id = "example"
    message.start.survey.weights_version = "v1"
    message.start.disclaimer_version = "demo-v1"
    message.start.disclaimer_accepted = True
    message.start.disclaimer_accepted_at.CopyFrom(message.metadata.issued_at)
    return message


def complete_command(session_id, revision, subject="guest"):
    message = command(subject)
    message.complete.session_id = session_id
    message.complete.expected_session_version = revision
    return message


class FailingOutboxStore(InMemoryScreeningStore):
    fail_next_result_event = False

    @contextmanager
    def transaction(self):
        with super().transaction() as transaction:
            append_event = transaction.append_event

            def append_and_fail(event):
                append_event(event)
                if ScreeningEvent.FromString(event).HasField("result_changed"):
                    self.fail_next_result_event = False
                    raise OSError("outbox unavailable")

            if self.fail_next_result_event:
                with patch.object(transaction, "append_event", side_effect=append_and_fail):
                    yield transaction
            else:
                yield transaction


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.rules = LocalRegistry()
        self.rules.publish(EXAMPLE)
        self.storage = FailingOutboxStore(self.rules)
        self.workflow = ScreeningWorkflow(self.storage)

    def assert_succeeded(self, operation):
        self.assertEqual(operation.state, metadata.OPERATION_STATE_SUCCEEDED, operation.error)

    def start(self):
        result = self.workflow.execute(start_command())
        self.assert_succeeded(result)
        self.assertEqual(result.resources[0].version, 1)
        return result.resources[0].resource_id

    def session(self, session_id):
        with self.storage.transaction() as transaction:
            return transaction.get_session(session_id)

    def result(self, session_id):
        with self.storage.transaction() as transaction:
            return transaction.get_latest_result(session_id)

    def events(self, message=None):
        events = [ScreeningEvent.FromString(event) for event in self.storage.outbox_events()]
        if message is None:
            return events
        return [event for event in events if event.metadata.operation_id == message.metadata.operation_id]

    def save(self, session_id, code, value):
        message = command()
        message.save_answer.session_id = session_id
        message.save_answer.expected_session_version = self.session(session_id).version
        message.save_answer.answer.question_code = code
        if isinstance(value, bool):
            message.save_answer.answer.boolean_value = value
        else:
            message.save_answer.answer.choice_value = value
        result = self.workflow.execute(message)
        self.assert_succeeded(result)
        return message

    def ready_session(self):
        session_id = self.start()
        for code, value in (("A1", "zero"), ("Б1", True), ("В1", False), ("Г1", True)):
            self.save(session_id, code, value)
        return session_id

    def assert_event(self, event, message, saved):
        self.assertEqual(event.WhichOneof("payload"), "result_changed")
        self.assertEqual(event.metadata.schema_version, 1)
        self.assertEqual(event.metadata.source, "screening")
        self.assertEqual(event.metadata.entity_type, "screening_result")
        self.assertEqual(event.metadata.entity_id, saved.result_id)
        self.assertEqual(event.metadata.entity_version, saved.version)
        self.assertEqual(event.metadata.operation_id, message.metadata.operation_id)
        self.assertEqual(event.metadata.causation_id, message.metadata.command_id)
        self.assertEqual(event.metadata.correlation_id, message.metadata.correlation_id)
        self.assertTrue(event.metadata.event_id)
        snapshot = event.result_changed.result
        self.assertEqual(snapshot.reference.result_id, saved.result_id)
        self.assertEqual(snapshot.reference.version, saved.version)
        self.assertEqual(snapshot.survey.weights_version, saved.calculation.weights_version)
        self.assertEqual(snapshot.session_id, saved.session_id)
        self.assertEqual(snapshot.subject_id, saved.subject_id)
        return snapshot

    def assert_session_event(self, event, message, session_id, version, status, interrupted=False):
        self.assertEqual(event.WhichOneof("payload"), "session_changed")
        self.assertEqual(event.metadata.source, "screening")
        self.assertEqual(event.metadata.schema_version, 1)
        self.assertEqual(event.metadata.entity_type, "screening_session")
        self.assertEqual((event.metadata.entity_id, event.metadata.entity_version), (session_id, version))
        self.assertEqual(event.metadata.operation_id, message.metadata.operation_id)
        self.assertEqual(event.metadata.causation_id, message.metadata.command_id)
        self.assertEqual(event.metadata.correlation_id, message.metadata.correlation_id)
        self.assertTrue(event.metadata.event_id)
        self.assertTrue(event.metadata.HasField("occurred_at"))
        change = event.session_changed
        self.assertEqual(change.session_id, session_id)
        self.assertEqual((change.survey.survey_id, change.survey.weights_version), ("example", "v1"))
        self.assertEqual(change.status, status)
        self.assertEqual(change.interrupted_by_red_flag, interrupted)

    def test_session_events_track_start_ordinary_save_and_abandonment(self):
        start = start_command()
        operation = self.workflow.execute(start)
        self.assert_succeeded(operation)
        session_id = operation.resources[0].resource_id
        save = self.save(session_id, "A1", "four")
        abandon = command()
        abandon.abandon.session_id = session_id
        abandon.abandon.expected_session_version = 2
        outcome = self.workflow.execute(abandon)
        self.assert_succeeded(outcome)
        self.assertEqual(self.workflow.execute(abandon), outcome)

        started, answered, abandoned = self.events()
        self.assert_session_event(started, start, session_id, 1, screening.SESSION_STATUS_IN_PROGRESS)
        self.assert_session_event(answered, save, session_id, 2, screening.SESSION_STATUS_IN_PROGRESS)
        self.assert_session_event(abandoned, abandon, session_id, 3, screening.SESSION_STATUS_ABANDONED)
        self.assertEqual(len({event.metadata.event_id for event in self.events()}), 3)

    def test_complete_commits_explanation_and_mis22_events_and_retry_is_idempotent(self):
        session_id = self.ready_session()
        message = complete_command(session_id, self.session(session_id).version)
        first = self.workflow.execute(message)
        self.assert_succeeded(first)
        self.assertEqual(first, self.workflow.execute(message))
        session = self.session(session_id)
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.version, message.complete.expected_session_version + 1)
        self.assertIsNotNone(session.completed_at)
        saved = self.result(session_id)
        self.assertEqual(saved.version, 1)
        self.assertEqual(saved.calculation.matched_range, (5, 10))
        self.assertEqual(saved.calculation.reason, "score")
        self.assertEqual(saved.calculation.total_score, 10)
        self.assertEqual(
            [(r.resource_type, r.resource_id, r.version) for r in first.resources],
            [("screening_session", session_id, session.version), ("screening_result", saved.result_id, 1)],
        )
        session_event, event = self.events(message)
        self.assert_session_event(session_event, message, session_id, session.version,
                                  screening.SESSION_STATUS_COMPLETED)
        snapshot = self.assert_event(event, message, saved)
        self.assertEqual(snapshot.total_score, 10)
        self.assertEqual(snapshot.level, screening.SCREENING_LEVEL_MEDIUM)
        self.assertEqual(dict(snapshot.block_scores), {"A": 0, "Б": 7, "Г": 3})
        self.assertEqual([a.weighted_score for a in snapshot.contributing_answers], [0, 7, 3])
        self.assertEqual([r.code for r in snapshot.recommendations], ["medium"])

    def test_publishing_v2_preserves_v1_for_existing_session(self):
        session_id = self.start()
        rules = self.rules.get("example", "v1")
        rules["weights_version"] = "v2"
        rules["blocks"][1]["questions"][0]["weights"]["yes"] = 6
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "v2.json"
            path.write_text(json.dumps(rules), encoding="utf-8")
            self.rules.publish(path)
        for code, value in (("A1", "four"), ("Б1", True), ("В1", False), ("Г1", False)):
            self.save(session_id, code, value)
        self.assert_succeeded(self.workflow.execute(complete_command(session_id, 5)))
        result = self.result(session_id).calculation
        self.assertEqual(self.rules.get("example")["weights_version"], "v2")
        self.assertEqual((result.weights_version, result.total_score, result.level), ("v1", 11, "high"))

    def test_incomplete_session_remains_a_draft_without_completion_event(self):
        session_id = self.start()
        self.save(session_id, "A1", "four")
        message = complete_command(session_id, 2)
        rejected = self.workflow.execute(message)
        self.assertEqual(rejected.state, metadata.OPERATION_STATE_REJECTED)
        self.assertEqual(rejected.error.code, "ANSWERS_INCOMPLETE")
        self.assertEqual(self.workflow.execute(message), rejected)
        session = self.session(session_id)
        self.assertEqual((session.status, session.version), ("in_progress", 2))
        self.assertEqual(session.answers["A1"].value, "four")
        self.assertIsNone(self.result(session_id))
        self.assertEqual(self.events(message), [])

    def test_tampered_wire_fields_are_ignored_and_cannot_change_score_or_replay(self):
        session_id = self.ready_session()
        message = complete_command(session_id, 5)
        forged = ScreeningCommand.FromString(message.SerializeToString())
        forged.complete.MergeFromString(b"\x18\x7b\x22\x04high")
        result = self.workflow.execute(forged)
        self.assert_succeeded(result)
        self.assertEqual(self.workflow.execute(message), result)
        calculation = self.result(session_id).calculation
        self.assertEqual((calculation.total_score, calculation.level), (10, "medium"))
        self.assertEqual(len(self.events(message)), 2)

    def test_stale_revision_and_wrong_subject_cannot_complete(self):
        session_id = self.ready_session()
        for message, code in [
            (complete_command(session_id, 4), "SESSION_VERSION_CONFLICT"),
            (complete_command(session_id, 5, subject="another"), "ACCESS_DENIED"),
        ]:
            with self.subTest(code=code):
                operation = self.workflow.execute(message)
                self.assertEqual(operation.state, metadata.OPERATION_STATE_REJECTED)
                self.assertEqual(operation.error.code, code)
                self.assertEqual(self.events(message), [])
        self.assertEqual(self.session(session_id).version, 5)
        self.assertIsNone(self.result(session_id))

    def test_reusing_command_id_with_changed_payload_cannot_overwrite_outcome(self):
        session_id = self.ready_session()
        message = complete_command(session_id, 5)
        original = self.workflow.execute(message)
        changed = ScreeningCommand.FromString(message.SerializeToString())
        changed.complete.expected_session_version = 6
        conflict = self.workflow.execute(changed)
        self.assertEqual(conflict.state, metadata.OPERATION_STATE_REJECTED)
        self.assertEqual(conflict.error.code, "COMMAND_ID_CONFLICT")
        self.assertEqual(self.workflow.execute(message), original)
        self.assertEqual(len(self.events(message)), 2)

    def test_conflicting_command_with_new_operation_id_records_rejection(self):
        session_id = self.ready_session()
        message = complete_command(session_id, 5)
        original = self.workflow.execute(message)
        changed = ScreeningCommand.FromString(message.SerializeToString())
        changed.metadata.operation_id = str(uuid4())
        changed.complete.expected_session_version = 6
        conflict = self.workflow.execute(changed)
        self.assertEqual(conflict.error.code, "COMMAND_ID_CONFLICT")
        with self.storage.transaction() as txn:
            saved = txn.get_operation(changed.metadata.operation_id)
            self.assertIsNotNone(saved)
            self.assertEqual(metadata.Operation.FromString(saved.response), conflict)
        self.assertEqual(self.workflow.execute(changed), conflict)
        self.assertEqual(self.workflow.execute(message), original)
        self.assertEqual(len(self.events(message)), 2)
        self.assertEqual(self.events(changed), [])

    def test_events_correlate_to_operation_when_command_correlation_is_blank(self):
        session_id = self.ready_session()
        message = complete_command(session_id, 5)
        message.metadata.correlation_id = " "
        self.assert_succeeded(self.workflow.execute(message))
        self.assertEqual([event.metadata.correlation_id for event in self.events(message)],
                         [message.metadata.operation_id] * 2)

    def test_outbox_failure_rolls_back_result_session_and_operation_before_retry(self):
        session_id = self.ready_session()
        message = complete_command(session_id, 5)
        self.storage.fail_next_result_event = True
        with self.assertRaisesRegex(OSError, "outbox unavailable"):
            self.workflow.execute(message)
        self.assertEqual((self.session(session_id).status, self.session(session_id).version),
                         ("in_progress", 5))
        self.assertIsNone(self.result(session_id))
        self.assertEqual(self.events(message), [])
        with self.storage.transaction() as txn:
            self.assertIsNone(txn.get_operation(message.metadata.operation_id))
        self.assert_succeeded(self.workflow.execute(message))
        self.assertEqual(len(self.events(message)), 2)

    def test_concurrent_completions_create_one_result_and_one_completion_event(self):
        session_id = self.ready_session()
        messages = [complete_command(session_id, 5), complete_command(session_id, 5)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            operations = list(pool.map(self.workflow.execute, messages))
        self.assertCountEqual(
            (result.state for result in operations),
            (metadata.OPERATION_STATE_SUCCEEDED, metadata.OPERATION_STATE_REJECTED),
        )
        self.assertEqual(self.result(session_id).version, 1)
        for message, operation in zip(messages, operations, strict=True):
            expected = ["session_changed", "result_changed"] if operation.state == metadata.OPERATION_STATE_SUCCEEDED else []
            self.assertEqual([event.WhichOneof("payload") for event in self.events(message)], expected)

    def test_immediate_flag_then_continuation_and_completion_preserve_one_result_identity(self):
        session_id = self.start()
        flag = self.save(session_id, "В1", True)
        urgent = self.result(session_id)
        self.assertEqual((urgent.version, urgent.calculation.level), (1, "red_flag"))
        self.assertTrue(self.session(session_id).interrupted_by_red_flag)
        interrupted, result_event = self.events(flag)
        self.assert_session_event(interrupted, flag, session_id, 2, screening.SESSION_STATUS_IN_PROGRESS,
                                  interrupted=True)
        snapshot = self.assert_event(result_event, flag, urgent)
        self.assertFalse(snapshot.HasField("total_score"))
        self.assertEqual(list(snapshot.red_flag_codes), ["example_flag"])
        self.assertEqual(snapshot.level, screening.SCREENING_LEVEL_RED_FLAG)

        resume = command()
        resume.continue_after_red_flag.session_id = session_id
        resume.continue_after_red_flag.expected_session_version = 2
        self.assert_succeeded(self.workflow.execute(resume))
        (resumed,) = self.events(resume)
        self.assert_session_event(resumed, resume, session_id, 3, screening.SESSION_STATUS_IN_PROGRESS)
        for code, value in (("A1", "nine"), ("Б1", True), ("Г1", True), ("В1", False)):
            self.save(session_id, code, value)
        message = complete_command(session_id, 7)
        self.assert_succeeded(self.workflow.execute(message))
        final = self.result(session_id)
        self.assertEqual((final.result_id, final.version), (urgent.result_id, 2))
        self.assertEqual((final.calculation.level, final.calculation.total_score), ("red_flag", 19))
        self.assertFalse(final.calculation.red_flags[0].matched_current_answer)
        completed, result_event = self.events(message)
        self.assert_session_event(completed, message, session_id, 8, screening.SESSION_STATUS_COMPLETED)
        self.assert_event(result_event, message, final)
        with self.storage.transaction() as txn:
            self.assertEqual(txn.get_result(urgent.result_id, 1), urgent)

    def test_urgent_session_can_finish_with_missing_answers(self):
        session_id = self.start()
        self.save(session_id, "В1", True)
        self.assert_succeeded(self.workflow.execute(complete_command(session_id, 2)))
        self.assertEqual(self.session(session_id).status, "completed")
        calculation = self.result(session_id).calculation
        self.assertFalse(calculation.scoring_complete)
        self.assertEqual(calculation.level, "red_flag")
        self.assertIsNone(calculation.total_score)


class MockTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_runtime_checks_database_before_dispatching_screening_command(self):
        import runtime

        body = start_command()
        callback = AsyncMock(return_value="succeeded")
        database_check = Mock()
        callbacks = []
        stop_callbacks = []
        broker = Mock()
        broker.subscriber.return_value = callbacks.append
        server = Mock()
        server.stop = AsyncMock()
        broker.stop = AsyncMock()

        async def deliver():
            database_check.assert_called_once_with("screening")
            (receive,) = callbacks
            await receive(body.SerializeToString())

        async def stop_soon():
            stop_callbacks[0]()

        broker.start = AsyncMock(side_effect=deliver)
        server.start = AsyncMock(side_effect=stop_soon)
        with (
            patch.object(runtime, "check_database", database_check),
            patch.object(runtime, "KafkaBroker", return_value=broker),
            patch.object(runtime.grpc.aio, "server", return_value=server),
            patch.object(asyncio.get_running_loop(), "add_signal_handler",
                         side_effect=lambda sig, stop: stop_callbacks.append(stop)),
            patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "mock:19092", "PGHOST": "mock-postgres"}),
        ):
            await runtime.serve("screening", Mock(), Mock(), ScreeningCommand, command_handler=callback)
        callback.assert_awaited_once_with(body)

    async def test_command_and_grpc_paths_share_the_same_mock_storage(self):
        from services.screening.main import build_mock_screening

        handler = build_mock_screening()
        server = grpc.aio.server()
        rpc.add_ScreeningQueryServiceServicer_to_server(handler, server)
        port = server.add_insecure_port("127.0.0.1:0")
        await server.start()
        self.addAsyncCleanup(server.stop, 0)

        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            client = rpc.ScreeningQueryServiceStub(channel)
            survey = await client.GetSurvey(queries.GetSurveyRequest(), timeout=5)
            self.assertEqual((survey.reference.survey_id, survey.reference.weights_version),
                             ("example", "v1"))

            message = start_command()
            self.assertEqual(await handler.handle_command(message), "succeeded")
            operation_request = metadata.GetOperationRequest(operation_id=message.metadata.operation_id)
            operation_request.context.request_id = "op"
            operation_request.context.actor.CopyFrom(message.metadata.actor)
            with self.assertRaises(grpc.aio.AioRpcError) as unauthenticated:
                await client.GetOperation(operation_request, timeout=5)
            self.assertEqual(unauthenticated.exception.code(), grpc.StatusCode.UNAUTHENTICATED)
            # Transport and IAM are exercised separately; isolate storage/ownership here.
            verified = patch('services.screening.main.principal_for', AsyncMock(return_value=message.metadata.actor))
            verified.start()
            self.addCleanup(verified.stop)
            operation = await client.GetOperation(operation_request, timeout=5)
            session_id = operation.resources[0].resource_id

            answer = command()
            answer.save_answer.session_id = session_id
            answer.save_answer.expected_session_version = 1
            answer.save_answer.answer.question_code = "В1"
            answer.save_answer.answer.boolean_value = True
            self.assertEqual(await handler.handle_command(answer), "succeeded")
            finish = complete_command(session_id, 2)
            self.assertEqual(await handler.handle_command(finish), "succeeded")

            query = queries.GetSessionResultRequest(session_id=session_id)
            query.context.CopyFrom(operation_request.context)
            result = await client.GetSessionResult(query, timeout=5)
            self.assertEqual(result.reference.version, 2)
            self.assertEqual(list(result.red_flag_codes), ["example_flag"])
            self.assertFalse(result.HasField("total_score"))
            exact = queries.GetResultRequest(context=query.context, result=result.reference)
            self.assertEqual(await client.GetResult(exact, timeout=5), result)
            exact.result.version = 99
            with self.assertRaises(grpc.aio.AioRpcError) as missing:
                await client.GetResult(exact, timeout=5)
            self.assertEqual(missing.exception.code(), grpc.StatusCode.NOT_FOUND)

            query.context.actor.subject_id = "another"
            with self.assertRaises(grpc.aio.AioRpcError) as denied:
                await client.GetSessionResult(query, timeout=5)
            self.assertEqual(denied.exception.code(), grpc.StatusCode.PERMISSION_DENIED)
