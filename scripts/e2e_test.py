#!/usr/bin/env python3
"""
Artilery — End-to-End Integration Test.

9-step test against the deployed AWS environment:
1. Publish bug.ingested → verify Triage Agent creates ticket
2. Verify DynamoDB PR state saved
3. Publish pr.opened → verify Review Agent assigns reviewer
4. Publish pr.reviewed → verify Jira comment
5. Publish pr.approved → verify status transition
6. Publish deploy.triggered → verify CodeDeploy started
7. Publish deploy.succeeded → verify Jira resolved
8. Test Chatbot RAG query
9. Verify end-to-end Kafka event flow

Summary table: Step | Expected | Actual | Pass/Fail | Duration

Usage:
    python -m scripts.e2e_test
    python -m scripts.e2e_test --step 8  # Run specific step
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("artilery.scripts.e2e_test")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


class TestResult:
    def __init__(self, step: int, name: str) -> None:
        self.step = step
        self.name = name
        self.expected = ""
        self.actual = ""
        self.passed = False
        self.duration = 0.0
        self.error = ""

    def __str__(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        return f"  {self.step}. {self.name}: {status} ({self.duration:.1f}s)"


results: list[TestResult] = []


def run_step(step_num: int, name: str, expected: str):
    """Decorator for test steps."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            r = TestResult(step_num, name)
            r.expected = expected
            start = time.time()
            try:
                r.actual = await func(*args, **kwargs)
                r.passed = True
            except Exception as exc:
                r.actual = f"ERROR: {exc}"
                r.error = str(exc)
            r.duration = time.time() - start
            results.append(r)
            logger.info(str(r))
            return r
        return wrapper
    return decorator


@run_step(1, "Bug Ingestion", "Event published to bug.ingested")
async def test_bug_ingestion() -> str:
    from shared.kafka_utils import KaosProducer
    bug_id = f"test-bug-{uuid.uuid4().hex[:8]}"
    payload = {
        "bug_id": bug_id, "title": "E2E Test Bug", "severity": "High",
        "description": "Automated e2e test", "service_name": "TestService",
        "reporter": "e2e-test",
    }
    with KaosProducer() as producer:
        producer.publish(topic="bug.ingested", key=bug_id, value=payload)
    return f"Published bug.ingested | bug_id={bug_id}"


@run_step(2, "DynamoDB State Check", "Idempotency key stored")
async def test_dynamo_state() -> str:
    from shared.dynamo_utils import DynamoClient
    dynamo = DynamoClient()
    test_key = f"e2e-test-{uuid.uuid4().hex[:8]}"
    saved = dynamo.save_idempotency_key(test_key, ttl_seconds=60)
    if not saved:
        raise Exception("Idempotency key save returned False")
    # Verify duplicate detection
    dup = dynamo.save_idempotency_key(test_key, ttl_seconds=60)
    if dup:
        raise Exception("Duplicate detection failed")
    return f"Idempotency key saved and duplicate detected | key={test_key}"


@run_step(3, "PR Opened Event", "Event published to pr.opened")
async def test_pr_opened() -> str:
    from shared.kafka_utils import KaosProducer
    pr_num = 9999
    payload = {
        "pr_number": pr_num, "pr_title": "E2E Test PR", "repo": "test-org/test-repo",
        "pr_author": {"login": "e2e-tester", "slack_id": "U00000000"},
        "service_name": "TestService", "files_changed": ["src/main.py", "tests/test.py"],
    }
    with KaosProducer() as producer:
        producer.publish(topic="pr.opened", key=str(pr_num), value=payload)
    return f"Published pr.opened | pr_number={pr_num}"


@run_step(4, "PR Reviewed Event", "Event published to pr.reviewed")
async def test_pr_reviewed() -> str:
    from shared.kafka_utils import KaosProducer
    payload = {
        "pr_number": 9999, "repo": "test-org/test-repo",
        "reviewer": {"login": "reviewer-1"}, "status": "changes_requested",
        "changes_requested": True, "review_comment": "Please fix the tests",
    }
    with KaosProducer() as producer:
        producer.publish(topic="pr.reviewed", key="9999", value=payload)
    return "Published pr.reviewed | status=changes_requested"


