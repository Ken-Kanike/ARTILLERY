"""
Artilery — Review Agent Unit Tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.review.agent import ReviewState, compile, run_review


class TestReviewAgentGraph:
    def test_graph_compiles(self) -> None:
        app = compile()
        assert app is not None


class TestReviewAgentIntegration:
    @pytest.fixture
    def pr_opened_event(self) -> dict:
        return {
            "event_type": "pr.opened",
            "payload": {
                "pr_number": 42,
                "pr_title": "Fix payment timeout",
                "pr_url": "https://github.com/company/payment-service/pull/42",
                "pr_author": {"login": "alice", "name": "Alice Chen"},
                "service_name": "PaymentService",
                "jira_ticket_key": "PROJ-123",
                "files_changed": ["src/payment.py", "tests/test_payment.py"],
            },
        }

    @patch("agents.review.agent.DynamoClient")
    @patch("agents.review.tools.assign_reviewer", new_callable=AsyncMock)
    @patch("agents.review.tools.notify_reviewer_slack", new_callable=AsyncMock)
    def test_pr_opened_assigns_reviewer(self, mock_notify, mock_assign, mock_dynamo_cls, pr_opened_event) -> None:
        mock_assign.return_value = {"reviewer_name": "Bob Martinez", "reviewer_slack_id": "U0BOB", "reviewer_jira_id": "jira-bob"}
        mock_notify.return_value = True
        mock_dynamo_cls.return_value = MagicMock()

        result = asyncio.run(run_review(pr_opened_event))
        assert result["reviewer"]["reviewer_name"] == "Bob Martinez"
        mock_assign.assert_called_once()
        mock_notify.assert_called_once()
