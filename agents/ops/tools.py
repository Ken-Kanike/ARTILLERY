"""
Artilery Ops Agent — Tool functions for LangGraph nodes.

Provides deployment, diagnosis, notification, and resolution tools:
- trigger_codedeploy: Start a new CodeDeploy deployment
- get_deployment_status: Poll CodeDeploy status
- fetch_cloudwatch_logs: Fetch deployment failure logs
- diagnose_with_bedrock: AI-powered failure analysis
- trigger_rollback: Stop failed deployment and redeploy
- retry_deployment: Create new deployment (with parent reference)
- notify_ops_channel: Alert the ops Slack channel
- notify_developer_failure: Rich Block Kit failure DM
- notify_success: Green Block Kit success DM
- escalate_to_lead: Escalation DM to team lead
- resolve_jira_ticket: Transition Jira to Resolved
- resolve_notion_page: Update Notion page to Resolved
- publish_deploy_event: Publish deployment events to Kafka
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.ops.tools")


# ── CodeDeploy Operations ───────────────────────────────────────────────────

async def trigger_codedeploy(
    application_name: str,
    deployment_group: str,
    github_repo: str,
    commit_id: str,
    pr_number: int,
) -> dict[str, Any]:
    """Start a new CodeDeploy deployment from GitHub.

    Returns dict with {deployment_id, deployment_url, status}.
    """
    settings = get_settings()
    logger.info("OPS | Triggering CodeDeploy | app=%s | group=%s | commit=%s", application_name, deployment_group, commit_id[:8])

    try:
        import boto3
        codedeploy = boto3.client(
            "codedeploy", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        response = codedeploy.create_deployment(
            applicationName=application_name,
            deploymentGroupName=deployment_group,
            revision={
                "revisionType": "GitHub",
                "gitHubLocation": {
                    "repository": github_repo,
                    "commitId": commit_id,
                },
            },
            description=f"Artilery automated deployment for PR #{pr_number}",
        )

        deployment_id = response["deploymentId"]
        deployment_url = f"https://{settings.AWS_REGION}.console.aws.amazon.com/codesuite/codedeploy/deployments/{deployment_id}"

        # Save metadata to DynamoDB
        from shared.dynamo_utils import DynamoClient
        dynamo = DynamoClient()
        dynamo.save_deployment(deployment_id, {
            "deployment_id": deployment_id,
            "application_name": application_name,
            "deployment_group": deployment_group,
            "github_repo": github_repo,
            "commit_id": commit_id,
            "pr_number": pr_number,
            "status": "triggered",
            "artilery_automated": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info("OPS | CodeDeploy triggered | deployment_id=%s", deployment_id)
        return {"deployment_id": deployment_id, "deployment_url": deployment_url, "status": "triggered"}

    except Exception as exc:
        logger.error("OPS | CodeDeploy trigger failed | error=%s", exc)
        raise


async def get_deployment_status(deployment_id: str) -> dict[str, Any]:
    """Poll CodeDeploy for current deployment status.

    Returns dict with {status, error_code, error_message, start_time, end_time}.
    """
    settings = get_settings()
    logger.info("OPS | Checking deployment status | id=%s", deployment_id)

    try:
        import boto3
        codedeploy = boto3.client(
            "codedeploy", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        response = codedeploy.get_deployment(deploymentId=deployment_id)
        info = response.get("deploymentInfo", {})
        error_info = info.get("errorInformation", {})

        return {
            "status": info.get("status", "Unknown"),
            "error_code": error_info.get("code", ""),
            "error_message": error_info.get("message", ""),
            "start_time": str(info.get("startTime", "")),
            "end_time": str(info.get("completeTime", "")),
        }

    except Exception as exc:
        logger.error("OPS | Status check failed | id=%s | error=%s", deployment_id, exc)
        return {"status": "Unknown", "error_code": "", "error_message": str(exc), "start_time": "", "end_time": ""}


async def fetch_cloudwatch_logs(deployment_id: str, service_name: str) -> str:
    """Fetch deployment failure logs from CloudWatch.

    Falls back to S3 if CloudWatch is not available.
    """
    settings = get_settings()
    logger.info("OPS | Fetching CloudWatch logs | deployment=%s", deployment_id)

    try:
        import boto3
        logs_client = boto3.client(
            "logs", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        log_group = f"/aws/codedeploy/{service_name}"
        response = logs_client.filter_log_events(
            logGroupName=log_group,
            filterPattern=deployment_id,
            limit=100,
        )

        events = response.get("events", [])
        if events:
            return "\n".join(e.get("message", "") for e in events)

        logger.info("OPS | No CloudWatch logs found, checking S3...")

    except Exception as exc:
        logger.warning("OPS | CloudWatch fetch failed | error=%s", exc)

    # Fallback: try S3
    try:
        from shared.s3_utils import S3Client
        s3 = S3Client()
        keys = s3.list_recent_events("deploy.failed", days=3)
        for key in keys:
            if deployment_id in key:
                return s3.get_deployment_log(key)
    except Exception as exc:
        logger.warning("OPS | S3 fallback failed | error=%s", exc)

    return f"No detailed logs found for deployment {deployment_id}"


async def diagnose_with_bedrock(
    deployment_id: str,
    error_logs: str,
    service_name: str,
    files_changed: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Use AWS Bedrock to diagnose a deployment failure.

    Returns dict with {root_cause, remediation/suggested_fix, confidence, auto_fixable/action_items, severity}.
    """
    settings = get_settings()
    logger.info("OPS | Diagnosing with Bedrock | deployment=%s | service=%s", deployment_id, service_name)

    # Truncate logs if too long (>3000 tokens ~12KB)
    if len(error_logs) > 12000:
        error_logs = error_logs[:6000] + "\n... [TRUNCATED] ...\n" + error_logs[-6000:]

    prompt = f"""You are a DevOps expert analyzing deployment failures. Be specific, concise, and actionable.

Service: {service_name}
Deployment ID: {deployment_id}
Files Changed: {json.dumps(files_changed or [])}

=== Error Logs ===
{error_logs}

Analyze the failure and respond in this exact JSON format:
{{
    "root_cause": "Brief description of the root cause",
    "suggested_fix": "Step-by-step fix instructions",
    "confidence": 0.85,
    "action_items": ["item 1", "item 2"],
    "severity": "high|medium|low",
    "auto_fixable": true
}}"""

    try:
        from shared.llm import invoke_llm
        import asyncio

        answer = await invoke_llm(
            prompt=prompt,
            system="You are a DevOps expert. Always respond with valid JSON.",
            max_tokens=1024,
            temperature=0.2,
        )

        # Log response (truncated)
        logger.info("OPS | LLM diagnosis received | len=%d", len(answer))

        # Parse JSON from response
        diagnosis = json.loads(answer)

        # Save diagnosis to S3
        try:
            from shared.s3_utils import S3Client
            s3 = S3Client()
            s3.store_event("diagnoses", deployment_id, diagnosis)
        except Exception:
            pass

        return {
            "root_cause": diagnosis.get("root_cause", "Unknown"),
            "remediation": diagnosis.get("suggested_fix", diagnosis.get("remediation", "")),
            "confidence": float(diagnosis.get("confidence", 0.5)),
            "auto_fixable": diagnosis.get("auto_fixable", False),
            "severity": diagnosis.get("severity", "medium"),
            "action_items": diagnosis.get("action_items", []),
        }

    except Exception as exc:
        logger.error("OPS | Bedrock diagnosis failed | error=%s", exc)
        return {
            "root_cause": f"Automated diagnosis unavailable: {str(exc)[:100]}",
            "remediation": "Please review the error logs manually.",
            "confidence": 0.0,
            "auto_fixable": False,
            "severity": "unknown",
            "action_items": ["Review error logs", "Check service health"],
        }


