from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from confluent_kafka import Consumer
    from confluent_kafka import KafkaError
    from confluent_kafka import Producer
except ImportError:  # pragma: no cover - exercised only when dependency is absent
    Consumer = None
    KafkaError = None
    Producer = None


@dataclass(frozen=True)
class KafkaSettings:
    bootstrap_servers: str
    group_id: str | None = None
    auto_offset_reset: str = "earliest"


@dataclass(frozen=True)
class ConsumedEvent:
    topic: str
    key: str | None
    payload: dict[str, Any]
    partition: int
    offset: int
    raw_message: Any


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def load_kafka_settings(env_file: Path | None, group_id: str | None = None) -> KafkaSettings:
    env_values = load_env_file(env_file) if env_file else {}

    def resolve(name: str, default: str | None = None) -> str:
        value = os.getenv(name, env_values.get(name, default))
        if value is None:
            raise RuntimeError(f"Missing required Kafka setting: {name}")
        return value

    return KafkaSettings(
        bootstrap_servers=resolve("REDPANDA_BROKERS", "localhost:9092"),
        group_id=group_id,
        auto_offset_reset=resolve("KAFKA_AUTO_OFFSET_RESET", "earliest"),
    )


class EventProducer:
    def __init__(self, settings: KafkaSettings, client_id: str) -> None:
        if Producer is None:
            raise RuntimeError(
                "Event publishing requires confluent-kafka. Install the shared package "
                "dependencies before running Kafka-enabled workers."
            )
        self._producer = Producer(
            {
                "bootstrap.servers": settings.bootstrap_servers,
                "client.id": client_id,
                "acks": "all",
            }
        )

    def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        encoded_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        encoded_headers = list(headers.items()) if headers else None
        self._producer.produce(topic=topic, key=key, value=encoded_payload, headers=encoded_headers)
        self._producer.poll(0)

    def flush(self, timeout_seconds: float = 10.0) -> None:
        self._producer.flush(timeout_seconds)


class EventConsumer:
    def __init__(self, settings: KafkaSettings, topics: list[str], client_id: str) -> None:
        if Consumer is None:
            raise RuntimeError(
                "Event consumption requires confluent-kafka. Install the shared package "
                "dependencies before running Kafka-enabled workers."
            )
        if not settings.group_id:
            raise RuntimeError("Kafka consumer settings require a group_id.")
        self._consumer = Consumer(
            {
                "bootstrap.servers": settings.bootstrap_servers,
                "group.id": settings.group_id,
                "client.id": client_id,
                "auto.offset.reset": settings.auto_offset_reset,
                "enable.auto.commit": False,
                "allow.auto.create.topics": True,
            }
        )
        self._consumer.subscribe(topics)

    def poll(self, timeout_seconds: float = 1.0) -> ConsumedEvent | None:
        message = self._consumer.poll(timeout_seconds)
        if message is None:
            return None

        if message.error():
            if KafkaError is not None and _is_transient_consumer_error(message.error()):
                return None
            raise RuntimeError(f"Kafka consumer error: {message.error()}")

        raw_value = message.value()
        payload = json.loads(raw_value.decode("utf-8")) if raw_value else {}
        raw_key = message.key()
        key = raw_key.decode("utf-8") if raw_key else None
        return ConsumedEvent(
            topic=message.topic(),
            key=key,
            payload=payload,
            partition=message.partition(),
            offset=message.offset(),
            raw_message=message,
        )

    def commit(self, event: ConsumedEvent) -> None:
        self._consumer.commit(event.raw_message)

    def close(self) -> None:
        self._consumer.close()


def _is_transient_consumer_error(error) -> bool:
    if KafkaError is None:
        return False

    transient_codes = {
        KafkaError._PARTITION_EOF,
        KafkaError._TRANSPORT,
        KafkaError._ALL_BROKERS_DOWN,
        KafkaError.LEADER_NOT_AVAILABLE,
        KafkaError.UNKNOWN_TOPIC_OR_PART,
    }
    return error.code() in transient_codes or error.retriable()
