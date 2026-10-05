#!/usr/bin/env python3
"""
Artilery — S3 Event Indexer for ChromaDB Vector Store.

Scans the S3 event log bucket, converts each event to readable text,
embeds it using Bedrock Titan, and stores it in ChromaDB for RAG retrieval.

Tracks indexed files in DynamoDB to avoid re-indexing.
Designed to run on a schedule (daily via EventBridge).

Usage:
    python -m scripts.index_events
    python -m scripts.index_events --days 30  # Index last 30 days
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from shared.config import get_settings
from shared.dynamo_utils import DynamoClient
from shared.s3_utils import S3Client
from shared.vector_store import VectorStore, chunk_text

logger = logging.getLogger("artilery.scripts.index_events")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

# Event types to index
EVENT_TYPES = [
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


def event_to_text(event: dict[str, Any]) -> str:
    """Convert an event JSON to human-readable text for embedding."""
    event_type = event.get("event_type", "unknown")
    timestamp = event.get("timestamp", "unknown")
    payload = event.get("payload", {})

    service = payload.get("service_name", payload.get("service", "unknown"))

    parts = [f"On {timestamp}, a {event_type} event occurred for {service}."]

    if event_type == "bug.ingested":
        parts.append(f"Bug ID: {payload.get('bug_id', 'N/A')}. "
                     f"Severity: {payload.get('severity', 'N/A')}. "
                     f"Description: {payload.get('description', 'N/A')}.")

    elif event_type == "ticket.created":
        parts.append(f"Jira ticket {payload.get('jira_ticket_key', 'N/A')} was created. "
                     f"Priority: {payload.get('priority', 'N/A')}. "
                     f"Assignee: {payload.get('assignee_slack_id', 'N/A')}.")

    elif event_type in ("pr.opened", "pr.approved", "pr.reviewed"):
        parts.append(f"PR #{payload.get('pr_number', 'N/A')}: {payload.get('pr_title', 'N/A')}. "
                     f"Author: {payload.get('pr_author', {}).get('login', 'N/A')}. "
                     f"Jira: {payload.get('jira_ticket_key', 'N/A')}.")

    elif event_type in ("deploy.triggered", "deploy.failed", "deploy.succeeded"):
        parts.append(f"Deployment ID: {payload.get('deployment_id', 'N/A')}. "
                     f"Status: {payload.get('status', event_type.split('.')[-1])}.")
        if payload.get("error_message"):
            parts.append(f"Error: {payload['error_message']}")

    elif event_type == "ticket.resolved":
        parts.append(f"Jira ticket {payload.get('jira_ticket_key', 'N/A')} was resolved. "
                     f"Deployment: {payload.get('deployment_id', 'N/A')}.")

    else:
        parts.append(f"Details: {json.dumps(payload, default=str)[:500]}")

    return " ".join(parts)


def is_already_indexed(dynamo: DynamoClient, s3_key: str) -> bool:
    """Check if an S3 key has already been indexed."""
    table = dynamo._get_table()
    response = table.get_item(Key={"pk": f"indexed#{s3_key}", "sk": "status"})
    return response.get("Item") is not None


def mark_as_indexed(dynamo: DynamoClient, s3_key: str) -> None:
    """Mark an S3 key as indexed in DynamoDB."""
    table = dynamo._get_table()
    table.put_item(Item={
        "pk": f"indexed#{s3_key}",
        "sk": "status",
        "indexed_at": datetime.now(timezone.utc).isoformat(),
    })


def main() -> None:
    """Run the event indexer."""
    parser = argparse.ArgumentParser(description="Index S3 events into ChromaDB")
    parser.add_argument("--days", type=int, default=7, help="Number of days to look back (default: 7)")
    parser.add_argument("--collection", default="event_logs", help="ChromaDB collection name")
    parser.add_argument("--dry-run", action="store_true", help="Print events without indexing")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Artilery — Event Indexer")
    logger.info("=" * 60)
    logger.info("Looking back %d days | collection=%s", args.days, args.collection)

    s3 = S3Client()
    dynamo = DynamoClient()
    vs = VectorStore(collection_name=args.collection)

    total_indexed = 0
    total_skipped = 0
    total_errors = 0

    for event_type in EVENT_TYPES:
        logger.info("Scanning event type: %s", event_type)
        try:
            keys = s3.list_recent_events(event_type, days=args.days)
        except Exception as exc:
            logger.warning("Failed to list events for %s: %s", event_type, exc)
            continue

        for key in keys:
            try:
                # Check if already indexed
                if is_already_indexed(dynamo, key):
                    total_skipped += 1
                    continue

                # Fetch event from S3
                event = s3.get_event(key)

                # Convert to text
                text = event_to_text(event)

                if args.dry_run:
                    logger.info("  [DRY RUN] Would index: %s", key)
                    logger.info("    Text: %s", text[:120])
                    total_indexed += 1
                    continue

                # Build metadata
                payload = event.get("payload", {})
                metadata: dict[str, Any] = {
                    "event_type": event.get("event_type", ""),
                    "event_id": event.get("event_id", ""),
                    "s3_key": key,
                    "timestamp": event.get("timestamp", ""),
                }
                service = payload.get("service_name", payload.get("service", ""))
                if service:
                    metadata["service_name"] = service

                # Chunk if needed and embed
                chunks = chunk_text(text)
                for i, chunk in enumerate(chunks):
                    doc_id = f"{key}:chunk-{i}" if len(chunks) > 1 else key
                    vs.embed_and_store(doc_id, chunk, metadata)

                # Mark as indexed
                mark_as_indexed(dynamo, key)
                total_indexed += 1

            except Exception as exc:
                logger.warning("Failed to index %s: %s", key, exc)
                total_errors += 1

    # Print summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("  Indexed: %d events", total_indexed)
    logger.info("  Skipped (already indexed): %d", total_skipped)
    logger.info("  Errors: %d", total_errors)
    logger.info("  Collection size: %d documents", vs.get_count())
    logger.info("=" * 60)

    # NOTE: To run this on a schedule, set up an EventBridge rule:
    #   Rule: Daily at midnight UTC
    #   Target: Lambda function running this script
    #   See scripts/deploy_aws.py for EventBridge setup


if __name__ == "__main__":
    main()