# ── Deployment Retry / Rollback ──────────────────────────────────────────────

async def trigger_rollback(deployment_id: str, service_name: str) -> dict[str, Any]:
    """Stop a failed deployment and trigger rollback."""
    settings = get_settings()
    logger.info("OPS | Triggering rollback | deployment=%s", deployment_id)

    try:
        import boto3
        codedeploy = boto3.client(
            "codedeploy", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        codedeploy.stop_deployment(deploymentId=deployment_id, autoRollbackEnabled=True)
        logger.info("OPS | Rollback triggered | deployment=%s", deployment_id)
        return {"status": "rollback_triggered", "deployment_id": deployment_id}

    except Exception as exc:
        logger.error("OPS | Rollback failed | error=%s", exc)
        return {"status": "rollback_failed", "error": str(exc)}


async def retry_deployment(
    deployment_id: str,
    application_name: str,
    deployment_group: str,
) -> dict[str, Any]:
    """Retry a failed deployment by creating a new one with the same config.

    Returns dict with {new_deployment_id, status}.
    """
    settings = get_settings()
    logger.info("OPS | Retrying deployment | parent=%s", deployment_id)

    try:
        import boto3
        codedeploy = boto3.client(
            "codedeploy", region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )

        # Get original deployment config
        original = codedeploy.get_deployment(deploymentId=deployment_id)
        original_info = original.get("deploymentInfo", {})

        response = codedeploy.create_deployment(
            applicationName=application_name,
            deploymentGroupName=deployment_group,
            revision=original_info.get("revision", {}),
            description=f"Artilery automated retry of {deployment_id}",
        )

        new_id = response["deploymentId"]

        # Save with parent reference in DynamoDB
        from shared.dynamo_utils import DynamoClient
        dynamo = DynamoClient()
        dynamo.save_deployment(new_id, {
            "deployment_id": new_id,
            "parent_deployment_id": deployment_id,
            "application_name": application_name,
            "deployment_group": deployment_group,
            "status": "retry_triggered",
            "artilery_automated": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        logger.info("OPS | Retry deployment created | new_id=%s | parent=%s", new_id, deployment_id)
        return {"new_deployment_id": new_id, "status": "retry_triggered"}

    except Exception as exc:
        logger.error("OPS | Retry failed | error=%s", exc)
        return {"new_deployment_id": "", "status": f"retry_failed: {exc}"}


# ── Notifications ────────────────────────────────────────────────────────────

async def notify_ops_channel(
    service_name: str,
    deployment_id: str,
    root_cause: str,
    remediation: str,
    jira_ticket_key: Optional[str] = None,
) -> bool:
    """Send deployment failure alert to the ops Slack channel."""
    settings = get_settings()
    channel = settings.DEFAULT_SLACK_CHANNEL
    logger.info("OPS | Alerting ops channel | deployment=%s", deployment_id)

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "🔴 Deployment Failed — Ops Alert"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Service:* `{service_name}`\n*Deployment:* `{deployment_id}`"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Root Cause:*\n{root_cause}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Suggested Fix:*\n{remediation}"}},
    ]
    if jira_ticket_key:
        jira_url = f"{settings.JIRA_URL}/browse/{jira_ticket_key}"
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": f"📋 {jira_ticket_key}"}, "url": jira_url, "style": "primary"},
        ]})

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=channel, text=f"Deployment {deployment_id} failed for {service_name}", blocks=blocks)
        return True
    except Exception as exc:
        logger.error("OPS | Slack alert failed | error=%s", exc)
        return False


