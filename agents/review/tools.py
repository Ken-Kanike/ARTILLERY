"""
Artilery Review Agent — Tool functions for LangGraph nodes.

Provides: assign_reviewer, notify_reviewer_slack, update_jira_pr_status,
update_notion_pr_status, notify_developer_changes_requested.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from shared.config import get_settings
from shared.neo4j_utils import Neo4jClient

logger = logging.getLogger("artilery.review.tools")

EXT_TO_SKILL: dict[str, str] = {
    ".py": "Python", ".java": "Java", ".go": "Go", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".js": "TypeScript", ".tf": "DevOps",
    ".yml": "DevOps", ".yaml": "DevOps", ".css": "CSS",
}


async def assign_reviewer(
    service_name: str,
    pr_author_slack_id: str,
    files_changed: list[str],
) -> dict[str, Any]:
    """Assign a reviewer using Neo4j skill-based routing."""
    logger.info("REVIEW | Assigning reviewer | service=%s", service_name)

    file_extensions = list({os.path.splitext(f)[1] for f in files_changed if os.path.splitext(f)[1]})

    client = Neo4jClient()
    reviewer = client.get_reviewer_for_service(
        service_name=service_name,
        exclude_developer_id=pr_author_slack_id,
        file_extensions=file_extensions,
    )
    client.close()

    if not reviewer:
        logger.warning("REVIEW | No reviewer found for %s", service_name)
        return {}

    return {
        "reviewer_name": reviewer.get("reviewer_name", ""),
        "reviewer_slack_id": reviewer.get("reviewer_slack_id", ""),
        "reviewer_jira_id": reviewer.get("reviewer_jira_id", ""),
    }


async def notify_reviewer_slack(
    reviewer_slack_id: str,
    pr_title: str,
    pr_url: str,
    pr_author: str,
    service_name: str,
    files_changed: list[str],
    jira_ticket_key: Optional[str] = None,
) -> bool:
    """Send rich Block Kit DM to the assigned reviewer."""
    settings = get_settings()
    logger.info("REVIEW | Notifying reviewer | user=%s | pr=%s", reviewer_slack_id, pr_title[:50])

    files_display = files_changed[:5]
    remaining = len(files_changed) - 5
    files_text = "\n".join(f"• `{f}`" for f in files_display)
    if remaining > 0:
        files_text += f"\n• _+{remaining} more files_"

    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "📝 You've been assigned to review a PR"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{pr_title}*\nby {pr_author} · `{service_name}`"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Files changed:*\n{files_text}"}},
        {"type": "divider"},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "🔍 Open PR"}, "url": pr_url, "style": "primary"},
        ]},
    ]
    if jira_ticket_key:
        jira_url = f"{settings.JIRA_URL}/browse/{jira_ticket_key}"
        blocks[-1]["elements"].append(
            {"type": "button", "text": {"type": "plain_text", "text": f"📋 {jira_ticket_key}"}, "url": jira_url}
        )

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)

        # Open a DM channel with the user first
        dm = client.conversations_open(users=[reviewer_slack_id])
        dm_channel = dm["channel"]["id"]

        client.chat_postMessage(
            channel=dm_channel,
            text=f"You've been assigned to review: {pr_title}",
            blocks=blocks,
        )
        logger.info("REVIEW | Slack DM sent to %s in channel %s", reviewer_slack_id, dm_channel)
        return True
    except Exception as exc:
        logger.error("REVIEW | Slack notification failed | error=%s", exc)
        return False


async def update_jira_pr_status(
    jira_ticket_key: str,
    status: str,
    pr_url: str,
    reviewer_name: str,
) -> bool:
    """Add a comment and transition Jira ticket status."""
    if not jira_ticket_key:
        logger.warning("REVIEW | No Jira key — skipping Jira update")
        return False

    settings = get_settings()
    logger.info("REVIEW | Updating Jira | key=%s | status=%s", jira_ticket_key, status)

    try:
        from atlassian import Jira
        jira = Jira(url=settings.JIRA_URL, username=settings.JIRA_USERNAME, password=settings.JIRA_API_TOKEN)

        comment = f"PR status updated to *{status}* by {reviewer_name}\nPR: {pr_url}\n_Updated by Artilery_"
        jira.issue_add_comment(jira_ticket_key, comment)

        # Attempt status transition
        transitions = jira.get_issue_transitions(jira_ticket_key)
        for t in transitions:
            if status.lower() in t.get("name", "").lower():
                jira.set_issue_status(jira_ticket_key, t["name"])
                break

        return True
    except Exception as exc:
        logger.error("REVIEW | Jira update failed | key=%s | error=%s", jira_ticket_key, exc)
        return False


async def ensure_jira_ticket(
    jira_ticket_key: Optional[str],
    pr_title: str,
    pr_url: str,
    service_name: str,
    pr_author: str,
    reviewer_name: str = "",
) -> Optional[str]:
    """Ensure a Jira ticket exists for the PR. Create one if missing, then add PR comment.

    Returns the Jira ticket key (existing or newly created).
    """
    settings = get_settings()
    if not settings.JIRA_URL or not settings.JIRA_API_TOKEN:
        logger.warning("REVIEW | Jira not configured — skipping")
        return jira_ticket_key

    try:
        from atlassian import Jira
        jira = Jira(url=settings.JIRA_URL, username=settings.JIRA_USERNAME, password=settings.JIRA_API_TOKEN)

        # Check if ticket exists
        if jira_ticket_key:
            try:
                jira.issue(jira_ticket_key)
                logger.info("REVIEW | Jira ticket exists | key=%s", jira_ticket_key)
            except Exception:
                logger.info("REVIEW | Jira ticket %s not found — creating", jira_ticket_key)
                jira_ticket_key = None  # Will create below

        # Create ticket if needed
        if not jira_ticket_key:
            fields = {
                "project": {"key": settings.JIRA_PROJECT_KEY},
                "summary": f"[{service_name}] {pr_title}",
                "description": f"Auto-created by Artilery Review Agent.\n\nPR: {pr_url}\nAuthor: {pr_author}\nService: {service_name}",
                "issuetype": {"name": "Task"},
            }
            new_issue = jira.create_issue(fields=fields)
            jira_ticket_key = new_issue.get("key", "")
            logger.info("REVIEW | Jira ticket created | key=%s", jira_ticket_key)

        # Add PR link comment
        comment = (
            f"PR opened: *{pr_title}*\n"
            f"Author: {pr_author}\n"
            f"Reviewer: {reviewer_name or 'Pending'}\n"
            f"Service: {service_name}\n"
            f"PR Link: {pr_url}\n\n"
            f"_Auto-tracked by Artilery_"
        )
        jira.issue_add_comment(jira_ticket_key, comment)
        logger.info("REVIEW | Jira comment added | key=%s", jira_ticket_key)

        return jira_ticket_key

    except Exception as exc:
        logger.error("REVIEW | Jira ensure/create failed | error=%s", exc)
        return jira_ticket_key


async def create_notion_tracking_page(
    pr_title: str,
    pr_url: str,
    pr_author: str,
    service_name: str,
    jira_ticket_key: Optional[str],
    reviewer_name: str = "",
) -> Optional[str]:
    """Create a Notion page to track the PR lifecycle. Returns the page ID."""
    settings = get_settings()
    if not settings.NOTION_TOKEN or not settings.NOTION_DATABASE_ID:
        logger.warning("REVIEW | Notion not configured — skipping")
        return None

    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=settings.NOTION_TOKEN)

        properties: dict[str, Any] = {
            "Name": {"title": [{"text": {"content": pr_title}}]},
            "Status": {"select": {"name": "In Review"}},
        }

        # Build page content blocks
        children = [
            {"type": "heading_2", "heading_2": {"rich_text": [{"type": "text", "text": {"content": "PR Details"}}]}},
            {"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"Service: {service_name}\n"}},
                {"type": "text", "text": {"content": f"Author: {pr_author}\n"}},
                {"type": "text", "text": {"content": f"Reviewer: {reviewer_name or 'Pending'}\n"}},
                {"type": "text", "text": {"content": f"Jira: {jira_ticket_key or 'N/A'}\n"}},
            ]}},
            {"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": "PR Link: "}},
                {"type": "text", "text": {"content": pr_url, "link": {"url": pr_url}}},
            ]}},
            {"type": "divider", "divider": {}},
            {"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": "Auto-tracked by Artilery Review Agent"}}
            ]}},
        ]

        page = notion.pages.create(
            parent={"database_id": settings.NOTION_DATABASE_ID},
            properties=properties,
            children=children,
        )
        page_id = page.get("id", "")
        logger.info("REVIEW | Notion tracking page created | page_id=%s", page_id)
        return page_id

    except Exception as exc:
        logger.error("REVIEW | Notion page creation failed | error=%s", exc)
        return None


async def update_notion_pr_status(
    notion_page_id: Optional[str],
    status: str,
    pr_url: str,
) -> bool:
    """Update the Status property of the Notion page."""
    if not notion_page_id:
        return False

    settings = get_settings()
    try:
        from notion_client import Client as NotionClient
        notion = NotionClient(auth=settings.NOTION_TOKEN)
        notion.pages.update(
            page_id=notion_page_id,
            properties={"Status": {"select": {"name": status}}},
        )
        notion.blocks.children.append(
            block_id=notion_page_id,
            children=[{"type": "paragraph", "paragraph": {"rich_text": [
                {"type": "text", "text": {"content": f"PR status: {status} — ", "link": None}},
                {"type": "text", "text": {"content": pr_url, "link": {"url": pr_url}}},
            ]}}],
        )
        return True
    except Exception as exc:
        logger.error("REVIEW | Notion update failed | error=%s", exc)
        return False


async def notify_developer_changes_requested(
    author_slack_id: str,
    reviewer_name: str,
    pr_url: str,
    jira_ticket_key: Optional[str],
    review_comment: str,
) -> bool:
    """Send Slack DM to PR author about requested changes."""
    settings = get_settings()
    blocks: list[dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "🔄 Changes Requested"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{reviewer_name}* has requested changes on your PR."}},
    ]
    if review_comment:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f">>> {review_comment[:500]}"}})
    buttons = [{"type": "button", "text": {"type": "plain_text", "text": "🔍 View PR"}, "url": pr_url, "style": "primary"}]
    if jira_ticket_key:
        buttons.append({"type": "button", "text": {"type": "plain_text", "text": f"📋 {jira_ticket_key}"}, "url": f"{settings.JIRA_URL}/browse/{jira_ticket_key}"})
    blocks.append({"type": "actions", "elements": buttons})

    try:
        from slack_sdk import WebClient
        client = WebClient(token=settings.SLACK_BOT_TOKEN)
        dm = client.conversations_open(users=[author_slack_id])
        dm_channel = dm["channel"]["id"]
        client.chat_postMessage(channel=dm_channel, text=f"Changes requested by {reviewer_name}", blocks=blocks)
        return True
    except Exception as exc:
        logger.error("REVIEW | Changes notification failed | error=%s", exc)
        return False
