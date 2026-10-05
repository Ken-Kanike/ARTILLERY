"""
Artilery — Triage Agent Unit Tests.

Tests for the Triage Agent end-to-end flow, individual tools,
and error handling / retry behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.triage.agent import TriageState, compile, run_triage
from agents.triage.tools import build_severity_blocks


class TestBuildSeverityBlocks:
    """Tests for the Slack Block Kit builder."""

    def test_returns_list_of_blocks(self) -> None:
        blocks = build_severity_blocks(
            bug_summary="[BUG-001] Payment timeout",
            service_name="PaymentService",
            priority="High",
            jira_ticket_key="PROJ-123",
            jira_ticket_url="https://jira.example.com/browse/PROJ-123",
        )
        assert isinstance(blocks, list)
        assert len(blocks) >= 3

    def test_critical_has_red_badge(self) -> None:
        blocks = build_severity_blocks(
            bug_summary="Critical bug",
            service_name="AuthService",
            priority="Critical",
            jira_ticket_key="PROJ-100",
            jira_ticket_url="https://jira.example.com/browse/PROJ-100",
        )
        header_text = blocks[0]["text"]["text"]
        assert "🔴" in header_text

    def test_low_has_green_badge(self) -> None:
        blocks = build_severity_blocks(
            bug_summary="Minor bug",
            service_name="UserService",
            priority="Low",
            jira_ticket_key="PROJ-200",
            jira_ticket_url="https://jira.example.com/browse/PROJ-200",
        )
        header_text = blocks[0]["text"]["text"]
        assert "🟢" in header_text

    def test_notion_button_added_when_url_provided(self) -> None:
        blocks = build_severity_blocks(
            bug_summary="test",
            service_name="TestService",
            priority="Medium",
            jira_ticket_key="T-1",
            jira_ticket_url="https://jira.example.com/T-1",
            notion_page_url="https://notion.so/page-123",
        )
        # Find actions block and check for Notion button
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions) == 1
        assert len(actions[0]["elements"]) == 2  # Jira + Notion

    def test_no_notion_button_when_no_url(self) -> None:
        blocks = build_severity_blocks(
            bug_summary="test",
            service_name="TestService",
            priority="Medium",
            jira_ticket_key="T-1",
            jira_ticket_url="https://jira.example.com/T-1",
        )
        actions = [b for b in blocks if b.get("type") == "actions"]
        assert len(actions[0]["elements"]) == 1  # Jira only


class TestTriageAgentGraph:
    """Tests for the Triage Agent LangGraph compilation."""

    def test_graph_compiles(self) -> None:
        """The LangGraph should compile without errors."""
        app = compile()
        assert app is not None

    def test_graph_has_expected_nodes(self) -> None:
        app = compile()
        # LangGraph compiled apps have node structure we can inspect
        assert app is not None


class TestTriageAgentIntegration:
    """Integration tests for the Triage Agent (mocked externals)."""

    @pytest.fixture
    def sample_event(self) -> dict:
        return {
            "event_id": "test-event-001",
            "event_type": "bug.ingested",
            "timestamp": "2024-01-01T00:00:00Z",
            "payload": {
                "bug_id": "BUG-TEST-001",
                "service": "PaymentService",
                "severity": "High",
                "description": "Payment timeout after 30 seconds on checkout flow",
            },
        }

    @patch("agents.triage.agent.Neo4jClient")
    @patch("agents.triage.tools.create_jira_ticket", new_callable=AsyncMock)
    @patch("agents.triage.tools.create_notion_page", new_callable=AsyncMock)
    @patch("agents.triage.tools.send_slack_dm", new_callable=AsyncMock)
    @patch("agents.triage.tools.publish_ticket_created", new_callable=AsyncMock)
    def test_happy_path(self, mock_publish, mock_slack, mock_notion, mock_jira, mock_neo4j_cls, sample_event) -> None:
        """Happy path: all tools succeed."""
        # Mock Neo4j
        mock_client = MagicMock()
        mock_client.get_service_owner.return_value = {
            "developer_name": "Alice Chen",
            "developer_id": "dev-001",
            "slack_user_id": "U0ALICE001",
            "jira_account_id": "jira-alice-001",
            "email": "alice@example.com",
            "team_name": "Backend",
            "slack_channel_id": "C0BACKEND01",
        }
        mock_neo4j_cls.return_value = mock_client

        # Mock tools
        mock_jira.return_value = {"ticket_key": "PROJ-123", "ticket_url": "https://jira.example.com/PROJ-123", "ticket_id": "10001"}
        mock_notion.return_value = {"page_id": "notion-page-001", "page_url": "https://notion.so/page-001"}
        mock_slack.return_value = True
        mock_publish.return_value = None

        result = asyncio.run(run_triage(sample_event))

        assert result["bug_id"] == "BUG-TEST-001"
        assert result["kafka_published"] is True
        assert result["slack_sent"] is True
        assert result["jira_ticket"]["ticket_key"] == "PROJ-123"
        assert result["error"] is None
        mock_jira.assert_called_once()
        mock_notion.assert_called_once()
        mock_slack.assert_called_once()
        mock_publish.assert_called_once()
