"""
Artilery — Kafka Utilities Unit Tests.

Tests for the shared Kafka producer and consumer wrappers including
event envelope creation, serialization, and error handling.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from shared.kafka_utils import build_event_envelope


class TestBuildEventEnvelope:
    """Tests for the event envelope builder."""

    def test_envelope_has_required_fields(self) -> None:
        """Envelope must contain event_id, event_type, timestamp, payload."""
        envelope = build_event_envelope(
            event_type="bug.ingested",
            payload={"bug_id": "BUG-001"},
        )

        assert "event_id" in envelope
        assert "event_type" in envelope
        assert "timestamp" in envelope
        assert "payload" in envelope

    def test_event_id_is_valid_uuid4(self) -> None:
        """event_id must be a valid UUID4 string."""
        envelope = build_event_envelope("test.event", {})
        parsed = uuid.UUID(envelope["event_id"], version=4)
        assert str(parsed) == envelope["event_id"]

    def test_event_type_matches_input(self) -> None:
        """event_type must match the provided topic name."""
        envelope = build_event_envelope("bug.ingested", {})
        assert envelope["event_type"] == "bug.ingested"

    def test_timestamp_is_iso8601_utc(self) -> None:
        """timestamp must be a valid ISO-8601 UTC datetime string."""
        envelope = build_event_envelope("test.event", {})
        parsed = datetime.fromisoformat(envelope["timestamp"])
        assert parsed.tzinfo is not None

    def test_payload_is_preserved(self) -> None:
        """The raw payload must be embedded unchanged."""
        payload = {"bug_id": "BUG-001", "service": "PaymentService", "severity": "HIGH"}
        envelope = build_event_envelope("bug.ingested", payload)
        assert envelope["payload"] == payload

    def test_envelope_is_json_serializable(self) -> None:
        """The complete envelope must be JSON-serializable."""
        envelope = build_event_envelope(
            "bug.ingested",
            {"bug_id": "BUG-001", "nested": {"key": [1, 2, 3]}},
        )
        serialized = json.dumps(envelope)
        deserialized = json.loads(serialized)
        assert deserialized == envelope

    def test_each_call_produces_unique_event_id(self) -> None:
        """Consecutive calls must produce different event_ids."""
        e1 = build_event_envelope("test.event", {})
        e2 = build_event_envelope("test.event", {})
        assert e1["event_id"] != e2["event_id"]


class TestKaosProducerConfig:
    """Tests for producer configuration."""

    @patch("shared.kafka_utils.get_settings")
    @patch("shared.kafka_utils.Producer")
    def test_producer_uses_sasl_ssl(self, mock_producer_cls: MagicMock, mock_settings: MagicMock) -> None:
        """Producer must configure SASL_SSL security protocol."""
        mock_settings.return_value.get_kafka_config.return_value = {
            "bootstrap.servers": "test:9092",
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": "key",
            "sasl.password": "secret",
        }
        mock_settings.return_value.CONFLUENT_BOOTSTRAP_SERVERS = "test:9092"

        from shared.kafka_utils import KaosProducer
        producer = KaosProducer()

        # Verify Producer was called with SASL_SSL config.
        call_args = mock_producer_cls.call_args[0][0]
        assert call_args["security.protocol"] == "SASL_SSL"
        assert call_args["sasl.mechanisms"] == "PLAIN"


class TestKaosConsumerConfig:
    """Tests for consumer configuration."""

    @patch("shared.kafka_utils.get_settings")
    @patch("shared.kafka_utils.Consumer")
    def test_consumer_uses_group_id(self, mock_consumer_cls: MagicMock, mock_settings: MagicMock) -> None:
        """Consumer must set the provided group.id."""
        mock_settings.return_value.get_kafka_config.return_value = {
            "bootstrap.servers": "test:9092",
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": "key",
            "sasl.password": "secret",
        }

        from shared.kafka_utils import KaosConsumer
        consumer = KaosConsumer(
            topic="bug.ingested",
            group_id="test-group",
            auto_offset_reset="earliest",
        )

        call_args = mock_consumer_cls.call_args[0][0]
        assert call_args["group.id"] == "test-group"
        assert call_args["auto.offset.reset"] == "earliest"
