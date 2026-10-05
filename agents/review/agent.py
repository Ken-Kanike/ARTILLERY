"""
Artilery Review Agent — LangGraph state machine.

Consumes pr.opened, pr.reviewed, pr.approved events and orchestrates
reviewer assignment, status tracking, and Jira/Notion synchronization.

Entrypoint: python -m agents.review.agent
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.review import tools
from shared.config import get_settings
from shared.dynamo_utils import DynamoClient
from shared.kafka_utils import KaosProducer

logger = logging.getLogger("artilery.review.agent")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


class ReviewState(TypedDict):
    pr_number: int
    pr_title: str
    pr_url: str
    pr_author_login: str
    pr_author_slack_id: str
    service_name: str
    jira_ticket_key: Optional[str]
    notion_page_id: Optional[str]
    files_changed: list[str]
    reviewer: Optional[dict]
    event_type: str
    changes_requested: bool
    review_comment: str
    retry_count: int
    error: Optional[str]


# ── Nodes ────────────────────────────────────────────────────────────────────

async def route_event_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Routing event | type=%s | pr=#%d", state["event_type"], state["pr_number"])
    return {**state, "error": None}


async def assign_reviewer_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Entering node: assign_reviewer | pr=#%d", state["pr_number"])
    try:
        reviewer = await tools.assign_reviewer(
            service_name=state["service_name"],
            pr_author_slack_id=state.get("pr_author_slack_id", ""),
            files_changed=state.get("files_changed", []),
        )
        return {**state, "reviewer": reviewer, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def notify_reviewer_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Entering node: notify_reviewer | pr=#%d", state["pr_number"])
    try:
        reviewer = state.get("reviewer", {})
        if reviewer:
            await tools.notify_reviewer_slack(
                reviewer_slack_id=reviewer.get("reviewer_slack_id", ""),
                pr_title=state["pr_title"],
                pr_url=state["pr_url"],
                pr_author=state.get("pr_author_login", ""),
                service_name=state["service_name"],
                files_changed=state.get("files_changed", []),
                jira_ticket_key=state.get("jira_ticket_key"),
            )
        return {**state, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def sync_integrations_node(state: ReviewState) -> ReviewState:
    """Auto-create Jira ticket (if missing), add PR comment, create Notion tracking page."""
    logger.info("REVIEW | Entering node: sync_integrations | pr=#%d", state["pr_number"])
    try:
        reviewer = state.get("reviewer", {})
        reviewer_name = reviewer.get("reviewer_name", "") if reviewer else ""

        # Ensure Jira ticket exists and add PR comment
        jira_key = await tools.ensure_jira_ticket(
            jira_ticket_key=state.get("jira_ticket_key"),
            pr_title=state["pr_title"],
            pr_url=state["pr_url"],
            service_name=state["service_name"],
            pr_author=state.get("pr_author_login", ""),
            reviewer_name=reviewer_name,
        )

        # Create Notion tracking page
        notion_page_id = await tools.create_notion_tracking_page(
            pr_title=state["pr_title"],
            pr_url=state["pr_url"],
            pr_author=state.get("pr_author_login", ""),
            service_name=state["service_name"],
            jira_ticket_key=jira_key,
            reviewer_name=reviewer_name,
        )

        return {**state, "jira_ticket_key": jira_key, "notion_page_id": notion_page_id, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def save_state_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Entering node: save_state | pr=#%d", state["pr_number"])
    try:
        dynamo = DynamoClient()
        reviewer = state.get("reviewer", {})
        dynamo.save_pr_state(state["pr_number"], state["service_name"], {
            "pr_title": state["pr_title"],
            "pr_url": state["pr_url"],
            "pr_author": state.get("pr_author_login", ""),
            "service_name": state["service_name"],
            "jira_ticket_key": state.get("jira_ticket_key"),
            "reviewer_slack_id": reviewer.get("reviewer_slack_id", ""),
            "reviewer_name": reviewer.get("reviewer_name", ""),
            "status": "in_review",
        })
        return {**state, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def handle_approval_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Entering node: handle_approval | pr=#%d", state["pr_number"])
    try:
        reviewer = state.get("reviewer", {})
        reviewer_name = reviewer.get("reviewer_name", "Reviewer")

        if state.get("jira_ticket_key"):
            await tools.update_jira_pr_status(state["jira_ticket_key"], "Approved", state["pr_url"], reviewer_name)
        await tools.update_notion_pr_status(state.get("notion_page_id"), "Approved", state["pr_url"])

        # Publish deploy.triggered
        with KaosProducer() as producer:
            producer.publish("deploy.triggered", key=str(state["pr_number"]), value={
                "pr_number": state["pr_number"],
                "service_name": state["service_name"],
                "jira_ticket_key": state.get("jira_ticket_key"),
            })

        return {**state, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def handle_changes_node(state: ReviewState) -> ReviewState:
    logger.info("REVIEW | Entering node: handle_changes | pr=#%d", state["pr_number"])
    try:
        reviewer = state.get("reviewer", {})
        await tools.notify_developer_changes_requested(
            author_slack_id=state.get("pr_author_slack_id", ""),
            reviewer_name=reviewer.get("reviewer_name", "Reviewer"),
            pr_url=state["pr_url"],
            jira_ticket_key=state.get("jira_ticket_key"),
            review_comment=state.get("review_comment", ""),
        )
        if state.get("jira_ticket_key"):
            await tools.update_jira_pr_status(state["jira_ticket_key"], "Changes Requested", state["pr_url"], reviewer.get("reviewer_name", ""))
        return {**state, "error": None}
    except Exception as exc:
        return {**state, "error": str(exc)}


async def error_handler_node(state: ReviewState) -> ReviewState:
    new_retry = state["retry_count"] + 1
    logger.error("REVIEW | Error handler | pr=#%d | error=%s | retry=%d", state["pr_number"], state["error"], new_retry)
    return {**state, "retry_count": new_retry, "error": None}


# ── Routing ──────────────────────────────────────────────────────────────────

def route_by_event(state: ReviewState) -> str:
    et = state.get("event_type", "")
    if et == "pr.opened":
        return "assign"
    elif et == "pr.approved":
        return "approve"
    elif et == "pr.reviewed" and state.get("changes_requested"):
        return "changes"
    return "assign"  # default


def should_continue(state: ReviewState) -> str:
    return "error_handler" if state.get("error") else "continue"


# ── Graph ────────────────────────────────────────────────────────────────────

def compile() -> Any:
    graph = StateGraph(ReviewState)

    graph.add_node("route_event", route_event_node)
    graph.add_node("assign_reviewer", assign_reviewer_node)
    graph.add_node("notify_reviewer", notify_reviewer_node)
    graph.add_node("sync_integrations", sync_integrations_node)
    graph.add_node("save_state", save_state_node)
    graph.add_node("handle_approval", handle_approval_node)
    graph.add_node("handle_changes", handle_changes_node)
    graph.add_node("error_handler", error_handler_node)

    graph.set_entry_point("route_event")
    graph.add_conditional_edges("route_event", route_by_event, {"assign": "assign_reviewer", "approve": "handle_approval", "changes": "handle_changes"})
    graph.add_conditional_edges("assign_reviewer", should_continue, {"continue": "notify_reviewer", "error_handler": "error_handler"})
    graph.add_conditional_edges("notify_reviewer", should_continue, {"continue": "sync_integrations", "error_handler": "error_handler"})
    graph.add_conditional_edges("sync_integrations", should_continue, {"continue": "save_state", "error_handler": "error_handler"})
    graph.add_edge("save_state", END)
    graph.add_edge("handle_approval", END)
    graph.add_edge("handle_changes", END)
    graph.add_edge("error_handler", END)

    return graph.compile()


async def run_review(event: dict[str, Any]) -> ReviewState:
    payload = event.get("payload", event)
    pr_author = payload.get("pr_author", {})

    initial: ReviewState = {
        "pr_number": payload.get("pr_number", 0),
        "pr_title": payload.get("pr_title", ""),
        "pr_url": payload.get("pr_url", ""),
        "pr_author_login": pr_author.get("login", "") if isinstance(pr_author, dict) else str(pr_author),
        "pr_author_slack_id": "",
        "service_name": payload.get("service_name", ""),
        "jira_ticket_key": payload.get("jira_ticket_key"),
        "notion_page_id": None,
        "files_changed": payload.get("files_changed", []),
        "reviewer": None,
        "event_type": event.get("event_type", "pr.opened"),
        "changes_requested": payload.get("changes_requested", False),
        "review_comment": payload.get("review_comment", ""),
        "retry_count": 0,
        "error": None,
    }

    app = compile()
    return await app.ainvoke(initial)


if __name__ == "__main__":
    import threading
    from shared.kafka_utils import KaosConsumer

    logger.info("Starting Review Agent consumer...")

    REVIEW_TOPICS = ["pr.opened", "pr.reviewed", "pr.approved"]

    def handler(event: dict[str, Any]) -> None:
        asyncio.run(run_review(event))

    def run_consumer(topic: str) -> None:
        logger.info("Review Agent subscribing to %s", topic)
        consumer = KaosConsumer(topic=topic, group_id="artilery-review-agent")
        consumer.consume(handler)

    threads = []
    for topic in REVIEW_TOPICS:
        t = threading.Thread(target=run_consumer, args=(topic,), daemon=True)
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
