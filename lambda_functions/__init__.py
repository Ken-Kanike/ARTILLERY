"""
Artilery — CloudWatch → Kafka Bridge (AWS Lambda).

Receives CodeDeploy state change events via CloudWatch Events / EventBridge,
transforms them into Artilery Kafka events, and publishes:
- deploy.triggered  — Deployment started
- deploy.failed     — Deployment failed
- deploy.succeeded  — Deployment succeeded

Deployed as an AWS Lambda function with Mangum adapter.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("artilery.lambda.cloudwatch_bridge")
logging.basicConfig(level=logging.INFO)

# CodeDeploy status → Kafka topic mapping
STATUS_TO_TOPIC: dict[str, str] = {
    "CREATED": "deploy.triggered",
    "IN_PROGRESS": "deploy.triggered",
    "SUCCEEDED": "deploy.succeeded",
    "FAILED": "deploy.failed",
    "STOPPED": "deploy.failed",
    "READY": "deploy.triggered",
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """AWS Lambda handler for CloudWatch/EventBridge events.

    Expected event format (from CodeDeploy state change):
    {
        "source": "aws.codedeploy",
        "detail-type": "CodeDeploy Deployment State-change Notification",
        "detail": {
            "deploymentId": "d-ABC123",
            "applicationName": "my-app",
            "deploymentGroupName": "my-app-group",
            "status": "FAILED",
            "errorInformation": "..."
        }
    }
    """
    logger.info("CloudWatch bridge invoked | event_source=%s", event.get("source", "unknown"))

    detail = event.get("detail", {})
    status = detail.get("status", "")
    deployment_id = detail.get("deploymentId", "")
    app_name = detail.get("applicationName", "")

    topic = STATUS_TO_TOPIC.get(status)
    if not topic:
        logger.warning("Unknown CodeDeploy status: %s", status)
        return {"statusCode": 200, "body": "ignored"}

    # Transform to Artilery event payload
    payload = {
        "deployment_id": deployment_id,
        "service_name": _app_name_to_service(app_name),
        "status": status.lower(),
        "error_message": detail.get("errorInformation", ""),
        "deployment_group": detail.get("deploymentGroupName", ""),
        "region": event.get("region", ""),
    }

    try:
        from shared.kafka_utils import KaosProducer

        with KaosProducer() as producer:
            producer.publish(topic=topic, key=deployment_id, value=payload)

        logger.info("Published %s | deployment=%s | service=%s", topic, deployment_id, payload["service_name"])
        return {"statusCode": 200, "body": json.dumps({"topic": topic, "deployment_id": deployment_id})}

    except Exception as exc:
        logger.error("Failed to publish %s | error=%s", topic, exc)
        return {"statusCode": 500, "body": json.dumps({"error": str(exc)})}


def _app_name_to_service(app_name: str) -> str:
    """Convert CodeDeploy app name to service name."""
    # e.g., "artilery-paymentservice" → "PaymentService"
    name = app_name.replace("artilery-", "").replace("kaos-", "")
    parts = name.replace("_", "-").split("-")
    return "".join(p.capitalize() for p in parts)
