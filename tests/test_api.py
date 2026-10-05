"""
Artilery — GitHub Webhook API Tests.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


class TestHealthCheck:
    def test_health_returns_ok(self) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "artilery-api"


class TestGitHubWebhook:
    @pytest.fixture
    def pr_opened_payload(self) -> dict:
        return {
            "action": "opened",
            "pull_request": {
                "number": 42,
                "title": "Fix payment timeout",
                "html_url": "https://github.com/company/payment-service/pull/42",
                "user": {"login": "alice", "name": "Alice Chen"},
                "head": {"ref": "feat/PROJ-123-fix-timeout"},
                "base": {"ref": "main"},
            },
            "repository": {"name": "payment-service", "full_name": "company/payment-service"},
        }

    @patch("api.routers.github.get_settings")
    @patch("api.routers.github.KaosProducer")
    def test_pr_opened_publishes_event(self, mock_producer_cls, mock_settings, pr_opened_payload) -> None:
        mock_settings.return_value = MagicMock(GITHUB_WEBHOOK_SECRET=None)
        mock_producer = MagicMock()
        mock_producer.__enter__ = MagicMock(return_value=mock_producer)
        mock_producer.__exit__ = MagicMock(return_value=False)
        mock_producer_cls.return_value = mock_producer

        response = client.post(
            "/webhook/github",
            json=pr_opened_payload,
            headers={"X-GitHub-Event": "pull_request"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
        mock_producer.publish.assert_called_once()
        call_args = mock_producer.publish.call_args
        assert call_args.kwargs.get("topic", call_args[1].get("topic", call_args[0][0] if call_args[0] else "")) == "pr.opened" or "pr.opened" in str(call_args)

    @patch("api.routers.github.get_settings")
    def test_ping_event(self, mock_settings) -> None:
        mock_settings.return_value = MagicMock(GITHUB_WEBHOOK_SECRET=None)
        response = client.post("/webhook/github", json={"zen": "test"}, headers={"X-GitHub-Event": "ping"})
        assert response.status_code == 200

    @patch("api.routers.github.get_settings")
    def test_invalid_signature_rejected(self, mock_settings) -> None:
        mock_settings.return_value = MagicMock(GITHUB_WEBHOOK_SECRET="mysecret")
        response = client.post(
            "/webhook/github",
            json={"action": "opened"},
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": "sha256=invalid"},
        )
        assert response.status_code == 401

    @patch("api.routers.github.get_settings")
    def test_valid_signature_accepted(self, mock_settings) -> None:
        mock_settings.return_value = MagicMock(GITHUB_WEBHOOK_SECRET="mysecret")
        payload = json.dumps({"action": "opened", "pull_request": {"number": 1, "title": "test", "html_url": "", "user": {"login": "a"}, "head": {"ref": "main"}, "base": {"ref": "main"}}, "repository": {"name": "test", "full_name": "org/test"}}).encode()
        sig = "sha256=" + hmac.new(b"mysecret", payload, hashlib.sha256).hexdigest()

        response = client.post(
            "/webhook/github",
            content=payload,
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": sig, "Content-Type": "application/json"},
        )
        assert response.status_code == 200