async def notify_developer_failure(
    developer_slack_id: str,
    deployment_id: str,
    service_name: str,
    root_cause: str,
    suggested_fix: str,
    action_items: list[str],
    jira_ticket_key: Optional[str] = None,
) -> bool:
    """Send rich Block Kit failure DM to the developer."""
    settings = get_settings()
    logger.info("OPS | Notifying developer of failure | user=%s", developer_slack_id)

    action_text = "\n".join(f"{i+1}. {item}" for i, item in enumerate(action_items))
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "🔴 Deployment Failed — Action Required"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Deployment:* `{deployment_id}`\n*Service:* `{service_name}`"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*AI-Diagnosed Root Cause:*\n{root_cause}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Suggested Fix:*\n{suggested_fix}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Action Items:*\n{action_text}"}},
        {"type": "divider"},
    ]
    buttons = []
    if jira_ticket_key:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": f"📋 {jira_ticket_key}"}, "url": f"{settings.JIRA_URL}/browse/{jira_ticket_key}", "style": "primary"})
    buttons.append({"type": "button", "text": {"type": "plain_text", "text": "📄 View Logs"}, "url": f"https://{settings.AWS_REGION}.console.aws.amazon.com/codesuite/codedeploy/deployments/{deployment_id}"})
    blocks.append({"type": "actions", "elements": buttons})

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=developer_slack_id, text=f"Deployment {deployment_id} failed", blocks=blocks)
        return True
    except Exception as exc:
        logger.error("OPS | Developer notification failed | error=%s", exc)
        return False


