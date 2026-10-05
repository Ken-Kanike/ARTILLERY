"""
Artilery Shared DynamoDB Utilities — State Management.

Provides a DynamoClient class for managing PR state, agent checkpoints,
idempotency keys, and chat history in AWS DynamoDB.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.dynamo")


class DynamoClient:
    """AWS DynamoDB client for Artilery state management."""

    def __init__(self, table_name: Optional[str] = None) -> None:
        settings = get_settings()
        self._table_name = table_name or settings.DYNAMODB_TABLE_NAME or "artilery_state"
        self._resource: Any = None
        self._table: Any = None

    def _get_table(self) -> Any:
        if self._table is None:
            import boto3
            settings = get_settings()

            kwargs: dict[str, Any] = {"region_name": settings.AWS_REGION}

            # Local mode: connect to Docker DynamoDB
            endpoint = settings.DYNAMODB_ENDPOINT_URL
            if settings.is_local and not endpoint:
                endpoint = "http://localhost:8000"

            if endpoint:
                kwargs["endpoint_url"] = endpoint
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID or "local"
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY or "local"
            else:
                kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY

            self._resource = boto3.resource("dynamodb", **kwargs)
            self._table = self._resource.Table(self._table_name)
        return self._table

    # ── PR State ─────────────────────────────────────────────────────────

    def _pr_key(self, pr_number: int, repo: str) -> dict[str, str]:
        return {"pk": f"pr#{repo}#{pr_number}", "sk": "metadata"}

    def get_pr_state(self, pr_number: int, repo: str) -> Optional[dict[str, Any]]:
        """Retrieve PR state from DynamoDB."""
        table = self._get_table()
        response = table.get_item(Key=self._pr_key(pr_number, repo))
        item = response.get("Item")
        if item:
            logger.info("DYNAMO | PR state retrieved | pr=%s/%d", repo, pr_number)
        return item

    def save_pr_state(self, pr_number: int, repo: str, state: dict[str, Any]) -> None:
        """Save PR state to DynamoDB."""
        table = self._get_table()
        now = datetime.now(timezone.utc).isoformat()
        item = {
            **self._pr_key(pr_number, repo),
            "pr_number": pr_number,
            "repo": repo,
            "created_at": now,
            "updated_at": now,
            **{k: v for k, v in state.items() if v is not None},
        }
        table.put_item(Item=item)
        logger.info("DYNAMO | PR state saved | pr=%s/%d", repo, pr_number)

    def update_pr_state(self, pr_number: int, repo: str, updates: dict[str, Any]) -> None:
        """Update specific fields in PR state."""
        table = self._get_table()
        now = datetime.now(timezone.utc).isoformat()
        updates["updated_at"] = now

        update_expr_parts = []
        expr_names = {}
        expr_values = {}
        for i, (key, value) in enumerate(updates.items()):
            attr_name = f"#k{i}"
            attr_value = f":v{i}"
            update_expr_parts.append(f"{attr_name} = {attr_value}")
            expr_names[attr_name] = key
            expr_values[attr_value] = value

        table.update_item(
            Key=self._pr_key(pr_number, repo),
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )
        logger.info("DYNAMO | PR state updated | pr=%s/%d | fields=%s", repo, pr_number, list(updates.keys()))

    # ── Agent Checkpoints ────────────────────────────────────────────────

    def get_agent_checkpoint(self, checkpoint_id: str) -> Optional[dict[str, Any]]:
        table = self._get_table()
        response = table.get_item(Key={"pk": f"checkpoint#{checkpoint_id}", "sk": "data"})
        return response.get("Item")

    def save_agent_checkpoint(self, checkpoint_id: str, data: dict[str, Any]) -> None:
        table = self._get_table()
        table.put_item(Item={
            "pk": f"checkpoint#{checkpoint_id}",
            "sk": "data",
            "checkpoint_id": checkpoint_id,
            "data": data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    # ── Idempotency ──────────────────────────────────────────────────────

    def save_idempotency_key(self, key: str, ttl_seconds: int = 86400) -> bool:
        """Save an idempotency key. Returns False if key already exists (duplicate)."""
        table = self._get_table()
        ttl = int(time.time()) + ttl_seconds
        try:
            table.put_item(
                Item={"pk": f"idempotency#{key}", "sk": "lock", "ttl": ttl},
                ConditionExpression="attribute_not_exists(pk)",
            )
            logger.info("DYNAMO | Idempotency key saved | key=%s", key)
            return True
        except Exception as exc:
            if "ConditionalCheckFailedException" in str(type(exc).__name__):
                logger.info("DYNAMO | Duplicate event detected | key=%s", key)
                return False
            raise

    # ── Chat History ─────────────────────────────────────────────────────

    def save_chat_turn(self, session_id: str, role: str, content: str) -> None:
        table = self._get_table()
        now = datetime.now(timezone.utc).isoformat()
        table.put_item(Item={
            "pk": f"chat#{session_id}",
            "sk": now,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": now,
        })

    def get_chat_history(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        table = self._get_table()
        response = table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": f"chat#{session_id}"},
            ScanIndexForward=True,
            Limit=limit,
        )
        return response.get("Items", [])

    def delete_chat_history(self, session_id: str) -> None:
        table = self._get_table()
        items = self.get_chat_history(session_id, limit=1000)
        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        logger.info("DYNAMO | Chat history deleted | session=%s | items=%d", session_id, len(items))

    # ── Deployment State ─────────────────────────────────────────────────

    def save_deployment(self, deployment_id: str, data: dict[str, Any]) -> None:
        table = self._get_table()
        table.put_item(Item={
            "pk": f"deployment#{deployment_id}",
            "sk": "metadata",
            **data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_deployment(self, deployment_id: str) -> Optional[dict[str, Any]]:
        table = self._get_table()
        response = table.get_item(Key={"pk": f"deployment#{deployment_id}", "sk": "metadata"})
        return response.get("Item")