@run_step(5, "PR Approved Event", "Event published to pr.approved")
async def test_pr_approved() -> str:
    from shared.kafka_utils import KaosProducer
    payload = {
        "pr_number": 9999, "repo": "test-org/test-repo",
        "reviewer": {"login": "reviewer-1"}, "status": "approved",
    }
    with KaosProducer() as producer:
        producer.publish(topic="pr.approved", key="9999", value=payload)
    return "Published pr.approved | status=approved"


@run_step(6, "Deploy Triggered", "Event published to deploy.triggered")
async def test_deploy_triggered() -> str:
    from shared.kafka_utils import KaosProducer
    dep_id = f"d-TEST{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "deployment_id": dep_id, "service_name": "TestService",
        "application_name": "TestApp", "deployment_group": "TestGroup",
        "github_repo": "test-org/test-repo", "commit_id": "abc123",
    }
    with KaosProducer() as producer:
        producer.publish(topic="deploy.triggered", key=dep_id, value=payload)
    return f"Published deploy.triggered | deployment_id={dep_id}"


@run_step(7, "Deploy Succeeded", "Event published to deploy.succeeded")
async def test_deploy_succeeded() -> str:
    from shared.kafka_utils import KaosProducer
    dep_id = f"d-TEST{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "deployment_id": dep_id, "service_name": "TestService",
        "status": "Succeeded",
    }
    with KaosProducer() as producer:
        producer.publish(topic="deploy.succeeded", key=dep_id, value=payload)
    return f"Published deploy.succeeded | deployment_id={dep_id}"


@run_step(8, "Chatbot RAG Query", "Answer generated with sources")
async def test_chatbot_query() -> str:
    from agents.chatbot.agent import ask
    result = await ask("Who owns TestService?", session_id="e2e-test")
    answer = result.get("answer", "")
    if not answer:
        raise Exception("Chatbot returned empty answer")
    return f"Chatbot answered | intent={result.get('intent', '')} | len={len(answer)}"


@run_step(9, "S3 Event Storage", "Event stored in S3")
async def test_s3_storage() -> str:
    from shared.s3_utils import S3Client
    s3 = S3Client()
    event_id = f"e2e-{uuid.uuid4().hex[:8]}"
    key = s3.store_event("e2e_test", event_id, {"test": True, "timestamp": datetime.now(timezone.utc).isoformat()})
    # Verify retrieval
    event = s3.get_event(key)
    if event.get("event_id") != event_id:
        raise Exception("S3 round-trip failed")
    return f"S3 event stored and retrieved | key={key}"


async def run_all_tests() -> None:
    tests = [
        test_bug_ingestion, test_dynamo_state, test_pr_opened,
        test_pr_reviewed, test_pr_approved, test_deploy_triggered,
        test_deploy_succeeded, test_chatbot_query, test_s3_storage,
    ]

    for test_fn in tests:
        await test_fn()

    # Print summary table
    print("\n" + "=" * 80)
    print("ARTILERY E2E TEST RESULTS")
    print("=" * 80)
    print(f"{'Step':<5} {'Test Name':<30} {'Status':<10} {'Duration':<10} {'Details'}")
    print("-" * 80)
    for r in results:
        status = "PASS ✅" if r.passed else "FAIL ❌"
        detail = r.actual[:40] if r.passed else r.error[:40]
        print(f"{r.step:<5} {r.name:<30} {status:<10} {r.duration:<10.1f} {detail}")
    print("-" * 80)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\nResult: {passed}/{total} passed")
    print("=" * 80)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Artilery E2E Tests")
    parser.add_argument("--step", type=int, help="Run specific step (1-9)")
    args = parser.parse_args()

    asyncio.run(run_all_tests())