async def notify_success(
    developer_slack_id: str,
    service_name: str,
    deployment_id: str,
    jira_ticket_key: Optional[str] = None,
    duration_seconds: int = 0,
) -> bool:
    """Send green Block Kit success DM to the developer."""
    settings = get_settings()
    logger.info("OPS | Notifying success | user=%s | deployment=%s", developer_slack_id, deployment_id)

    duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s" if duration_seconds else "N/A"
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "✅ Deployment Succeeded"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Service:* `{service_name}`\n*Deployment:* `{deployment_id}`\n*Duration:* {duration_str}"}},
    ]
    if jira_ticket_key:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"Jira ticket `{jira_ticket_key}` has been resolved. ✅"}})

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)
        client.chat_postMessage(channel=developer_slack_id, text=f"Deployment {deployment_id} succeeded!", blocks=blocks)
        return True
    except Exception as exc:
        logger.error("OPS | Success notification failed | error=%s", exc)
        return False


async def escalate_to_lead(
    team_lead_slack_id: str,
    developer_name: str,
    service_name: str,
    deployment_id: str,
    failure_count: int,
    jira_ticket_key: Optional[str] = None,
) -> bool:
    """Escalate repeated failures to team lead via Slack DM."""
    settings = get_settings()
    logger.info("OPS | Escalating to lead | lead=%s | failures=%d", team_lead_slack_id, failure_count)

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Escalation Required"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": (
            f"*{service_name}* has failed *{failure_count}* consecutive deployments.\n"
            f"Developer: {developer_name}\n"
            f"Latest deployment: `{deployment_id}`"
        )}},
    ]
    if jira_ticket_key:
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": f"📋 {jira_ticket_key}"}, "url": f"{settings.JIRA_URL}/browse/{jira_ticket_key}", "style": "danger"},
        ]})

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)
        client.chat_postMessage(
            channel=team_lead_slack_id,
            text=f"Escalation: {service_name} has failed {failure_count} deployments",
            blocks=blocks,
        )
        return True
    except Exception as exc:
        logger.error("OPS | Escalation failed | error=%s", exc)
        return False


# ── Resolution ───────────────────────────────────────────────────────────────

async def resolve_jira_ticket(
    jira_ticket_key: str,
    deployment_id: str,
    duration_seconds: int = 0,
) -> bool:
    """Resolve a Jira ticket after successful deployment."""
    if not jira_ticket_key:
        return False

    settings = get_settings()
    logger.info("OPS | Resolving Jira ticket | key=%s", jira_ticket_key)

    try:
        from atlassian import Jira
        jira = Jira(url=settings.JIRA_URL, username=settings.JIRA_USERNAME, password=settings.JIRA_API_TOKEN)

        duration_str = f"{duration_seconds // 60}m {duration_seconds % 60}s" if duration_seconds else "N/A"
        comment = (
            f"✅ *Deployment Succeeded*\n"
            f"Deployment ID: {deployment_id}\n"
            f"Duration: {duration_str}\n"
            f"_Resolved automatically by Artilery_"
        )
        jira.issue_add_comment(jira_ticket_key, comment)

        transitions = jira.get_issue_transitions(jira_ticket_key)
        for t in transitions:
            if any(word in t.get("name", "").lower() for word in ("done", "resolved", "closed")):
                jira.set_issue_status(jira_ticket_key, t["name"])
                break

        return True
    except Exception as exc:
        logger.error("OPS | Jira resolution failed | key=%s | error=%s", jira_ticket_key, exc)
        return False


async def resolve_notion_page(notion_page_id: Optional[str]) -> bool:
    """Update Notion page status to Resolved."""
    if not notion_page_id:
        return False

    settings = get_settings()
    logger.info("OPS | Resolving Notion page | id=%s", notion_page_id)

    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=settings.NOTION_TOKEN)
        notion.pages.update(
            page_id=notion_page_id,
            properties={"Status": {"select": {"name": "Resolved"}}},
        )
        notion.blocks.children.append(
            block_id=notion_page_id,
            children=[{"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"✅ Resolved automatically by Artilery — {datetime.now(timezone.utc).isoformat()}"}}
            ]}}],
        )
        return True
    except Exception as exc:
        logger.error("OPS | Notion resolution failed | error=%s", exc)
        return False


# ── Kafka Publishing ─────────────────────────────────────────────────────────

async def publish_deploy_event(topic: str, deployment_id: str, payload: dict[str, Any]) -> None:
    """Publish a deployment event to Kafka."""
    from shared.kafka_utils import KaosProducer

    logger.info("OPS | Publishing %s | deployment=%s", topic, deployment_id)
    with KaosProducer() as producer:
        producer.publish(topic=topic, key=deployment_id, value=payload)
