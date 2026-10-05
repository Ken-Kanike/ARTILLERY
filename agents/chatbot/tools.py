"""
Artilery Chatbot Agent — Tool functions.

Provides retrieval tools for the RAG pipeline:
- query_knowledge_graph: Neo4j queries based on intent
- retrieve_recent_events: S3 event log retrieval
- retrieve_state: DynamoDB state lookup
- generate_answer: LLM inference with context (Ollama local / Bedrock production)
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.chatbot.tools")


# ── Neo4j Knowledge Graph ───────────────────────────────────────────────────

async def query_knowledge_graph(query: str, intent: str) -> list[dict[str, Any]]:
    """Query Neo4j based on classified intent."""
    from shared.neo4j_utils import Neo4jClient

    client = Neo4jClient()
    results: list[dict[str, Any]] = []

    try:
        if intent == "team_query":
            results = client.execute_query(
                "MATCH (d:Developer)-[:MEMBER_OF]->(t:Team) "
                "OPTIONAL MATCH (d)-[oc:ON_CALL]->(s:Service) "
                "RETURN t.name AS team, d.name AS developer, d.email AS email, "
                "collect(DISTINCT s.name) AS on_call_services "
                "ORDER BY t.name, d.name"
            )

        elif intent == "service_query":
            results = client.execute_query(
                "MATCH (t:Team)-[:OWNS]->(s:Service) "
                "OPTIONAL MATCH (s)-[:DEPENDS_ON]->(dep:Service) "
                "RETURN s.name AS service, t.name AS owner_team, "
                "collect(DISTINCT dep.name) AS dependencies, "
                "s.repo_url AS repo_url"
            )

        elif intent in ("triage_query", "deployment_query", "pr_query"):
            results = client.execute_query(
                "MATCH (d:Developer)-[:MEMBER_OF]->(t:Team)-[:OWNS]->(s:Service) "
                "OPTIONAL MATCH (d)-[oc:ON_CALL]->(s) "
                "RETURN s.name AS service, d.name AS on_call_developer, "
                "t.name AS team, d.slack_user_id AS slack_id"
            )

        else:
            results = client.execute_query(
                "MATCH (n) RETURN DISTINCT labels(n) AS type, count(n) AS count"
            )

    except Exception as exc:
        logger.warning("CHATBOT | Neo4j query failed | intent=%s | error=%s", intent, exc)

    finally:
        client.close()

    return results


# ── S3 Event Retrieval ───────────────────────────────────────────────────

async def retrieve_recent_events(intent: str, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve relevant events from S3 based on intent."""
    from shared.s3_utils import S3Client

    intent_to_topics: dict[str, list[str]] = {
        "deployment_query": ["deploy.failed", "deploy.succeeded", "deploy.triggered"],
        "triage_query": ["bug.ingested", "ticket.created"],
        "pr_query": ["pr.opened", "pr.approved", "pr.reviewed"],
    }

    topics = intent_to_topics.get(intent, ["bug.ingested", "deploy.failed"])
    events: list[dict[str, Any]] = []

    try:
        s3 = S3Client()
        for topic in topics:
            keys = s3.list_recent_events(topic, days=3)
            for key in keys[:limit]:
                try:
                    event = s3.get_event(key)
                    events.append(event)
                except Exception:
                    pass
    except Exception as exc:
        logger.warning("CHATBOT | S3 retrieval failed | error=%s", exc)

    return events[:limit]


# ── DynamoDB State Retrieval ─────────────────────────────────────────────

async def retrieve_state(query: str, intent: str) -> dict[str, Any]:
    """Retrieve relevant state from DynamoDB."""
    from shared.dynamo_utils import DynamoClient

    result: dict[str, Any] = {}
    try:
        dynamo = DynamoClient()

        if intent == "pr_query":
            # Try to extract PR number from query
            import re
            pr_match = re.search(r"#?(\d+)", query)
            if pr_match:
                pr_num = int(pr_match.group(1))
                state = dynamo.get_pr_state(pr_num, "")
                if state:
                    result = {"pr_state": state}

        elif intent == "deployment_query":
            import re
            dep_match = re.search(r"d-[A-Z0-9]+", query, re.IGNORECASE)
            if dep_match:
                state = dynamo.get_deployment(dep_match.group(0))
                if state:
                    result = {"deployment_state": state}

    except Exception as exc:
        logger.warning("CHATBOT | DynamoDB retrieval failed | error=%s", exc)

    return result


# ── Answer Generation ────────────────────────────────────────────────────

async def generate_answer(
    query: str,
    neo4j_context: list[dict[str, Any]],
    event_context: list[dict[str, Any]],
    state_context: dict[str, Any],
    chat_history: list[dict[str, Any]],
    retrieved_text: str = "",
) -> tuple[str, list[str]]:
    """Generate an answer using the unified LLM interface (Ollama local / Bedrock production).

    Returns (answer_text, list_of_sources).
    """
    from shared.llm import invoke_llm

    # Build context string
    context_parts: list[str] = []
    sources: list[str] = []

    if neo4j_context:
        context_parts.append("=== Organization Knowledge Graph ===")
        for item in neo4j_context[:10]:
            context_parts.append(json.dumps(item, default=str))
        sources.append("Neo4j Knowledge Graph")

    if event_context:
        context_parts.append("\n=== Recent Events ===")
        for event in event_context[:5]:
            context_parts.append(json.dumps(event, default=str))
        sources.append(f"S3 Event Logs ({len(event_context)} events)")

    if state_context:
        context_parts.append("\n=== Current State ===")
        context_parts.append(json.dumps(state_context, default=str))
        sources.append("DynamoDB State Store")

    context_text = "\n".join(context_parts) if context_parts else "No specific context available."

    # Append retrieved text from hybrid retriever pipeline
    if retrieved_text and retrieved_text != "No specific context available.":
        context_text = context_text + "\n\n=== Hybrid Retrieval Results ===\n" + retrieved_text

    # Build history string
    history_text = ""
    if chat_history:
        history_parts = []
        for turn in chat_history[-5:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            history_parts.append(f"{role}: {content}")
        history_text = "\n".join(history_parts)

    prompt = f"""You are Artilery Bot, an AI assistant for the Artilery CI/CD automation platform.
You have access to the organization's knowledge graph, recent deployment/PR events, and system state.

Answer the user's question using ONLY the provided context. If the context doesn't contain
enough information, say so clearly. Be concise and helpful.

{f"=== Chat History ==={chr(10)}{history_text}" if history_text else ""}

=== Context ===
{context_text}

=== User Question ===
{query}

Respond in a clear, structured format. Use bullet points for lists. Mention specific names,
services, and ticket numbers when available."""

    try:
        answer = await invoke_llm(
            prompt=prompt,
            system="You are Artilery Bot, a DevOps CI/CD assistant. Be concise and helpful.",
            max_tokens=1024,
        )
        return answer, sources

    except Exception as exc:
        logger.error("CHATBOT | LLM generation failed | error=%s", exc)

        # Fallback: generate a basic response from context
        if neo4j_context:
            fallback = "Based on the knowledge graph:\n"
            for item in neo4j_context[:3]:
                fallback += f"• {json.dumps(item, default=str)}\n"
            return fallback, sources

        # If we have retrieved text, return that
        if retrieved_text and retrieved_text != "No specific context available.":
            return f"Based on available data:\n\n{retrieved_text}", sources

        return f"I'm sorry, I couldn't process your query right now. Please try again later.", sources
