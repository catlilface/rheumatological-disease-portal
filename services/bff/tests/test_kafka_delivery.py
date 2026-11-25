import json
import os
import time
from collections import Counter
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from confluent_kafka import KafkaError
from confluent_kafka.admin import AdminClient, NewTopic
from pg8000.dbapi import connect

from app.messaging.kafka import KafkaInboxOutbox, Message, Metadata, RejectMessage


@pytest.fixture
def stack():
    brokers = os.getenv("TEST_KAFKA_BROKERS")
    if not brokers:
        pytest.skip("TEST_KAFKA_BROKERS is required")
    database = dict(
        host=os.environ["TEST_PGHOST"],
        port=int(os.environ["TEST_PGPORT"]),
        database="postgres",
        user="postgres",
        password=os.environ["TEST_PGPASSWORD"],
        timeout=5,
    )

    name = f"delivery_{uuid4().hex}"
    app_role, migrator_role = f"{name}_app", f"{name}_migrator"
    app_password, migrator_password = uuid4().hex, uuid4().hex
    with closing(connect(**database)) as admin_db:
        admin_db.autocommit = True
        cursor = admin_db.cursor()
        cursor.execute(f"CREATE ROLE {migrator_role} LOGIN PASSWORD '{migrator_password}'")
        cursor.execute(f"CREATE ROLE {app_role} LOGIN PASSWORD '{app_password}'")
        cursor.execute(f"CREATE DATABASE {name} OWNER {migrator_role}")
        cursor.execute(f"REVOKE ALL ON DATABASE {name} FROM PUBLIC")
        cursor.execute(f"GRANT CONNECT ON DATABASE {name} TO {app_role}")
    database["database"] = name

    migrator = dict(database, user=migrator_role, password=migrator_password)
    migrations = Path(__file__).resolve().parents[1] / "migrations"
    with closing(connect(**migrator)) as db:
        cursor = db.cursor()
        cursor.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {app_role}")
        cursor.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_role}"
        )
        for migration in sorted(migrations.glob("*.sql")):
            cursor.execute(migration.read_text().split("-- migrate:down")[0])
        cursor.execute("CREATE TABLE demo_counter (id uuid PRIMARY KEY, value integer NOT NULL)")
        db.commit()
    database = dict(database, user=app_role, password=app_password)
    suffix = uuid4().hex
    commands, events, dead = (f"delivery-{suffix}-{kind}" for kind in ("command", "event", "dead"))
    admin = AdminClient({"bootstrap.servers": brokers})
    for future in admin.create_topics([NewTopic(topic, 2, 1) for topic in (commands, events, dead)]).values():
        future.result(15)

    def worker(**settings):
        return KafkaInboxOutbox.from_config(database, brokers, dead_letter_topic=dead, retry_delay=0, **settings)

    def consumer(group, *topics):
        return KafkaInboxOutbox.consumer(brokers, group, list(topics))

    def query(sql):
        with closing(connect(**database)) as db:
            cursor = db.cursor()
            cursor.execute(sql)
            return [tuple(row) for row in cursor.fetchall()]

    return worker, consumer, query, commands, events, dead


def read_one(worker, consumer, handler):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if worker.consume_one(consumer, handler):
            return
    pytest.fail("Kafka record not delivered")


def drain(worker):
    while worker.publish_one():
        pass


def example_handler(events):
    def handle(cursor, command):
        meta = command.metadata
        cursor.execute(
            "INSERT INTO demo_counter VALUES (%s, 1) "
            "ON CONFLICT (id) DO UPDATE SET value = demo_counter.value + 1 RETURNING value",
            (meta.entity_id,),
        )
        value = cursor.fetchone()[0]
        event = replace(meta, id=uuid4(), kind="event")
        KafkaInboxOutbox.enqueue(cursor, Message(events, event, str(value).encode()))
        return {"value": value}

    return handle


def test_recovers_after_commit_and_redelivery(stack):
    worker, consumer, query, commands, events, _ = stack
    transport = worker()
    assert query(
        "SELECT has_sequence_privilege(pg_get_serial_sequence('kafka_outbox', 'position'), 'USAGE')"
    ) == [(False,)]
    metadata = Metadata(uuid4(), uuid4(), "counter", uuid4(), 1, "command")
    command = Message(commands, metadata, b"increment")
    transport.submit(command)
    transport.submit(command)
    with pytest.raises(RejectMessage):
        transport.submit(replace(command, payload=b"different"))
    assert transport.publish_one()

    class OffsetFailure:
        def __init__(self, inner):
            self.inner = inner

        def poll(self, timeout):
            return self.inner.poll(timeout)

        def commit(self, **kwargs):
            raise RuntimeError("offset commit failed")

        def close(self):
            self.inner.close()

    group = uuid4().hex
    with pytest.raises(RuntimeError, match="offset commit failed"):
        read_one(transport, OffsetFailure(consumer(group, commands)), example_handler(events))
    assert query("SELECT value FROM demo_counter") == [(1,)]
    assert query("SELECT count(*) FROM kafka_outbox WHERE published_at IS NULL") == [(1,)]

    recovered = worker()
    with closing(consumer(group, commands)) as incoming:
        read_one(recovered, incoming, lambda *_: pytest.fail("command ran twice"))
    assert recovered.operation(metadata.operation_id) == {"status": "succeeded", "result": {"value": 1}}
    drain(recovered)
    received = []
    with closing(consumer(uuid4().hex, events)) as incoming:
        read_one(recovered, incoming, lambda _, event: received.append(event.payload) or {})
    assert received == [b"1"]
    assert query("SELECT value FROM demo_counter") == [(1,)]


