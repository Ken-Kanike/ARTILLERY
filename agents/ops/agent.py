"""
Artilery Ops Agent — Deployment Monitor & AI Diagnostics.

LangGraph state machine that:
1. Listens for deploy.triggered → triggers CodeDeploy
2. Listens for deploy.failed → fetches logs → AI diagnosis → notify → rollback/escalate
3. Listens for deploy.succeeded → resolves Jira/Notion → success DM

Uses AWS Bedrock (Claude 3 Sonnet) for failure diagnosis.
Escalates to team lead after 3 consecutive failures.

Entrypoint: python -m agents.ops.agent
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.ops import tools as ops_tools
from shared.config import get_settings

logger = logging.getLogger("artilery.ops.agent")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


class OpsState(TypedDict):
    event_type: str
    deployment_id: str
    application_name: str
    deployment_group: str
    github_repo: str
    commit_id: str
    pr_number: int
    service_name: str
    developer_slack_id: str
    team_lead_slack_id: str
    jira_ticket_key: str
    notion_page_id: Optional[str]
    error_logs: Optional[str]
    diagnosis: Optional[dict[str, Any]]
    failure_count: int
    deploy_start_time: str
    slack_notified: bool
    error: Optional[str]


# ── Nodes ────────────────────────────────────────────────────────────────────

async def route_event_node(state: OpsState) -> OpsState:
    """Route based on event_type."""
    logger.info("OPS | Routing event | type=%s | deployment=%s", state["event_type"], state.get("deployment_id", ""))
    return state


async def trigger_deploy_node(state: OpsState) -> OpsState:
    """Trigger a CodeDeploy deployment."""
    logger.info("OPS | Entering trigger_deploy_node | service=%s", state["service_name"])
    try:
        result = await ops_tools.trigger_codedeploy(
            application_name=state.get("application_name", state["service_name"]),
            deployment_group=state.get("deployment_group", f"{state['service_name']}-group"),
            github_repo=state.get("github_repo", ""),
            commit_id=state.get("commit_id", ""),
            pr_number=state.get("pr_number", 0),
        )
        return {**state, "deployment_id": result["deployment_id"], "error": None}
    except Exception as exc:
        logger.error("OPS | CodeDeploy trigger failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def fetch_logs_node(state: OpsState) -> OpsState:
    """Fetch deployment failure logs from CloudWatch."""
    logger.info("OPS | Entering fetch_logs_node | deployment=%s", state["deployment_id"])
    try:
        logs = await ops_tools.fetch_cloudwatch_logs(state["deployment_id"], state["service_name"])
        return {**state, "error_logs": logs, "error": None}
    except Exception as exc:
        logger.error("OPS | Log fetch failed | error=%s", exc)
        return {**state, "error_logs": f"Log fetch failed: {exc}", "error": str(exc)}


async def diagnose_node(state: OpsState) -> OpsState:
    """AI-diagnose the failure using Bedrock."""
    logger.info("OPS | Entering diagnose_node | deployment=%s", state["deployment_id"])
    try:
        diagnosis = await ops_tools.diagnose_with_bedrock(
            deployment_id=state["deployment_id"],
            error_logs=state.get("error_logs", ""),
            service_name=state["service_name"],
        )

        # Store deployment log in S3
        try:
            from shared.s3_utils import S3Client
            s3 = S3Client()
            s3.store_deployment_log(state["deployment_id"], state.get("error_logs", ""))
        except Exception:
            pass

        return {**state, "diagnosis": diagnosis, "error": None}
    except Exception as exc:
        logger.error("OPS | Diagnosis failed | error=%s", exc)
        return {**state, "diagnosis": {"root_cause": str(exc), "confidence": 0.0}, "error": str(exc)}


async def notify_failure_node(state: OpsState) -> OpsState:
    """Notify the developer and ops channel about the failure."""
    logger.info("OPS | Entering notify_failure_node | deployment=%s", state["deployment_id"])
    diagnosis = state.get("diagnosis", {})

    # Notify ops channel
    await ops_tools.notify_ops_channel(
        service_name=state["service_name"],
        deployment_id=state["deployment_id"],
        root_cause=diagnosis.get("root_cause", "Unknown"),
        remediation=diagnosis.get("remediation", ""),
        jira_ticket_key=state.get("jira_ticket_key"),
    )

    # Notify developer
    if state.get("developer_slack_id"):
        await ops_tools.notify_developer_failure(
            developer_slack_id=state["developer_slack_id"],
            deployment_id=state["deployment_id"],
            service_name=state["service_name"],
            root_cause=diagnosis.get("root_cause", "Unknown"),
            suggested_fix=diagnosis.get("remediation", ""),
            action_items=diagnosis.get("action_items", []),
            jira_ticket_key=state.get("jira_ticket_key"),
        )

    # Auto-rollback if confidence is high enough
    if diagnosis.get("auto_fixable") and diagnosis.get("confidence", 0) >= 0.8:
        logger.info("OPS | Auto-rollback triggered | confidence=%.2f", diagnosis["confidence"])
        await ops_tools.trigger_rollback(state["deployment_id"], state["service_name"])

    return {**state, "slack_notified": True, "failure_count": state.get("failure_count", 0) + 1}


async def escalate_node(state: OpsState) -> OpsState:
    """Escalate to team lead after 3+ failures."""
    logger.info("OPS | Entering escalate_node | failures=%d", state["failure_count"])

    if state.get("team_lead_slack_id"):
        await ops_tools.escalate_to_lead(
            team_lead_slack_id=state["team_lead_slack_id"],
            developer_name=state.get("developer_slack_id", "unknown"),
            service_name=state["service_name"],
            deployment_id=state["deployment_id"],
            failure_count=state["failure_count"],
            jira_ticket_key=state.get("jira_ticket_key"),
        )

    return state


async def resolve_node(state: OpsState) -> OpsState:
    """Resolve Jira, Notion, and send success notification."""
    logger.info("OPS | Entering resolve_node | deployment=%s", state["deployment_id"])

    # Calculate deployment duration
    duration = 0
    if state.get("deploy_start_time"):
        try:
            from datetime import datetime, timezone
            start = datetime.fromisoformat(state["deploy_start_time"])
            duration = int((datetime.now(timezone.utc) - start).total_seconds())
        except Exception:
            pass

    # Resolve Jira
    if state.get("jira_ticket_key"):
        await ops_tools.resolve_jira_ticket(
            jira_ticket_key=state["jira_ticket_key"],
            deployment_id=state["deployment_id"],
            duration_seconds=duration,
        )

    # Resolve Notion
    if state.get("notion_page_id"):
        await ops_tools.resolve_notion_page(state["notion_page_id"])

    # Send success notification
    if state.get("developer_slack_id"):
        await ops_tools.notify_success(
            developer_slack_id=state["developer_slack_id"],
            service_name=state["service_name"],
            deployment_id=state["deployment_id"],
            jira_ticket_key=state.get("jira_ticket_key"),
            duration_seconds=duration,
        )

    # Publish ticket.resolved event
    await ops_tools.publish_deploy_event(
        topic="ticket.resolved",
        deployment_id=state["deployment_id"],
        payload={
            "deployment_id": state["deployment_id"],
            "service_name": state["service_name"],
            "jira_ticket_key": state.get("jira_ticket_key", ""),
            "duration_seconds": duration,
        },
    )

    return {**state, "error": None}


async def error_handler_node(state: OpsState) -> OpsState:
    """Handle errors with logging and alerting."""
    logger.error("OPS | Error handler | deployment=%s | error=%s", state.get("deployment_id"), state.get("error"))
    return state


# ── Routing Logic ────────────────────────────────────────────────────────────

def route_by_event_type(state: OpsState) -> str:
    et = state.get("event_type", "")
    if et == "deploy.triggered":
        return "trigger_deploy"
    elif et == "deploy.failed":
        return "fetch_logs"
    elif et == "deploy.succeeded":
        return "resolve"
    return "error_handler"


def route_after_failure(state: OpsState) -> str:
    if state.get("failure_count", 0) >= 3:
        return "escalate"
    return "__end__"


# ── Graph ────────────────────────────────────────────────────────────────────

def compile() -> Any:
    graph = StateGraph(OpsState)

    graph.add_node("route_event", route_event_node)
    graph.add_node("trigger_deploy", trigger_deploy_node)
    graph.add_node("fetch_logs", fetch_logs_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("notify_failure", notify_failure_node)
    graph.add_node("escalate", escalate_node)
    graph.add_node("resolve", resolve_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("route_event")

    graph.add_conditional_edges("route_event", route_by_event_type, {
        "trigger_deploy": "trigger_deploy",
        "fetch_logs": "fetch_logs",
        "resolve": "resolve",
        "error_handler": "error_handler",
    })

    graph.add_edge("trigger_deploy", END)
    graph.add_edge("fetch_logs", "diagnose")
    graph.add_edge("diagnose", "notify_failure")

    graph.add_conditional_edges("notify_failure", route_after_failure, {
        "escalate": "escalate",
        "__end__": END,
    })

    graph.add_edge("escalate", END)
    graph.add_edge("resolve", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


async def run_ops(event: dict[str, Any]) -> dict[str, Any]:
    """Run the Ops Agent for a single event."""
    payload = event.get("payload", event)

    initial: OpsState = {
        "event_type": event.get("event_type", payload.get("event_type", "")),
        "deployment_id": payload.get("deployment_id", ""),
        "application_name": payload.get("application_name", ""),
        "deployment_group": payload.get("deployment_group", ""),
        "github_repo": payload.get("github_repo", ""),
        "commit_id": payload.get("commit_id", ""),
        "pr_number": payload.get("pr_number", 0),
        "service_name": payload.get("service_name", ""),
        "developer_slack_id": payload.get("developer_slack_id", ""),
        "team_lead_slack_id": payload.get("team_lead_slack_id", ""),
        "jira_ticket_key": payload.get("jira_ticket_key", ""),
        "notion_page_id": payload.get("notion_page_id"),
        "error_logs": payload.get("error_message", None),
        "diagnosis": None,
        "failure_count": payload.get("failure_count", 0),
        "deploy_start_time": payload.get("deploy_start_time", ""),
        "slack_notified": False,
        "error": None,
    }

    app = compile()
    return await app.ainvoke(initial)


if __name__ == "__main__":
    import threading
    from shared.kafka_utils import KaosConsumer

    logger.info("Starting Ops Agent consumer...")

    OPS_TOPICS = ["deploy.triggered", "deploy.failed", "deploy.succeeded"]

    def handler(event: dict[str, Any]) -> None:
        asyncio.run(run_ops(event))

    def run_consumer(topic: str) -> None:
        logger.info("Ops Agent subscribing to %s", topic)
        consumer = KaosConsumer(topic=topic, group_id="artilery-ops-agent")
        consumer.consume(handler)

    threads = []
    for topic in OPS_TOPICS:
        t = threading.Thread(target=run_consumer, args=(topic,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
