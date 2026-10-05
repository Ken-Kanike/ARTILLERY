"""
Artilery Shared Kafka Utilities — Production-grade Producer & Consumer.

Provides KaosProducer and KaosConsumer wrappers around confluent-kafka
configured for Confluent Cloud (SASL/SSL). Features include:

- Automatic JSON serialization with event envelope (event_id, timestamp)
- Delivery confirmation callbacks with structured logging
- Retry logic with exponential backoff (producer)
- Graceful SIGTERM/SIGINT shutdown (consumer)
- Dead letter queue: failed messages go to {topic}.dlq after 3 attempts
- Context manager support for both producer and consumer

Usage:
    from shared.kafka_utils import KaosProducer, KaosConsumer

    # Produce
    with KaosProducer() as producer:
        producer.publish("bug.ingested", key="BUG-001", value={"service": "PaymentService"})

    # Consume
    consumer = KaosConsumer(topic="bug.ingested", group_id="triage-agent")
    consumer.consume(handler=my_handler_fn)
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic

from shared.config import get_settings

logger = logging.getLogger("artilery.kafka")

# ── Structured log format ────────────────────────────────────────────────────
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


# =============================================================================
# Event Envelope
# =============================================================================

def build_event_envelope(
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Wrap a raw payload in the standard Artilery event envelope.

    Every Kafka message in Artilery contains:
    - event_id:   UUID4 for deduplication and tracing
    - event_type: dot-notation topic name (e.g. bug.ingested)
    - timestamp:  ISO-8601 UTC timestamp
    - payload:    the actual event data
    """
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


# =============================================================================
# Producer
# =============================================================================

class KaosProducer:
    """Confluent Cloud Kafka producer with retry logic and delivery callbacks.

    Supports context manager usage:
        with KaosProducer() as p:
            p.publish("topic", "key", {"data": 1})
    """

    MAX_RETRIES: int = 3
    BACKOFF_BASE: float = 0.5  # seconds

    def __init__(self, config_overrides: Optional[dict[str, str]] = None) -> None:
        settings = get_settings()
        producer_config = {
            **settings.get_kafka_config(),
            "client.id": "artilery-producer",
            "acks": "all",
            "retries": 5,
            "retry.backoff.ms": 200,
            "linger.ms": 5,
            "compression.type": "snappy",
        }
        # Idempotence requires replication — disable for single-node local Kafka
        if not settings.is_local:
            producer_config["enable.idempotence"] = True

        if config_overrides:
            producer_config.update(config_overrides)

        self._producer = Producer(producer_config)
        bootstrap = settings.KAFKA_BOOTSTRAP_SERVERS if settings.is_local else settings.CONFLUENT_BOOTSTRAP_SERVERS
        logger.info("KaosProducer initialized | mode=%s | bootstrap=%s", settings.ARTILERY_ENV, bootstrap)

    # ── Context manager ──────────────────────────────────────────────────

    def __enter__(self) -> KaosProducer:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.flush()

    # ── Delivery callback ────────────────────────────────────────────────

    @staticmethod
    def _delivery_callback(err: Optional[KafkaError], msg: Any) -> None:
        """Log delivery success or failure for each produced message."""
        if err is not None:
            logger.error(
                "DELIVERY FAILED | topic=%s | partition=%s | error=%s",
                msg.topic(),
                msg.partition(),
                err,
            )
        else:
            logger.info(
                "DELIVERED | topic=%s | partition=%s | offset=%s | key=%s",
                msg.topic(),
                msg.partition(),
                msg.offset(),
                msg.key(),
            )

    # ── Publish ──────────────────────────────────────────────────────────

    def publish(
        self,
        topic: str,
        key: str,
        value: dict[str, Any],
        event_type: Optional[str] = None,
    ) -> None:
        """Publish a message to Kafka with automatic envelope wrapping.

        Args:
            topic: Kafka topic name.
            key: Message key (used for partitioning).
            value: Raw payload dict — will be wrapped in the event envelope.
            event_type: Override event_type in the envelope (defaults to topic name).

        Raises:
            KafkaException: After MAX_RETRIES exhausted.
        """
        envelope = build_event_envelope(
            event_type=event_type or topic,
            payload=value,
        )
        serialized = json.dumps(envelope).encode("utf-8")
        key_bytes = key.encode("utf-8")

        last_error: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self._producer.produce(
                    topic=topic,
                    key=key_bytes,
                    value=serialized,
                    callback=self._delivery_callback,
                )
                # Trigger delivery callbacks for previously produced messages.
                self._producer.poll(0)
                logger.info(
                    "PRODUCED | topic=%s | key=%s | event_id=%s | attempt=%d",
                    topic, key, envelope["event_id"], attempt,
                )
                return
            except BufferError as exc:
                last_error = exc
                backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Producer buffer full, retrying in %.1fs | attempt=%d/%d | topic=%s",
                    backoff, attempt, self.MAX_RETRIES, topic,
                )
                self._producer.poll(1)
                time.sleep(backoff)
            except KafkaException as exc:
                last_error = exc
                backoff = self.BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "Kafka produce error, retrying in %.1fs | attempt=%d/%d | topic=%s | error=%s",
                    backoff, attempt, self.MAX_RETRIES, topic, exc,
                )
                time.sleep(backoff)

        raise KafkaException(
            KafkaError._MSG_TIMED_OUT,
            f"Failed to produce to {topic} after {self.MAX_RETRIES} attempts: {last_error}",
        )

    # ── Flush ────────────────────────────────────────────────────────────

    def flush(self, timeout: float = 10.0) -> int:
        """Flush all buffered messages. Returns number of messages still in queue."""
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning("Producer flush timed out | remaining_messages=%d", remaining)
        else:
            logger.info("Producer flushed successfully")
        return remaining