def test_conflicts_versions_and_poison_message(stack):
    worker, consumer, query, commands, events, dead = stack
    transport = worker(max_attempts=2)
    initial = Metadata(uuid4(), uuid4(), "counter", uuid4(), 1, "command")
    replay = replace(initial, id=uuid4())
    conflict = replace(initial, id=uuid4())
    gap = replace(initial, id=uuid4(), operation_id=uuid4(), version=3)
    poison = replace(initial, id=uuid4(), operation_id=uuid4(), version=2)
    transport.producer.produce(
        commands,
        key=initial.key,
        value=b"invalid metadata",
        headers=[("mis-delivery", b"\xff")],
    )
    assert transport.producer.flush(10) == 0
    for metadata, payload in (
        (initial, b"ok"), (replay, b"ok"), (conflict, b"other"), (gap, b"ok"), (poison, b"poison"),
    ):
        transport.submit(Message(commands, metadata, payload))
    drain(transport)
    transport.producer.produce(commands, key=initial.key, value=b"missing metadata")
    assert transport.producer.flush(10) == 0
    calls = []
    apply = example_handler(events)

    def handle(cursor, message):
        calls.append(message.payload)
        result = apply(cursor, message)
        if message.payload == b"poison":
            raise RuntimeError("transient fault")
        return result

    with closing(consumer(uuid4().hex, commands)) as incoming:
        for _ in range(7):
            read_one(transport, incoming, handle)
    assert calls == [b"ok", b"poison", b"poison"]
    assert query("SELECT value FROM demo_counter") == [(1,)]
    assert transport.operation(gap.operation_id) == {"error": "version_gap"}
    assert transport.operation(poison.operation_id) == {"error": "handler_failed"}
    assert transport.operation(conflict.operation_id)["status"] == "succeeded"
    assert query(f"SELECT count(*) FROM kafka_outbox WHERE topic = '{dead}' AND published_at IS NULL") == [(5,)]
    drain(transport)
    assert query("SELECT count(*) FROM kafka_outbox WHERE published_at IS NULL") == [(0,)]
    codes = Counter()
    deadline = time.monotonic() + 15
    with closing(consumer(uuid4().hex, dead)) as incoming:
        while codes.total() < 5 and time.monotonic() < deadline:
            record = incoming.poll(1)
            if record is not None:
                assert record.error() is None
                codes[json.loads(record.value())["code"]] += 1
    assert codes == {"idempotency_conflict": 1, "version_gap": 1, "handler_failed": 1, "invalid_message": 2}


def test_publish_failure_leaves_event_for_restart(stack):
    worker, consumer, query, _, events, _ = stack
    transport = worker()
    metadata = Metadata(uuid4(), uuid4(), "projection", uuid4(), 2, "event")
    transport.submit(Message(events, metadata, b"new"))
    transport.submit(Message(events, replace(metadata, id=uuid4(), version=1), b"old"))

    class UnavailableProducer:
        def produce(self, *args, **kwargs):
            raise BufferError("Kafka producer unavailable")

    transport.producer = UnavailableProducer()
    with pytest.raises(BufferError):
        transport.publish_one()
    assert query("SELECT count(*) FROM kafka_outbox WHERE published_at IS NULL") == [(2,)]

    recovered = worker()
    drain(recovered)
    applied = []
    with closing(consumer(uuid4().hex, events)) as incoming:
        for _ in range(2):
            read_one(recovered, incoming, lambda _, message: applied.append(message.payload) or {})
    assert applied == [b"new"]
    assert query("SELECT version FROM kafka_versions") == [(2,)]


def test_oversized_message_quarantines_only_its_key(stack):
    worker, consumer, query, commands, _, _ = stack
    transport = worker()
    first = Metadata(uuid4(), uuid4(), "counter", uuid4(), 1, "command")
    following = replace(first, id=uuid4(), operation_id=uuid4(), version=2)
    unrelated = replace(first, id=uuid4(), operation_id=uuid4(), entity_id=uuid4())
    transport.submit(Message(commands, first, b"x" * 2_000_000))
    transport.submit(Message(commands, following, b"waiting"))
    transport.submit(Message(commands, unrelated, b"ready"))

    assert transport.publish_one()
    recovered = worker()
    assert recovered.publish_one()
    assert not recovered.publish_one()
    assert query(
        "SELECT id, published_at IS NOT NULL, quarantined_at IS NOT NULL, publish_error "
        "FROM kafka_outbox ORDER BY position"
    ) == [
        (first.id, False, True, KafkaError.MSG_SIZE_TOO_LARGE),
        (following.id, False, False, None),
        (unrelated.id, True, False, None),
    ]
    applied = []
    with closing(consumer(uuid4().hex, commands)) as incoming:
        read_one(recovered, incoming, lambda _, message: applied.append(message.metadata.id) or {})
    assert applied == [unrelated.id]


def test_metadata_round_trip_preserves_partition_key():
    metadata = Metadata(uuid4(), uuid4(), "screening:session", uuid4(), 1, "command")
    assert Metadata.decode(metadata.encode()) == metadata
    assert metadata.key == f"screening:session:{metadata.entity_id}"
    with pytest.raises(ValueError, match="Invalid version"):
        replace(metadata, version=True)
