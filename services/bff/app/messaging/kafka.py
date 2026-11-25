import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from confluent_kafka import Consumer, KafkaException, Producer
from pg8000.dbapi import Connection, Cursor, connect


@dataclass(frozen=True)
class Metadata:
    id: UUID
    operation_id: UUID
    stream: str
    entity_id: UUID
    version: int
    kind: Literal["command", "event"]

    def __post_init__(self):
        if not all(isinstance(value, UUID) for value in (self.id, self.operation_id, self.entity_id)):
            raise ValueError("Invalid identifier")
        if not isinstance(self.stream, str) or not self.stream or "\x00" in self.stream:
            raise ValueError("Invalid stream")
        if type(self.version) is not int or not 0 < self.version < 2**63:
            raise ValueError("Invalid version")
        if self.kind not in ("command", "event"):
            raise ValueError("Invalid message kind")

    @property
    def key(self) -> str:
        return f"{self.stream}:{self.entity_id}"

    def encode(self) -> bytes:
        return json.dumps(asdict(self), default=str, sort_keys=True).encode()

    @classmethod
    def decode(cls, data: bytes):
        values = json.loads(data)
        for field in ("id", "operation_id", "entity_id"):
            values[field] = UUID(values[field])
        return cls(**values)


@dataclass(frozen=True)
class Message:
    topic: str
    metadata: Metadata
    payload: bytes

    def __post_init__(self):
        _validate_topic(self.topic)
        if not isinstance(self.payload, bytes):
            raise TypeError("Message payload must be bytes")

    def fingerprint(self) -> bytes:
        values = asdict(self.metadata)
        del values["id"]
        identity = json.dumps([self.topic, values], default=str, sort_keys=True).encode()
        return hashlib.sha256(identity + b"\x00" + self.payload).digest()


class RejectMessage(Exception):
    pass


Handler = Callable[[Cursor, Message], dict]
_HEADER = "mis-delivery"


def _validate_topic(topic: str):
    if topic in (".", "..") or not re.fullmatch(r"[a-zA-Z0-9._-]{1,249}", topic):
        raise ValueError("Invalid Kafka topic")


