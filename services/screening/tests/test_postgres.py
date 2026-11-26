import asyncio
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
from pathlib import Path
from threading import get_ident
from unittest.mock import Mock, patch
from uuid import UUID, uuid7

from contracts.common.v1 import metadata_pb2 as metadata
from contracts.common.v1 import screening_pb2 as screening
from contracts.events.v1.screening_pb2 import ScreeningEvent
from pg8000.dbapi import DatabaseError, connect

from services.screening.postgres_store import PostgresScreeningStore
from services.screening.rules import RuleConfigError, load_rules
from services.screening.workflow import InvalidCommand, ScreeningWorkflow

from test_workflow import EXAMPLE, command, complete_command, start_command


POSTGRES_PORT = os.environ.get("SCREENING_TEST_POSTGRES_PORT")


class PostgresTransactionTests(unittest.TestCase):
    def test_commit_and_rollback_close_the_connection(self):
        connection = Mock()
        storage = PostgresScreeningStore(lambda: connection)
        with storage.transaction():
            connection.commit.assert_not_called()
        connection.commit.assert_called_once_with()
        connection.rollback.assert_not_called()
        connection.cursor.return_value.close.assert_called_once_with()
        connection.close.assert_called_once_with()

        connection.reset_mock()
        with self.assertRaisesRegex(OSError, "outbox unavailable"):
            with storage.transaction():
                raise OSError("outbox unavailable")
        connection.commit.assert_not_called()
        connection.rollback.assert_called_once_with()
        connection.cursor.return_value.close.assert_called_once_with()
        connection.close.assert_called_once_with()


class FailingPostgresStore(PostgresScreeningStore):
    fail_result_event = False

    @contextmanager
    def transaction(self):
        with super().transaction() as transaction:
            if not self.fail_result_event:
                yield transaction
                return

            append = transaction.append_event

            def duplicate_result_event(event):
                append(event)
                if ScreeningEvent.FromString(event).HasField("result_changed"):
                    append(event)

            with patch.object(transaction, "append_event", side_effect=duplicate_result_event):
                yield transaction


