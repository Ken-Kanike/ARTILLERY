"""
Artilery — Ops Agent Unit Tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.ops.agent import OpsState, compile, run_ops


class TestOpsAgentGraph:
    def test_graph_compiles(self) -> None:
        app = compile()
        assert app is not None


class TestOpsAgentIntegration:
    @pytest.fixture
    def deploy_failed_event(self) -> dict:
        return {
            "event_type": "deploy.failed",
            "payload": {
                "deployment_id": "d-TEST001",
                "service_name": "PaymentService",
                "error_message": "Health check failed on port 8080",
                "jira_ticket_key": "PROJ-123",
            },
        }

    @patch("shared.s3_utils.S3Client")
    @patch("agents.ops.tools.fetch_cloudwatch_logs", new_callable=AsyncMock)
    @patch("agents.ops.tools.diagnose_with_bedrock", new_callable=AsyncMock)
    @patch("agents.ops.tools.notify_ops_channel", new_callable=AsyncMock)
    @patch("agents.ops.tools.notify_developer_failure", new_callable=AsyncMock)
    def test_failure_diagnosis_flow(self, mock_dev_notify, mock_notify, mock_diagnose, mock_logs, mock_s3_cls, deploy_failed_event) -> None:
        mock_logs.return_value = "ERROR: Health check failed\nERROR: Connection refused"
        mock_diagnose.return_value = {
            "root_cause": "Application failed to bind to port 8080",
            "remediation": "Check port configuration",
            "confidence": 0.9,
            "auto_fixable": True,
            "severity": "high",
            "action_items": ["Check port binding", "Review health check config"],
        }
        mock_notify.return_value = True
        mock_dev_notify.return_value = True
        mock_s3_cls.return_value = MagicMock()
        mock_s3_cls.return_value.store_deployment_log.return_value = "logs/test.gz"

        result = asyncio.run(run_ops(deploy_failed_event))
        assert result["diagnosis"]["confidence"] == 0.9
        assert result["slack_notified"] is True
        mock_diagnose.assert_called_once()
