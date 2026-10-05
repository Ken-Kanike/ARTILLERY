"""
Artilery Triage Agent — LangGraph state machine.

Consumes bug.ingested events from Kafka and orchestrates:
1. Neo4j owner lookup (on-call or fallback team lead)
2. Jira ticket creation with pre-filled metadata
3. Notion page creation mirroring Jira
4. Slack DM notification with Block Kit rich message
5. Kafka ticket.created publication

Entrypoint: python -m agents.triage.agent
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.triage import tools
from shared.config import get_settings
from shared.neo4j_utils import Neo4jClient

logger = logging.getLogger("artilery.triage.agent")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


# ── State Schema ─────────────────────────────────────────────────────────────

class TriageState(TypedDict):
    """State passed between LangGraph nodes."""
    bug_id: str
    service_name: str
    severity: str
    description: str
    owner: dict
    jira_ticket: dict
    notion_page: dict
    slack_sent: bool
    kafka_published: bool
    error: Optional[str]
    retry_count: int


# ── Graph Nodes ──────────────────────────────────────────────────────────────

async def query_owner_node(state: TriageState) -> TriageState:
    """Query Neo4j for the on-call owner of the service."""
    logger.info("TRIAGE | Entering node: query_owner_node | bug_id=%s", state["bug_id"])
    try:
        client = Neo4jClient()
        owner = client.get_service_owner(state["service_name"])
        client.close()

        if not owner:
            settings = get_settings()
            fallback = settings.DEFAULT_SLACK_CHANNEL or "C0123456789"
            logger.warning("TRIAGE | No owner found, using fallback channel | service=%s", state["service_name"])
            owner = {
                "developer_name": "Unassigned",
                "developer_id": "unknown",
                "slack_user_id": fallback,
                "jira_account_id": "",
                "email": "",
                "team_name": "Unknown",
                "slack_channel_id": fallback,
            }

        return {**state, "owner": owner, "error": None}
    except Exception as exc:
        logger.error("TRIAGE | query_owner_node failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def create_jira_node(state: TriageState) -> TriageState:
    """Create a Jira ticket for the bug."""
    logger.info("TRIAGE | Entering node: create_jira_node | bug_id=%s", state["bug_id"])
    try:
        result = await tools.create_jira_ticket(
            summary=f"[{state['severity']}] {state['service_name']} — {state['bug_id']}",
            description=state["description"],
            priority=state["severity"],
            assignee_jira_id=state["owner"].get("jira_account_id", ""),
            service_name=state["service_name"],
            bug_id=state["bug_id"],
        )
        return {**state, "jira_ticket": result, "error": None}
    except Exception as exc:
        logger.error("TRIAGE | create_jira_node failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def create_notion_node(state: TriageState) -> TriageState:
    """Create a Notion page mirroring the Jira ticket."""
    logger.info("TRIAGE | Entering node: create_notion_node | bug_id=%s", state["bug_id"])
    try:
        result = await tools.create_notion_page(
            title=f"[{state['bug_id']}] {state['service_name']} — {state['severity']}",
            jira_ticket_key=state["jira_ticket"].get("ticket_key", ""),
            jira_ticket_url=state["jira_ticket"].get("ticket_url", ""),
            service_name=state["service_name"],
            assignee_name=state["owner"].get("developer_name", ""),
            priority=state["severity"],
            description=state["description"],
        )
        return {**state, "notion_page": result, "error": None}
    except Exception as exc:
        logger.error("TRIAGE | create_notion_node failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def notify_slack_node(state: TriageState) -> TriageState:
    """Send a Slack DM to the service owner with rich Block Kit message."""
    logger.info("TRIAGE | Entering node: notify_slack_node | bug_id=%s", state["bug_id"])
    try:
        blocks = tools.build_severity_blocks(
            bug_summary=f"[{state['bug_id']}] {state['description'][:100]}",
            service_name=state["service_name"],
            priority=state["severity"],
            jira_ticket_key=state["jira_ticket"].get("ticket_key", ""),
            jira_ticket_url=state["jira_ticket"].get("ticket_url", ""),
            notion_page_url=state["notion_page"].get("page_url"),
        )
        sent = await tools.send_slack_dm(
            slack_user_id=state["owner"]["slack_user_id"],
            message=f"Bug assigned: {state['bug_id']} ({state['severity']}) — {state['service_name']}",
            blocks=blocks,
        )
        return {**state, "slack_sent": sent, "error": None}
    except Exception as exc:
        logger.error("TRIAGE | notify_slack_node failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def publish_event_node(state: TriageState) -> TriageState:
    """Publish ticket.created event to Kafka."""
    logger.info("TRIAGE | Entering node: publish_event_node | bug_id=%s", state["bug_id"])
    try:
        await tools.publish_ticket_created(
            bug_id=state["bug_id"],
            jira_ticket_key=state["jira_ticket"].get("ticket_key", ""),
            jira_ticket_url=state["jira_ticket"].get("ticket_url", ""),
            notion_page_id=state["notion_page"].get("page_id", ""),
            service_name=state["service_name"],
            assignee_slack_id=state["owner"]["slack_user_id"],
            priority=state["severity"],
        )
        return {**state, "kafka_published": True, "error": None}
    except Exception as exc:
        logger.error("TRIAGE | publish_event_node failed | error=%s", exc)
        return {**state, "error": str(exc)}


async def error_handler_node(state: TriageState) -> TriageState:
    """Handle errors: log, increment retry count, alert #kaos-alerts."""
    new_retry = state["retry_count"] + 1
    logger.error(
        "TRIAGE | Error handler | bug_id=%s | error=%s | retry_count=%d",
        state["bug_id"], state["error"], new_retry,
    )

    if new_retry >= 3:
        logger.error("TRIAGE | Max retries reached | bug_id=%s — giving up", state["bug_id"])
        await tools.send_slack_channel_alert(
            channel_id=get_settings().DEFAULT_SLACK_CHANNEL or "C0123456789",
            message=f"🚨 Artilery Triage Agent FAILED after 3 retries\nBug: {state['bug_id']}\nService: {state['service_name']}\nError: {state['error']}",
        )

    return {**state, "retry_count": new_retry, "error": None}


