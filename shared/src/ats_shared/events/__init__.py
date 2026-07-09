"""Kafka-compatible event helpers for ATS services."""

from ats_shared.events.kafka import EventConsumer
from ats_shared.events.kafka import EventProducer
from ats_shared.events.kafka import KafkaSettings
from ats_shared.events.kafka import load_kafka_settings
from ats_shared.events.topics import CANDIDATE_RANKED_TOPIC
from ats_shared.events.topics import RESUME_EMBEDDED_TOPIC
from ats_shared.events.topics import RESUME_PARSED_TOPIC
from ats_shared.events.topics import RESUME_UPLOADED_TOPIC

__all__ = [
    "CANDIDATE_RANKED_TOPIC",
    "EventConsumer",
    "EventProducer",
    "KafkaSettings",
    "RESUME_EMBEDDED_TOPIC",
    "RESUME_PARSED_TOPIC",
    "RESUME_UPLOADED_TOPIC",
    "load_kafka_settings",
]
