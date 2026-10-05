"""
Artilery Shared S3 Utilities — Event Log Storage.

Provides an S3Client class for storing structured event logs,
agent decision trails, and deployment artifacts in Amazon S3.
Used by the Ops Agent (deployment logs), Triage Agent (audit trails),
and Chatbot Agent (RAG document retrieval).
"""

from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.s3")


class S3Client:
    """S3 client for event log storage and retrieval."""

    def __init__(self, bucket: Optional[str] = None) -> None:
        settings = get_settings()
        self._bucket = bucket or settings.S3_BUCKET_NAME or "artilery-event-logs"
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3
            settings = get_settings()

            kwargs: dict[str, Any] = {"region_name": settings.AWS_REGION}

            # Local mode: connect to LocalStack
            endpoint = settings.S3_ENDPOINT_URL
            if settings.is_local and not endpoint:
                endpoint = "http://localhost:4566"

            if endpoint:
                kwargs["endpoint_url"] = endpoint
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID or "local"
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY or "local"
            else:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            self._client = boto3.client("s3", **kwargs)

            # Create bucket if local mode (LocalStack)
            if settings.is_local:
                try:
                    self._client.head_bucket(Bucket=self._bucket)
                except Exception:
                    try:
                        self._client.create_bucket(Bucket=self._bucket)
                        logger.info("S3 | Created local bucket: %s", self._bucket)
                    except Exception:
                        pass  # Bucket may already exist
        return self._client

    # ── Event Logging ────────────────────────────────────────────────────

    def store_event(self, event_type: str, event_id: str, payload: dict[str, Any]) -> str:
        """Store an event as a JSON file in S3.

        Path: events/{event_type}/{YYYY}/{MM}/{DD}/{event_id}.json.gz
        """
        now = datetime.now(timezone.utc)
        key = f"events/{event_type}/{now.strftime('%Y/%m/%d')}/{event_id}.json.gz"

        document = {
            "event_id": event_id,
            "event_type": event_type,
            "timestamp": now.isoformat(),
            "payload": payload,
        }

        body = gzip.compress(json.dumps(document, default=str).encode("utf-8"))

        self._get_client().put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ContentEncoding="gzip",
            Metadata={"event_type": event_type, "event_id": event_id},
        )
        logger.info("S3 | Event stored | key=%s | size=%d bytes", key, len(body))
        return key

    def store_agent_trace(self, agent_name: str, trace_id: str, trace: dict[str, Any]) -> str:
        """Store an agent decision trace for auditing."""
        now = datetime.now(timezone.utc)
        key = f"traces/{agent_name}/{now.strftime('%Y/%m/%d')}/{trace_id}.json.gz"

        body = gzip.compress(json.dumps(trace, default=str).encode("utf-8"))
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ContentEncoding="gzip",
        )
        logger.info("S3 | Agent trace stored | key=%s", key)
        return key

    def store_deployment_log(self, deployment_id: str, log_content: str) -> str:
        """Store raw deployment logs."""
        now = datetime.now(timezone.utc)
        key = f"deployments/{now.strftime('%Y/%m/%d')}/{deployment_id}.log.gz"

        body = gzip.compress(log_content.encode("utf-8"))
        self._get_client().put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="text/plain",
            ContentEncoding="gzip",
        )
        logger.info("S3 | Deployment log stored | key=%s", key)
        return key

    # ── Retrieval ────────────────────────────────────────────────────────

    def get_event(self, key: str) -> dict[str, Any]:
        """Retrieve and decompress an event from S3."""
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        compressed = response["Body"].read()
        return json.loads(gzip.decompress(compressed))

    def list_events(self, event_type: str, date: Optional[str] = None, limit: int = 50) -> list[str]:
        """List event keys by type and optional date (YYYY/MM/DD)."""
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y/%m/%d")
        prefix = f"events/{event_type}/{date}/"

        response = self._get_client().list_objects_v2(Bucket=self._bucket, Prefix=prefix, MaxKeys=limit)
        return [obj["Key"] for obj in response.get("Contents", [])]

    def list_recent_events(self, event_type: str, days: int = 7) -> list[str]:
        """List recent events across multiple days."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        all_keys: list[str] = []
        for i in range(days):
            date = (now - timedelta(days=i)).strftime("%Y/%m/%d")
            all_keys.extend(self.list_events(event_type, date))
        return all_keys

    def get_deployment_log(self, key: str) -> str:
        """Retrieve and decompress a deployment log."""
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        return gzip.decompress(response["Body"].read()).decode("utf-8")

    def batch_get_events(self, keys: list[str]) -> list[dict[str, Any]]:
        """Retrieve multiple events by key."""
        results = []
        for key in keys:
            try:
                results.append(self.get_event(key))
            except Exception as exc:
                logger.warning("S3 | Failed to get event | key=%s | error=%s", key, exc)
        return results
