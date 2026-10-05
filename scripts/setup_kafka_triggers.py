#!/usr/bin/env python3
"""
Artilery — Kafka Lambda Event Source Mapping Setup.

Configures Lambda event source mappings for Confluent Cloud topics.

Mappings:
  - artilery-triage  ← bug.ingested
  - artilery-review  ← pr.opened, pr.reviewed, pr.approved
  - artilery-ops     ← deploy.triggered, deploy.failed, deploy.succeeded

Usage:
    python -m scripts.setup_kafka_triggers
"""

from __future__ import annotations

import json
import logging
import sys

logger = logging.getLogger("artilery.scripts.setup_kafka_triggers")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


KAFKA_TRIGGERS = {
    "artilery-triage": ["bug.ingested"],
    "artilery-review": ["pr.opened", "pr.reviewed", "pr.approved"],
    "artilery-ops": ["deploy.triggered", "deploy.failed", "deploy.succeeded"],
}


def main() -> None:
    import boto3
    from shared.config import get_settings

    settings = get_settings()
    lambda_client = boto3.client("lambda", region_name=settings.AWS_REGION)

    logger.info("=" * 60)
    logger.info("Artilery — Kafka Event Source Mapping Setup")
    logger.info("=" * 60)

    bootstrap_servers = settings.CONFLUENT_BOOTSTRAP_SERVERS

    for func_name, topics in KAFKA_TRIGGERS.items():
        for topic in topics:
            logger.info("Setting up %s → %s", topic, func_name)

            # Check for existing mapping
            existing = lambda_client.list_event_source_mappings(
                EventSourceArn=f"arn:aws:kafka:::topic/{topic}",
                FunctionName=func_name,
            ).get("EventSourceMappings", [])

            if existing:
                logger.info("  ⏭️  Mapping exists for %s → %s", topic, func_name)
                continue

            try:
                lambda_client.create_event_source_mapping(
                    EventSourceArn=f"arn:aws:kafka:::topic/{topic}",
                    FunctionName=func_name,
                    StartingPosition="LATEST",
                    BatchSize=10,
                    MaximumBatchingWindowInSeconds=5,
                    SourceAccessConfigurations=[
                        {
                            "Type": "SASL_SCRAM_512_AUTH",
                            "URI": f"arn:aws:secretsmanager:{settings.AWS_REGION}:"
                                   f"{boto3.client('sts').get_caller_identity()['Account']}:"
                                   f"secret:artilery/kafka-credentials",
                        },
                    ],
                    SelfManagedEventSource={
                        "Endpoints": {"KAFKA_BOOTSTRAP_SERVERS": [bootstrap_servers]},
                    },
                    Topics=[topic],
                )
                logger.info("  ✅ Created mapping: %s → %s", topic, func_name)
            except Exception as exc:
                logger.error("  ❌ Failed: %s → %s | %s", topic, func_name, exc)

    logger.info("\n✅ Kafka trigger setup complete!")


if __name__ == "__main__":
    main()
