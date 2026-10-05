"""
Artilery API — GitHub Webhook Handler.

POST /webhook/github
- Validates HMAC-SHA256 signature
- Parses PR events (opened, synchronize, closed+merged, review submitted)
- Publishes Kafka events: pr.opened, pr.reviewed, pr.approved
- Returns 200 immediately (never awaits agent processing)
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Request

from shared.config import get_settings
from shared.kafka_utils import KaosProducer

logger = logging.getLogger("artilery.api.github")

router = APIRouter()

JIRA_KEY_PATTERN = re.compile(r"([A-Z]+-\d+)")


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature (timing-safe)."""
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _extract_jira_key(branch_name: str) -> Optional[str]:
    """Extract Jira ticket key from branch name (e.g. feat/PROJ-123-fix → PROJ-123)."""
    match = JIRA_KEY_PATTERN.search(branch_name)
    return match.group(1) if match else None


# Known services in the organization (matches Neo4j seed data)
KNOWN_SERVICES = ["PaymentService", "AuthService", "NotificationService", "APIGateway", "UserService"]


def _infer_service_name(repo_name: str, pr_title: str = "", branch_name: str = "") -> str:
    """Infer service name from PR context — checks title, branch, then repo name."""
    search_text = f"{pr_title} {branch_name}".lower()
    for service in KNOWN_SERVICES:
        if service.lower() in search_text:
            return service

    name = repo_name.split("/")[-1] if "/" in repo_name else repo_name
    parts = name.replace("_", "-").split("-")
    return "".join(p.capitalize() for p in parts)


def _extract_pr_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract standardized PR metadata from a GitHub webhook payload."""
    pr = payload.get("pull_request", {})
    repo = payload.get("repository", {})
    head = pr.get("head", {})
    base = pr.get("base", {})
    user = pr.get("user", {})

    branch_name = head.get("ref", "")
    pr_title = pr.get("title", "")

    return {
        "pr_number": pr.get("number"),
        "pr_title": pr_title,
        "pr_url": pr.get("html_url", ""),
        "pr_author": {"login": user.get("login", ""), "name": user.get("name", user.get("login", ""))},
        "repo_name": repo.get("name", ""),
        "repo_full_name": repo.get("full_name", ""),
        "base_branch": base.get("ref", ""),
        "head_branch": branch_name,
        "files_changed": [],
        "service_name": _infer_service_name(repo.get("name", ""), pr_title=pr_title, branch_name=branch_name),
        "jira_ticket_key": _extract_jira_key(branch_name),
    }


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
) -> dict[str, str]:
    """Receive and process GitHub webhook events."""
    settings = get_settings()
    body = await request.body()

    # ── Signature Validation ─────────────────────────────────────────
    if settings.GITHUB_WEBHOOK_SECRET:
        if not x_hub_signature_256:
            logger.warning("WEBHOOK | Missing signature header")
            raise HTTPException(status_code=401, detail="Missing signature")
        if not _verify_signature(body, x_hub_signature_256, settings.GITHUB_WEBHOOK_SECRET):
            logger.warning("WEBHOOK | Invalid signature")
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    action = payload.get("action", "")

    logger.info("WEBHOOK | event=%s | action=%s", x_github_event, action)

    try:
        if x_github_event == "pull_request":
            metadata = _extract_pr_metadata(payload)
            pr_key = str(metadata["pr_number"])

            if action in ("opened", "synchronize"):
                with KaosProducer() as producer:
                    producer.publish("pr.opened", key=pr_key, value=metadata)
                logger.info("WEBHOOK | Published pr.opened | pr=#%s", pr_key)

            elif action == "closed" and payload.get("pull_request", {}).get("merged"):
                with KaosProducer() as producer:
                    producer.publish("pr.approved", key=pr_key, value=metadata)
                logger.info("WEBHOOK | Published pr.approved (merged) | pr=#%s", pr_key)

        elif x_github_event == "pull_request_review":
            if action == "submitted":
                review = payload.get("review", {})
                state = review.get("state", "")
                metadata = _extract_pr_metadata(payload)
                metadata["review_state"] = state
                metadata["review_comment"] = review.get("body", "")
                metadata["reviewer"] = review.get("user", {}).get("login", "")
                pr_key = str(metadata["pr_number"])

                if state == "approved":
                    with KaosProducer() as producer:
                        producer.publish("pr.approved", key=pr_key, value=metadata)
                    logger.info("WEBHOOK | Published pr.approved | pr=#%s", pr_key)

                elif state == "changes_requested":
                    metadata["changes_requested"] = True
                    with KaosProducer() as producer:
                        producer.publish("pr.reviewed", key=pr_key, value=metadata)
                    logger.info("WEBHOOK | Published pr.reviewed (changes_requested) | pr=#%s", pr_key)

                # state == "commented" → ignore

        elif x_github_event == "ping":
            logger.info("WEBHOOK | Ping received — webhook configured correctly")

    except Exception as exc:
        # Always return 200 to GitHub; log the error separately
        logger.error("WEBHOOK | Processing failed | error=%s", exc)

    return {"status": "accepted"}
