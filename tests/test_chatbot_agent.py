"""
Artilery — Chatbot Agent Unit Tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.chatbot.agent import ChatState, classify_intent, compile, ask


class TestIntentClassification:
    def test_team_query(self) -> None:
        assert classify_intent("Who owns the PaymentService?") == "service_owner"

    def test_service_query(self) -> None:
        assert classify_intent("What are the service dependencies?") == "general"

    def test_deployment_query(self) -> None:
        assert classify_intent("What deployments failed today?") == "deployment_history"

    def test_pr_query(self) -> None:
        assert classify_intent("Show me the pull request #42") == "pr_status"

    def test_triage_query(self) -> None:
        assert classify_intent("Show me recent bugs") == "recent_issues"

    def test_general_fallback(self) -> None:
        assert classify_intent("Hello, how are you?") == "general"


class TestChatbotGraph:
    def test_graph_compiles(self) -> None:
        app = compile()
        assert app is not None


class TestChatbotIntegration:
    @patch("agents.chatbot.retrievers.retrieve_from_neo4j", new_callable=AsyncMock)
    @patch("agents.chatbot.retrievers.retrieve_from_dynamo", new_callable=AsyncMock)
    @patch("agents.chatbot.retrievers.retrieve_from_vector_store", new_callable=AsyncMock)
    @patch("agents.chatbot.tools.generate_answer", new_callable=AsyncMock)
    @patch("agents.chatbot.agent.DynamoClient")
    def test_ask_returns_answer(self, mock_dynamo_cls, mock_gen, mock_vector, mock_dynamo_ret, mock_neo4j) -> None:
        mock_neo4j.return_value = "Alice Chen is on the Backend team."
        mock_dynamo_ret.return_value = ""
        mock_vector.return_value = ""
        mock_gen.return_value = ("Alice Chen owns the Backend team.", ["Neo4j"])
        mock_dynamo_cls.return_value = MagicMock()

        result = asyncio.run(ask("Who is on the backend team?", session_id="test"))
        assert "Alice" in result["answer"]
        assert result["intent"] == "team_info"