# =============================================================================
# Consumer
# =============================================================================

class KaosConsumer:
    """Confluent Cloud Kafka consumer with dead letter queue and graceful shutdown.

    Usage:
        def handler(event: dict) -> None:
            print(event)

        consumer = KaosConsumer(topic="bug.ingested", group_id="triage-agent")
        consumer.consume(handler)  # blocks forever until SIGTERM/SIGINT
    """

    MAX_HANDLER_RETRIES: int = 3
    POLL_TIMEOUT: float = 1.0

    def __init__(
        self,
        topic: str,
        group_id: str,
        auto_offset_reset: str = "earliest",
        config_overrides: Optional[dict[str, str]] = None,
    ) -> None:
        settings = get_settings()
        consumer_config = {
            **settings.get_kafka_config(),
            "group.id": group_id,
            "auto.offset.reset": auto_offset_reset,
            "enable.auto.commit": True,
            "auto.commit.interval.ms": 5000,
            "session.timeout.ms": 30000,
            "max.poll.interval.ms": 300000,
        }
        if config_overrides:
            consumer_config.update(config_overrides)

        self._consumer = Consumer(consumer_config)
        self._topic = topic
        self._running = True
        self._dlq_producer: Optional[KaosProducer] = None

        logger.info(
            "KaosConsumer initialized | topic=%s | group=%s | offset_reset=%s",
            topic, group_id, auto_offset_reset,
        )

    # ── Context manager ──────────────────────────────────────────────────

    def __enter__(self) -> KaosConsumer:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # ── Signal handlers ──────────────────────────────────────────────────

    def _setup_signal_handlers(self) -> None:
        """Register SIGTERM and SIGINT handlers for graceful shutdown."""
        import threading
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping signal handler setup — not on main thread")
            return

        def _shutdown_handler(signum: int, frame: Any) -> None:
            sig_name = signal.Signals(signum).name
            logger.info("Received %s — initiating graceful shutdown", sig_name)
            self._running = False

        signal.signal(signal.SIGTERM, _shutdown_handler)
        signal.signal(signal.SIGINT, _shutdown_handler)

    # ── Dead letter queue ────────────────────────────────────────────────

    def _send_to_dlq(self, topic: str, raw_value: bytes, error: str) -> None:
        """Publish a failed message to the dead letter queue topic."""
        dlq_topic = f"{topic}.dlq"
        if self._dlq_producer is None:
            self._dlq_producer = KaosProducer()

        dlq_payload = {
            "original_topic": topic,
            "original_value": raw_value.decode("utf-8", errors="replace"),
            "error": str(error),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self._dlq_producer.publish(
                topic=dlq_topic,
                key="dlq",
                value=dlq_payload,
                event_type=f"{topic}.dlq",
            )
            logger.warning("Message sent to DLQ | dlq_topic=%s", dlq_topic)
        except KafkaException as dlq_err:
            logger.error(
                "Failed to send message to DLQ | dlq_topic=%s | error=%s",
                dlq_topic, dlq_err,
            )

    # ── Consume loop ─────────────────────────────────────────────────────

    def consume(
        self,
        handler: Callable[[dict[str, Any]], None],
        batch_size: int = 1,
    ) -> None:
        """Start an infinite consume loop, calling handler for each message.

        Args:
            handler: Function that receives a parsed dict (the event envelope).
                     Must not return a value. Raise an exception to signal failure.
            batch_size: Reserved for future batch processing. Currently processes
                        one message at a time.

        The loop runs until SIGTERM/SIGINT. If the handler raises an exception
        3 times for the same message, the message is sent to {topic}.dlq.
        """
        self._setup_signal_handlers()
        self._consumer.subscribe([self._topic])
        logger.info("Consumer subscribed | topic=%s — entering poll loop", self._topic)

        try:
            while self._running:
                msg = self._consumer.poll(timeout=self.POLL_TIMEOUT)
                if msg is None:
                    continue

                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        logger.debug(
                            "Reached end of partition | topic=%s | partition=%s | offset=%s",
                            msg.topic(), msg.partition(), msg.offset(),
                        )
                        continue
                    logger.error("Consumer error | error=%s", msg.error())
                    continue

                # Parse the message value.
                raw_value = msg.value()
                try:
                    event = json.loads(raw_value)
                except json.JSONDecodeError as parse_err:
                    logger.error(
                        "Failed to parse message as JSON | topic=%s | error=%s",
                        msg.topic(), parse_err,
                    )
                    self._send_to_dlq(msg.topic(), raw_value, str(parse_err))
                    continue

                # Attempt to handle the message with retries.
                last_error: Exception | None = None
                for attempt in range(1, self.MAX_HANDLER_RETRIES + 1):
                    try:
                        logger.info(
                            "HANDLING | topic=%s | event_id=%s | attempt=%d/%d",
                            msg.topic(),
                            event.get("event_id", "unknown"),
                            attempt,
                            self.MAX_HANDLER_RETRIES,
                        )
                        handler(event)
                        last_error = None
                        break
                    except Exception as handler_err:
                        last_error = handler_err
                        logger.warning(
                            "Handler failed | topic=%s | event_id=%s | attempt=%d/%d | error=%s",
                            msg.topic(),
                            event.get("event_id", "unknown"),
                            attempt,
                            self.MAX_HANDLER_RETRIES,
                            handler_err,
                        )

                if last_error is not None:
                    logger.error(
                        "Handler exhausted retries — sending to DLQ | topic=%s | event_id=%s",
                        msg.topic(),
                        event.get("event_id", "unknown"),
                    )
                    self._send_to_dlq(msg.topic(), raw_value, str(last_error))

        except KafkaException as exc:
            logger.error("Fatal consumer error | error=%s", exc)
            raise
        finally:
            self.close()

    # ── Cleanup ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the consumer and flush the DLQ producer."""
        logger.info("Closing consumer | topic=%s", self._topic)
        try:
            self._consumer.close()
        except RuntimeError:
            pass  # Already closed
        if self._dlq_producer is not None:
            self._dlq_producer.flush()
        logger.info("Consumer closed | topic=%s", self._topic)


# =============================================================================
# Admin Helpers
# =============================================================================

def get_admin_client() -> AdminClient:
    """Create a Confluent AdminClient from settings."""
    settings = get_settings()
    return AdminClient(settings.get_kafka_config())


def create_topics(
    topics: list[str],
    num_partitions: int = 3,
    replication_factor: int | None = None,
    retention_ms: int = 604800000,  # 7 days
) -> dict[str, str]:
    """Create Kafka topics using the Confluent Admin API.

    Args:
        topics: List of topic names to create.
        num_partitions: Number of partitions per topic.
        replication_factor: Replication factor per topic. Auto-detected:
                            1 for local mode, 3 for production.
        retention_ms: Retention period in milliseconds (default 7 days).

    Returns:
        Dict mapping topic name to creation result ("created" or error string).
    """
    settings = get_settings()
    if replication_factor is None:
        replication_factor = 1 if settings.is_local else 3

    admin = get_admin_client()
    new_topics = [
        NewTopic(
            topic=name,
            num_partitions=num_partitions,
            replication_factor=replication_factor,
            config={"retention.ms": str(retention_ms)},
        )
        for name in topics
    ]

    results: dict[str, str] = {}
    futures = admin.create_topics(new_topics)

    for topic_name, future in futures.items():
        try:
            future.result()  # Block until topic is created or fails.
            results[topic_name] = "created"
            logger.info("Topic created | topic=%s | partitions=%d | rf=%d", topic_name, num_partitions, replication_factor)
        except KafkaException as exc:
            error_msg = str(exc)
            if "TOPIC_ALREADY_EXISTS" in error_msg:
                results[topic_name] = "already_exists"
                logger.info("Topic already exists | topic=%s", topic_name)
            else:
                results[topic_name] = f"error: {error_msg}"
                logger.error("Failed to create topic | topic=%s | error=%s", topic_name, error_msg)
        except Exception as exc:
            results[topic_name] = f"error: {exc}"
            logger.error("Unexpected error creating topic | topic=%s | error=%s", topic_name, exc)

    return results
