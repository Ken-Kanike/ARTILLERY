#!/usr/bin/env python3
"""
Artilery — Kafka Topic Creation Script.

Programmatically creates all required Kafka topics on Confluent Cloud
using the Confluent Admin API. Safe to run multiple times (idempotent).

Topics created:
  Core event topics (10):
    bug.ingested, ticket.created, pr.opened, pr.review.requested,
    pr.reviewed, pr.approved, deploy.triggered, deploy.failed,
    deploy.succeeded, ticket.resolved

  Dead letter queue topics (10):
    {each core topic}.dlq

Configuration:
  Each topic: 3 partitions, replication factor 3, 7-day retention.

Usage:
    python -m scripts.create_kafka_topics
"""

from __future__ import annotations

import logging
import sys

from shared.config import get_settings
from shared.kafka_utils import create_topics

logger = logging.getLogger("artilery.scripts.create_topics")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

# ── Topic definitions ────────────────────────────────────────────────────────

CORE_TOPICS: list[str] = [
    "bug.ingested",
    "ticket.created",
    "pr.opened",
    "pr.review.requested",
    "pr.reviewed",
    "pr.approved",
    "deploy.triggered",
    "deploy.failed",
    "deploy.succeeded",
    "ticket.resolved",
]

# Dead letter queue topics — one for each core topic.
DLQ_TOPICS: list[str] = [f"{topic}.dlq" for topic in CORE_TOPICS]

ALL_TOPICS: list[str] = CORE_TOPICS + DLQ_TOPICS

# ── Topic configuration ─────────────────────────────────────────────────────

NUM_PARTITIONS: int = 3
RETENTION_MS: int = 604800000  # 7 days in milliseconds


def main() -> None:
    """Create all Artilery Kafka topics."""
    logger.info("=" * 60)
    logger.info("Artilery — Kafka Topic Creation")
    logger.info("=" * 60)

    # Validate config before attempting topic creation.
    settings = get_settings()
    try:
        settings.validate()
    except ValueError as exc:
        logger.error("Configuration validation failed:\n%s", exc)
        sys.exit(1)

    # Auto-detect replication factor based on environment
    replication_factor = 1 if settings.is_local else 3

    logger.info(
        "Creating %d topics (%d core + %d DLQ) | partitions=%d | replication=%d | retention=%d ms",
        len(ALL_TOPICS),
        len(CORE_TOPICS),
        len(DLQ_TOPICS),
        NUM_PARTITIONS,
        replication_factor,
        RETENTION_MS,
    )

    results = create_topics(
        topics=ALL_TOPICS,
        num_partitions=NUM_PARTITIONS,
        replication_factor=replication_factor,
        retention_ms=RETENTION_MS,
    )

    # Print summary.
    logger.info("")
    logger.info("=" * 60)
    logger.info("TOPIC CREATION SUMMARY")
    logger.info("=" * 60)

    created_count = 0
    existing_count = 0
    error_count = 0

    for topic_name, result in sorted(results.items()):
        if result == "created":
            status = "✅ CREATED"
            created_count += 1
        elif result == "already_exists":
            status = "⏭️  EXISTS"
            existing_count += 1
        else:
            status = f"❌ ERROR: {result}"
            error_count += 1

        logger.info("  %-40s %s", topic_name, status)

    logger.info("")
    logger.info(
        "Results: %d created | %d already existed | %d errors",
        created_count, existing_count, error_count,
    )

    if error_count > 0:
        logger.error("Some topics failed to create. Check the errors above.")
        sys.exit(1)

    logger.info("All topics ready! ✅")


if __name__ == "__main__":
    main()
