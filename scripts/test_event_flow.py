#!/usr/bin/env python3
"""
Artilery — End-to-End Kafka Smoke Test.

Verifies that the Kafka producer and consumer are correctly configured
by performing a round-trip test:

1. Produce a test bug.ingested event to Kafka.
2. Consume it from the same topic.
3. Assert the message round-trips correctly.
4. Print clear success/failure output.

Usage:
    python -m scripts.test_event_flow
"""

from __future__ import annotations

import json
import logging
import sys
import time
import threading
from typing import Any, Optional

from shared.config import get_settings
from shared.kafka_utils import KaosProducer, build_event_envelope

logger = logging.getLogger("artilery.scripts.test_event_flow")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

# ── Test configuration ───────────────────────────────────────────────────────

TEST_TOPIC = "bug.ingested"
TEST_GROUP_ID = "artilery-smoke-test"
TEST_TIMEOUT_SECONDS = 30

TEST_PAYLOAD: dict[str, Any] = {
    "bug_id": "TEST-001",
    "service": "PaymentService",
    "severity": "HIGH",
    "description": "Test bug — Artilery smoke test event",
}


def main() -> None:
    """Run the end-to-end Kafka smoke test."""
    logger.info("=" * 60)
    logger.info("Artilery — Kafka Smoke Test")
    logger.info("=" * 60)

    # Validate config.
    settings = get_settings()
    try:
        settings.validate()
    except ValueError as exc:
        logger.error("Configuration validation failed:\n%s", exc)
        sys.exit(1)

    # ── Step 1: Produce ──────────────────────────────────────────────────

    logger.info("")
    logger.info("STEP 1: Publishing test event to '%s'...", TEST_TOPIC)

    produced_envelope = build_event_envelope(
        event_type=TEST_TOPIC,
        payload=TEST_PAYLOAD,
    )
    produced_event_id = produced_envelope["event_id"]

    try:
        with KaosProducer() as producer:
            producer.publish(
                topic=TEST_TOPIC,
                key=TEST_PAYLOAD["bug_id"],
                value=TEST_PAYLOAD,
            )
            producer.flush(timeout=10.0)
        logger.info("✅ Event published | event_id=%s", produced_event_id)
    except Exception as exc:
        logger.error("❌ Failed to produce event | error=%s", exc)
        sys.exit(1)

    # ── Step 2: Consume ──────────────────────────────────────────────────

    logger.info("")
    logger.info("STEP 2: Consuming from '%s' (timeout=%ds)...", TEST_TOPIC, TEST_TIMEOUT_SECONDS)

    received_event: Optional[dict[str, Any]] = None
    consume_error: Optional[str] = None

    def consume_worker() -> None:
        """Worker thread to consume a single message."""
        nonlocal received_event, consume_error
        try:
            from confluent_kafka import Consumer as RawConsumer
            config = {
                **settings.get_kafka_config(),
                "group.id": f"{TEST_GROUP_ID}-{int(time.time())}",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
            consumer = RawConsumer(config)
            consumer.subscribe([TEST_TOPIC])

            deadline = time.time() + TEST_TIMEOUT_SECONDS
            while time.time() < deadline:
                msg = consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    continue
                try:
                    event = json.loads(msg.value())
                    # Check if this is our test event by matching the payload bug_id.
                    payload = event.get("payload", {})
                    if payload.get("bug_id") == TEST_PAYLOAD["bug_id"]:
                        received_event = event
                        break
                except json.JSONDecodeError:
                    continue
            consumer.close()
        except Exception as exc:
            consume_error = str(exc)

    # Start consumer BEFORE producing (it uses "latest" offset, so we
    # need it subscribed before the message arrives).
    # Actually, we already produced above. Let's re-produce to be safe.
    consumer_thread = threading.Thread(target=consume_worker, daemon=True)
    consumer_thread.start()

    # Give consumer time to subscribe, then produce again.
    time.sleep(2)

    logger.info("Re-publishing event for consumer to pick up...")
    try:
        with KaosProducer() as producer:
            producer.publish(
                topic=TEST_TOPIC,
                key=TEST_PAYLOAD["bug_id"],
                value=TEST_PAYLOAD,
            )
            producer.flush(timeout=10.0)
    except Exception as exc:
        logger.error("❌ Failed to re-produce event | error=%s", exc)

    consumer_thread.join(timeout=TEST_TIMEOUT_SECONDS + 5)

    # ── Step 3: Assert ───────────────────────────────────────────────────

    logger.info("")
    logger.info("STEP 3: Verifying round-trip...")

    if consume_error:
        logger.error("❌ Consumer error: %s", consume_error)
        sys.exit(1)

    if received_event is None:
        logger.error(
            "❌ FAILED — No message received within %d seconds. "
            "Check that the topic '%s' exists and Confluent Cloud is reachable.",
            TEST_TIMEOUT_SECONDS,
            TEST_TOPIC,
        )
        sys.exit(1)

    # Validate envelope structure.
    assertions_passed = True

    def check(condition: bool, description: str) -> None:
        nonlocal assertions_passed
        if condition:
            logger.info("  ✅ %s", description)
        else:
            logger.error("  ❌ %s", description)
            assertions_passed = False

    check("event_id" in received_event, "Event has event_id")
    check("event_type" in received_event, "Event has event_type")
    check("timestamp" in received_event, "Event has timestamp")
    check("payload" in received_event, "Event has payload")

    payload = received_event.get("payload", {})
    check(payload.get("bug_id") == "TEST-001", "payload.bug_id == 'TEST-001'")
    check(payload.get("service") == "PaymentService", "payload.service == 'PaymentService'")
    check(payload.get("severity") == "HIGH", "payload.severity == 'HIGH'")
    check(payload.get("description") == TEST_PAYLOAD["description"], "payload.description matches")

    # ── Step 4: Summary ──────────────────────────────────────────────────

    logger.info("")
    logger.info("=" * 60)
    if assertions_passed:
        logger.info("🎉 SMOKE TEST PASSED — Kafka round-trip verified!")
        logger.info("   Event produced → consumed → validated successfully.")
    else:
        logger.error("💥 SMOKE TEST FAILED — Some assertions did not pass.")
        logger.error("   Check the output above for details.")
        sys.exit(1)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