# ── Routing ──────────────────────────────────────────────────────────────────

def should_continue(state: TriageState) -> str:
    """Route based on error presence."""
    if state.get("error"):
        return "error_handler"
    return "continue"


def should_retry(state: TriageState) -> str:
    """After error handler, decide to retry or give up."""
    if state["retry_count"] < 3:
        return "retry"
    return "give_up"


# ── Graph Construction ───────────────────────────────────────────────────────

def compile() -> Any:
    """Build and compile the Triage Agent LangGraph."""
    graph = StateGraph(TriageState)

    # Add nodes
    graph.add_node("query_owner", query_owner_node)
    graph.add_node("create_jira", create_jira_node)
    graph.add_node("create_notion", create_notion_node)
    graph.add_node("notify_slack", notify_slack_node)
    graph.add_node("publish_event", publish_event_node)
    graph.add_node("error_handler", error_handler_node)

    # Set entry point
    graph.set_entry_point("query_owner")

    # Edges with error routing
    graph.add_conditional_edges("query_owner", should_continue, {"continue": "create_jira", "error_handler": "error_handler"})
    graph.add_conditional_edges("create_jira", should_continue, {"continue": "create_notion", "error_handler": "error_handler"})
    graph.add_conditional_edges("create_notion", should_continue, {"continue": "notify_slack", "error_handler": "error_handler"})
    graph.add_conditional_edges("notify_slack", should_continue, {"continue": "publish_event", "error_handler": "error_handler"})
    graph.add_edge("publish_event", END)

    # Error handler: retry or give up
    graph.add_conditional_edges("error_handler", should_retry, {"retry": "query_owner", "give_up": END})

    return graph.compile()


async def run_triage(event: dict[str, Any]) -> TriageState:
    """Run the Triage Agent on a raw Kafka event.

    Args:
        event: Parsed Kafka event envelope with payload containing
               bug_id, service, severity, description.
    """
    payload = event.get("payload", event)

    initial_state: TriageState = {
        "bug_id": payload.get("bug_id", "UNKNOWN"),
        "service_name": payload.get("service", payload.get("service_name", "Unknown")),
        "severity": payload.get("severity", "Medium"),
        "description": payload.get("description", "No description provided"),
        "owner": {},
        "jira_ticket": {},
        "notion_page": {},
        "slack_sent": False,
        "kafka_published": False,
        "error": None,
        "retry_count": 0,
    }

    logger.info("TRIAGE | Starting | bug_id=%s | service=%s | severity=%s",
                initial_state["bug_id"], initial_state["service_name"], initial_state["severity"])

    app = compile()
    final_state = await app.ainvoke(initial_state)

    if final_state.get("kafka_published"):
        logger.info("TRIAGE | Completed successfully | bug_id=%s | jira=%s",
                     final_state["bug_id"], final_state["jira_ticket"].get("ticket_key"))
    else:
        logger.error("TRIAGE | Completed with failure | bug_id=%s | retries=%d",
                      final_state["bug_id"], final_state["retry_count"])

    return final_state


# ── Entrypoint ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from shared.kafka_utils import KaosConsumer

    logger.info("Starting Triage Agent consumer on 'bug.ingested'...")

    def handler(event: dict[str, Any]) -> None:
        result = asyncio.run(run_triage(event))
        logger.info("TRIAGE | Handler complete | bug_id=%s | published=%s",
                     result["bug_id"], result["kafka_published"])

    consumer = KaosConsumer(topic="bug.ingested", group_id="artilery-triage-agent")
    consumer.consume(handler)