@unittest.skipUnless(POSTGRES_PORT, "Set SCREENING_TEST_POSTGRES_PORT to use an isolated test database")
class PostgresWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.owner = str(uuid7())
        self.survey = f"test-{uuid7()}"
        self.storage = FailingPostgresStore(self.connect)
        self.workflow = ScreeningWorkflow(self.storage)
        self.rules = load_rules(EXAMPLE)
        self.rules["id"] = self.survey
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "rules.json"
        self.publish("d1", "Test disclaimer one.")

    @staticmethod
    def connect():
        return connect(
            host="127.0.0.1", port=int(POSTGRES_PORT), database="mis_screening",
            user="mis_screening_app", password=os.environ["SCREENING_TEST_POSTGRES_PASSWORD"],
            timeout=5,
        )

    def publish(self, disclaimer_version, disclaimer):
        self.path.write_text(json.dumps(self.rules, ensure_ascii=False), encoding="utf-8")
        self.storage.publish(self.path, disclaimer_version=disclaimer_version, disclaimer=disclaimer)

    def identify(self, message):
        message.metadata.command_id = str(uuid7())
        message.metadata.operation_id = str(uuid7())
        message.metadata.correlation_id = str(uuid7())
        message.metadata.actor.subject_id = self.owner
        message.metadata.actor.session_id = str(uuid7())
        return message

    def execute_success(self, message):
        operation = self.workflow.execute(message)
        self.assertEqual(operation.state, metadata.OPERATION_STATE_SUCCEEDED, operation.error)
        return operation

    def start(self):
        message = self.identify(start_command())
        message.start.survey.survey_id = self.survey
        message.start.disclaimer_version = "d1"
        operation = self.execute_success(message)
        session_id = operation.resources[0].resource_id
        self.assertEqual(UUID(session_id).version, 7)
        return session_id

    def save(self, session_id, revision, code, value):
        message = self.identify(command())
        answer = message.save_answer
        answer.session_id = session_id
        answer.expected_session_version = revision
        answer.answer.question_code = code
        if isinstance(value, bool):
            answer.answer.boolean_value = value
        else:
            answer.answer.choice_value = value
        self.execute_success(message)

    def ready(self, session_id):
        for version, (code, value) in enumerate(
            (("A1", "four"), ("Б1", True), ("В1", False), ("Г1", False)), start=1,
        ):
            self.save(session_id, version, code, value)

    def complete(self, session_id, revision=5):
        return self.identify(complete_command(session_id, revision))

    def events(self, operation_id):
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                "SELECT event_id, entity_id, entity_version, payload FROM outbox_events WHERE operation_id=%s",
                (UUID(operation_id),),
            )
            return [(str(event_id), str(entity_id), version, ScreeningEvent.FromString(payload))
                    for event_id, entity_id, version, payload in cursor.fetchall()]

    def test_pinned_rules_completion_snapshot_and_replay_after_new_adapter_instance(self):
        session_id = self.start()
        self.publish("d2", "Test disclaimer two.")
        self.rules["weights_version"] = "v2"
        self.rules["blocks"][1]["questions"][0]["weights"]["yes"] = 6
        self.publish("d2", "Test disclaimer two.")
        self.ready(session_id)
        message = self.complete(session_id)
        operation = self.execute_success(message)
        restarted = ScreeningWorkflow(PostgresScreeningStore(self.connect))
        self.assertEqual(restarted.execute(message), operation)
        result_id = operation.resources[1].resource_id
        self.assertEqual(UUID(result_id).version, 7)
        with self.storage.transaction() as transaction:
            self.assertEqual(transaction.get_questionnaire(self.survey).rules["weights_version"], "v2")
            self.assertEqual(transaction.get_questionnaire(self.survey, "v1").disclaimer_version, "d2")
            session = transaction.get_session(session_id)
            result = transaction.get_result(result_id, 1)
            self.assertIsNone(transaction.get_result(result_id, 2))
        self.assertEqual((session.status, session.version, session.final_result_id), ("completed", 6, result_id))
        self.assertIsNotNone(session.completed_at)
        self.assertEqual((session.weights_version, session.disclaimer_version), ("v1", "d1"))
        self.assertEqual(result.disclaimer, "Test disclaimer one.")
        self.assertEqual((result.calculation.total_score, result.calculation.matched_range), (11, (11, None)))
        self.assertEqual(result.calculation.reason, "score")
        events = self.events(message.metadata.operation_id)
        self.assertCountEqual([row[3].WhichOneof("payload") for row in events],
                              ["session_changed", "result_changed"])
        by_payload = {row[3].WhichOneof("payload"): row for row in events}
        session_event_id, entity_id, entity_version, event = by_payload["session_changed"]
        self.assertEqual(UUID(session_event_id).version, 7)
        self.assertEqual((entity_id, entity_version), (session_id, 6))
        self.assertEqual(event.metadata.entity_type, "screening_session")
        self.assertEqual((event.metadata.event_id, event.metadata.entity_id, event.metadata.entity_version),
                         (session_event_id, entity_id, entity_version))
        self.assertEqual(event.session_changed.session_id, session_id)
        self.assertEqual(event.session_changed.survey.survey_id, self.survey)
        self.assertEqual(event.session_changed.survey.weights_version, "v1")
        self.assertEqual(event.session_changed.status, screening.SESSION_STATUS_COMPLETED)
        self.assertFalse(event.session_changed.interrupted_by_red_flag)

        event_id, entity_id, entity_version, event = by_payload["result_changed"]
        self.assertEqual(UUID(event_id).version, 7)
        self.assertEqual((entity_id, entity_version), (result_id, 1))
        self.assertEqual((event.metadata.event_id, event.metadata.entity_id), (event_id, entity_id))
        self.assertEqual(event.result_changed.result.total_score, 11)

    def test_outbox_constraint_failure_undoes_every_write_and_can_be_retried(self):
        session_id = self.start()
        self.ready(session_id)
        message = self.complete(session_id)
        self.storage.fail_result_event = True
        with self.assertRaises(DatabaseError):
            self.workflow.execute(message)
        self.storage.fail_result_event = False
        with self.storage.transaction() as transaction:
            session = transaction.get_session(session_id)
            self.assertEqual((session.status, session.version), ("in_progress", 5))
            self.assertIsNone(transaction.get_latest_result(session_id))
            self.assertIsNone(transaction.get_operation(message.metadata.operation_id))
            self.assertFalse(transaction.has_command(message.metadata.command_id))
        self.assertEqual(self.events(message.metadata.operation_id), [])
        self.execute_success(message)
        self.assertCountEqual(
            [row[3].WhichOneof("payload") for row in self.events(message.metadata.operation_id)],
            ["session_changed", "result_changed"],
        )

    def test_parallel_completion_and_command_conflict_have_persistent_outcomes(self):
        session_id = self.start()
        self.ready(session_id)
        first, second = self.complete(session_id), self.complete(session_id)
        with ThreadPoolExecutor(max_workers=3) as executor:
            a, duplicate, b = executor.map(self.workflow.execute, [first, first, second])
        self.assertEqual(a, duplicate)
        self.assertCountEqual(
            [a.state, b.state], [metadata.OPERATION_STATE_SUCCEEDED, metadata.OPERATION_STATE_REJECTED],
        )
        for message, operation in ((first, a), (second, b)):
            expected = []
            if operation.state == metadata.OPERATION_STATE_SUCCEEDED:
                expected = ["session_changed", "result_changed"]
            self.assertCountEqual(
                [row[3].WhichOneof("payload") for row in self.events(message.metadata.operation_id)],
                expected,
            )

        conflict = self.complete(session_id, 6)
        conflict.metadata.command_id = first.metadata.command_id
        rejected = self.workflow.execute(conflict)
        self.assertEqual(rejected.error.code, "COMMAND_ID_CONFLICT")
        self.assertEqual(rejected, self.workflow.execute(conflict))
        with self.storage.transaction() as transaction:
            self.assertIsNotNone(transaction.get_operation(conflict.metadata.operation_id))
            self.assertEqual(transaction.get_latest_result(session_id).version, 1)

    def test_inbox_preserves_a_session_checkpoint_and_outcomes_for_both_operation_ids(self):
        session_id = self.start()
        self.ready(session_id)
        command = self.complete(session_id)
        original = self.execute_success(command)
        conflict = self.complete(session_id, 6)
        conflict.metadata.command_id = command.metadata.command_id
        rejected = self.workflow.execute(conflict)
        self.assertEqual(rejected.error.code, "COMMAND_ID_CONFLICT")

        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                "SELECT operation_id, outcome FROM inbox_messages WHERE message_id=%s",
                (UUID(command.metadata.command_id),),
            )
            operation_id, outcome = cursor.fetchone()
        self.assertEqual(str(operation_id), original.operation_id)
        checkpoint = outcome["screening"]["session"]
        self.assertEqual((checkpoint["id"], checkpoint["version"]), (session_id, 6))
        self.assertIsNotNone(checkpoint["completed_at"])
        self.assertFalse(checkpoint["interrupted_by_red_flag"])

        restarted = ScreeningWorkflow(PostgresScreeningStore(self.connect))
        self.assertEqual(restarted.execute(command), original)
        self.assertEqual(restarted.execute(conflict), rejected)

    def test_legacy_inbox_operation_id_stays_reserved_without_a_saved_response(self):
        original = self.identify(start_command())
        original.start.survey.survey_id = self.survey
        original.start.disclaimer_version = "d1"
        legacy = {"screening": {"operations": None}, "status": "legacy fixture"}
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO inbox_messages(message_id, operation_id, outcome) VALUES (%s, %s, %s::jsonb)",
                (UUID(original.metadata.command_id), UUID(original.metadata.operation_id), json.dumps(legacy)),
            )
            connection.commit()

        replay = self.workflow.execute(original)
        self.assertEqual(replay.error.code, "OPERATION_OUTCOME_UNAVAILABLE")
        changed = start_command()
        changed.CopyFrom(original)
        changed.metadata.command_id = str(uuid7())
        self.assertEqual(self.workflow.execute(changed).error.code, "OPERATION_ID_CONFLICT")

        original.metadata.operation_id = str(uuid7())
        self.assertEqual(self.workflow.execute(original).error.code, "COMMAND_ID_CONFLICT")
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute("SELECT outcome FROM inbox_messages WHERE message_id=%s",
                           (UUID(original.metadata.command_id),))
            self.assertEqual(cursor.fetchone()[0]["legacy_outcome"], legacy)
            cursor.execute("SELECT count(*) FROM screening_sessions WHERE owner_id=%s", (UUID(self.owner),))
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_urgent_revision_is_appended_before_completion_and_remains_addressable(self):
        session_id = self.start()
        self.save(session_id, 1, "В1", True)
        with self.storage.transaction() as transaction:
            first = transaction.get_latest_result(session_id)
            self.assertTrue(transaction.get_session(session_id).interrupted_by_red_flag)
        resume = self.identify(command())
        resume.continue_after_red_flag.session_id = session_id
        resume.continue_after_red_flag.expected_session_version = 2
        self.execute_success(resume)
        self.save(session_id, 3, "В1", False)
        self.execute_success(self.complete(session_id, 4))
        with self.storage.transaction() as transaction:
            final = transaction.get_latest_result(session_id)
            self.assertEqual(transaction.get_result(first.result_id, 1), first)
            self.assertFalse(transaction.get_session(session_id).interrupted_by_red_flag)
        self.assertEqual((final.result_id, final.version), (first.result_id, 2))
        self.assertEqual(final.calculation.level, "red_flag")
        self.assertFalse(final.calculation.red_flags[0].matched_current_answer)

    def test_publication_rejects_replacing_rules_or_disclaimer_under_the_same_version(self):
        with self.assertRaises(RuleConfigError):
            self.publish("d1", "Changed wording.")
        self.rules["blocks"][1]["questions"][0]["weights"]["yes"] = 6
        with self.assertRaises(RuleConfigError):
            self.publish("d2", "Test disclaimer two.")
        with self.storage.transaction() as transaction:
            current = transaction.get_questionnaire(self.survey, "v1")
            self.assertEqual(current.disclaimer_version, "d1")
            self.assertEqual(current.rules["blocks"][1]["questions"][0]["weights"]["yes"], 7)

    def test_new_session_requires_the_current_disclaimer_for_the_requested_rules_version(self):
        self.publish("d2", "Test disclaimer two.")
        message = self.identify(start_command())
        message.start.survey.survey_id = self.survey
        message.start.disclaimer_version = "d1"
        rejected = self.workflow.execute(message)
        self.assertEqual(rejected.error.code, "DISCLAIMER_REQUIRED")

        self.identify(message)
        message.start.disclaimer_version = "d2"
        success = self.execute_success(message)
        with self.storage.transaction() as transaction:
            session = transaction.get_session(success.resources[0].resource_id)
        self.assertEqual((session.weights_version, session.disclaimer_version), ("v1", "d2"))

    def test_invalid_database_identifiers_do_not_reach_sql(self):
        message = self.identify(start_command())
        message.metadata.correlation_id = "not-a-uuid"
        with self.assertRaises(InvalidCommand):
            self.workflow.execute(message)

    def test_invalid_questionnaire_key_is_rejected_as_an_operation(self):
        message = self.identify(start_command())
        message.start.survey.survey_id = self.survey + "\x00"
        message.start.disclaimer_version = "d1"
        result = self.workflow.execute(message)
        self.assertEqual(result.error.code, "RULES_NOT_FOUND")
        self.assertEqual(self.workflow.execute(message), result)

    def test_legacy_flag_without_a_full_snapshot_cannot_be_replaced(self):
        session_id = self.start()
        with closing(self.connect()) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                "INSERT INTO screening_results(session_id, revisions) VALUES (%s, %s::jsonb)",
                (UUID(session_id), '[{"level":"RED_FLAG","score":1}]'),
            )
            connection.commit()
        message = self.complete(session_id, 1)
        result = self.workflow.execute(message)
        self.assertEqual(result.error.code, "RESULT_SNAPSHOT_UNAVAILABLE")
        self.assertEqual(self.workflow.execute(message), result)
        with self.storage.transaction() as transaction:
            self.assertEqual(transaction.get_session(session_id).status, "in_progress")
        self.assertEqual(self.events(message.metadata.operation_id), [])

    def test_local_transport_can_persist_a_command_with_the_postgres_backend(self):
        from services.screening import main
        from contracts.grpc.v1.screening_pb2 import GetSurveyRequest

        connection_threads = []

        def record_thread():
            connection_threads.append(get_ident())
            return self.connect()

        with (
            patch.dict(os.environ, {"SCREENING_STORAGE": "postgres"}),
            patch.object(main, "connect_screening", record_thread),
        ):
            handler = main.build_mock_screening()
        message = self.identify(start_command())
        connection_threads.clear()

        async def request():
            survey = await handler.GetSurvey(GetSurveyRequest(), Mock())
            self.assertEqual(survey.reference.survey_id, "example")
            self.assertEqual(await handler.handle_command(message), "succeeded")
            self.assertEqual(len(connection_threads), 2)
            self.assertNotIn(get_ident(), connection_threads)

        asyncio.run(request())
        with self.storage.transaction() as transaction:
            operation = transaction.get_operation(message.metadata.operation_id)
            response = metadata.Operation.FromString(operation.response)
            session = transaction.get_session(response.resources[0].resource_id)
        self.assertEqual((session.survey_id, session.weights_version), ("example", "v1"))