class KafkaInboxOutbox:
    def __init__(
        self,
        connection: Callable[[], Connection],
        producer: Producer,
        *,
        dead_letter_topic: str,
        max_attempts: int = 3,
        retry_delay: float = 0.2,
        publish_timeout: float = 10,
    ):
        if max_attempts < 1 or retry_delay < 0 or publish_timeout <= 0:
            raise ValueError("Invalid retry or publication settings")
        _validate_topic(dead_letter_topic)
        self.connection = connection
        self.producer = producer
        self.dead_letter_topic = dead_letter_topic
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self.publish_timeout = publish_timeout

    @classmethod
    def from_config(cls, database: dict, brokers: str, **settings):
        return cls(
            lambda: connect(**database),
            Producer({
                "bootstrap.servers": brokers,
                "enable.idempotence": True,
                "message.timeout.ms": 8000,
            }),
            **settings,
        )

    @classmethod
    def from_environment(cls, **settings):
        return cls.from_config(
            {
                "host": os.environ["PGHOST"],
                "database": "mis_bff",
                "user": "mis_bff_app",
                "password": Path("/run/secrets/db-password").read_text().strip(),
                "timeout": 10,
            },
            os.environ["KAFKA_BOOTSTRAP_SERVERS"],
            **settings,
        )

    @staticmethod
    def consumer(brokers: str, group_id: str, topics: list[str]) -> Consumer:
        consumer = Consumer({
            "bootstrap.servers": brokers,
            "group.id": group_id,
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
        })
        consumer.subscribe(topics)
        return consumer

    def submit(self, message: Message):
        with self._transaction() as cursor:
            self.enqueue(cursor, message)

    @contextmanager
    def _transaction(self):
        connection = self.connection()
        try:
            cursor = connection.cursor()
            try:
                yield cursor
                connection.commit()
            finally:
                cursor.close()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _lock(cursor: Cursor, key: str):
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))

    @staticmethod
    def enqueue(cursor: Cursor, message: Message):
        KafkaInboxOutbox._lock(cursor, f"kafka:outbox:{message.metadata.key}")
        values = (message.topic, message.metadata.key, message.payload, message.metadata.encode())
        cursor.execute(
            "INSERT INTO public.kafka_outbox (id, topic, entity_key, payload, metadata) "
            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING RETURNING id",
            (message.metadata.id, *values),
        )
        if cursor.fetchone():
            return
        cursor.execute(
            "SELECT topic, entity_key, payload, metadata FROM public.kafka_outbox WHERE id = %s",
            (message.metadata.id,),
        )
        if tuple(cursor.fetchone()) != values:
            raise RejectMessage("Outbox message ID already has a different payload")

    def operation(self, operation_id: UUID) -> dict | None:
        with self._transaction() as cursor:
            cursor.execute("SELECT outcome FROM public.kafka_operations WHERE id = %s", (operation_id,))
            row = cursor.fetchone()
            return row[0] if row else None

    def publish_one(self) -> bool:
        with self._transaction() as cursor:
            self._lock(cursor, "kafka:publish")
            cursor.execute(
                "SELECT id, topic, entity_key, payload, metadata FROM public.kafka_outbox "
                "WHERE published_at IS NULL ORDER BY position LIMIT 1"
            )
            row = cursor.fetchone()
            if row is None:
                return False
            identifier, topic, key, payload, metadata = row
            reports = []
            headers = [(_HEADER, metadata)] if metadata is not None else []
            self.producer.produce(
                topic, key=key, value=payload, headers=headers,
                on_delivery=lambda error, _: reports.append(error),
            )
            self.producer.flush(self.publish_timeout)
            if not reports:
                raise TimeoutError("Kafka delivery confirmation timed out")
            if reports[0] is not None:
                raise KafkaException(reports[0])
            cursor.execute(
                "UPDATE public.kafka_outbox SET published_at = clock_timestamp() WHERE id = %s",
                (identifier,),
            )
            return True

    def consume_one(self, consumer: Consumer, handler: Handler, timeout: float = 1) -> bool:
        try:
            return self._consume(consumer, handler, timeout)
        except BaseException:
            consumer.close()
            raise

    def _consume(self, consumer, handler, timeout):
        record = consumer.poll(timeout)
        if record is None:
            return False
        if record.error() is not None:
            raise KafkaException(record.error())
        location = (record.topic(), record.partition(), record.offset())
        try:
            headers = [value for name, value in record.headers() or [] if name == _HEADER]
            if len(headers) != 1 or record.value() is None:
                raise ValueError("Missing message data")
            metadata = Metadata.decode(headers[0])
            if record.key() != metadata.key.encode():
                raise ValueError("Wrong partition key")
            message = Message(record.topic(), metadata, record.value())
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
            with self._transaction() as cursor:
                self._dead_letter(cursor, location, "invalid_message")
        else:
            while not self._attempt(message, handler, location):
                time.sleep(self.retry_delay)
        partitions = consumer.commit(message=record, asynchronous=False)
        for partition in partitions:
            if partition.error is not None:
                raise KafkaException(partition.error)
        return True

    def _dead_letter(self, cursor, location, code):
        topic, partition, offset = location
        payload = json.dumps({"topic": topic, "partition": partition, "offset": offset, "code": code})
        key = f"{topic}:{partition}:{offset}"
        cursor.execute(
            "INSERT INTO public.kafka_outbox (id, topic, entity_key, payload) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO NOTHING",
            (uuid5(NAMESPACE_URL, f"kafka:{key}"), self.dead_letter_topic, key, payload.encode()),
        )

    def _attempt(self, message, handler, location) -> bool:
        metadata = message.metadata
        fingerprint = message.fingerprint()
        with self._transaction() as cursor:
            self._lock(cursor, f"kafka:message:{metadata.id}")
            cursor.execute("SELECT fingerprint, attempts, outcome FROM public.kafka_inbox WHERE id = %s", (metadata.id,))
            row = cursor.fetchone()
            if row and row[0] != fingerprint:
                self._dead_letter(cursor, location, "idempotency_conflict")
                return True
            if row and row[2] is not None:
                return True
            attempts = row[1] if row else 0
            if not row:
                cursor.execute(
                    "INSERT INTO public.kafka_inbox (id, fingerprint) VALUES (%s, %s)",
                    (metadata.id, fingerprint),
                )
            if metadata.kind == "command":
                self._lock(cursor, f"kafka:operation:{metadata.operation_id}")
                cursor.execute(
                    "SELECT fingerprint, outcome, attempts FROM public.kafka_operations WHERE id = %s",
                    (metadata.operation_id,),
                )
                previous = cursor.fetchone()
                if previous and previous[0] != fingerprint:
                    outcome = {"error": "idempotency_conflict"}
                    self._dead_letter(cursor, location, outcome["error"])
                    self._finish_inbox(cursor, metadata.id, attempts, outcome)
                    return True
                if previous and previous[1] is not None:
                    self._finish_inbox(cursor, metadata.id, attempts, previous[1])
                    return True
                if previous:
                    attempts = previous[2]
                else:
                    cursor.execute(
                        "INSERT INTO public.kafka_operations (id, fingerprint) VALUES (%s, %s)",
                        (metadata.operation_id, fingerprint),
                    )
            self._lock(cursor, f"kafka:entity:{metadata.key}")
            outcome, retry = self._apply(cursor, message, handler)
            attempts += 1
            if retry and attempts < self.max_attempts:
                cursor.execute("UPDATE public.kafka_inbox SET attempts = %s WHERE id = %s", (attempts, metadata.id))
                if metadata.kind == "command":
                    cursor.execute(
                        "UPDATE public.kafka_operations SET attempts = %s WHERE id = %s",
                        (attempts, metadata.operation_id),
                    )
                return False
            if "error" in outcome:
                self._dead_letter(cursor, location, outcome["error"])
            self._finish_inbox(cursor, metadata.id, attempts, outcome)
            if metadata.kind == "command":
                cursor.execute(
                    "UPDATE public.kafka_operations SET attempts = %s, outcome = %s::jsonb WHERE id = %s",
                    (attempts, json.dumps(outcome), metadata.operation_id),
                )
            return True

    @staticmethod
    def _finish_inbox(cursor, identifier, attempts, outcome):
        cursor.execute(
            "UPDATE public.kafka_inbox SET attempts = %s, outcome = %s::jsonb WHERE id = %s",
            (attempts, json.dumps(outcome), identifier),
        )

    @staticmethod
    def _apply(cursor, message, handler):
        metadata = message.metadata
        cursor.execute(
            "SELECT version FROM public.kafka_versions WHERE kind = %s AND entity_key = %s",
            (metadata.kind, metadata.key),
        )
        row = cursor.fetchone()
        version = row[0] if row else 0
        if metadata.version <= version:
            if metadata.kind == "event":
                return {"status": "stale"}, False
            return {"error": "stale_version"}, False
        if metadata.kind == "command" and metadata.version != version + 1:
            return {"error": "version_gap"}, False
        cursor.execute("SAVEPOINT kafka_handler")
        try:
            result = handler(cursor, message)
            json.dumps(result, allow_nan=False)
        except RejectMessage:
            cursor.execute("ROLLBACK TO SAVEPOINT kafka_handler")
            return {"error": "rejected"}, False
        except Exception:
            cursor.execute("ROLLBACK TO SAVEPOINT kafka_handler")
            return {"error": "handler_failed"}, True
        cursor.execute("RELEASE SAVEPOINT kafka_handler")
        cursor.execute(
            "INSERT INTO public.kafka_versions (kind, entity_key, version) VALUES (%s, %s, %s) "
            "ON CONFLICT (kind, entity_key) DO UPDATE SET version = excluded.version",
            (metadata.kind, metadata.key, metadata.version),
        )
        return {"status": "succeeded", "result": result}, False
