"""
Artilery Chatbot — Retriever Functions.

Provides data-source-specific retrieval for the RAG pipeline:
- retrieve_from_neo4j: Cypher queries based on intent + entities
- retrieve_from_dynamo: DynamoDB state lookups
- retrieve_from_vector_store: ChromaDB similarity search
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.config import get_settings

logger = logging.getLogger("artilery.chatbot.retrievers")


async def retrieve_from_neo4j(question: str, intent: str, entities: dict[str, Any]) -> str:
    """Query Neo4j graph based on intent and extracted entities."""
    from shared.neo4j_utils import Neo4jClient

    client = Neo4jClient()
    results: list[dict[str, Any]] = []

    try:
        service = entities.get("service_name", "")
        team = entities.get("team_name", "")

        if intent == "service_owner" and service:
            owner = client.get_service_owner(service)
            if owner:
                return (
                    f"Service '{service}' is owned by {owner.get('developer_name', 'unknown')} "
                    f"from team {owner.get('team_name', 'unknown')}. "
                    f"Email: {owner.get('email', 'N/A')}. "
                    f"Slack: {owner.get('slack_user_id', 'N/A')}."
                )
            return f"No owner found for service '{service}'."

        elif intent == "on_call" and service:
            results = client.execute_query(
                "MATCH (d:Developer)-[oc:ON_CALL]->(s:Service {name: $service}) "
                "RETURN d.name AS developer, d.email AS email, d.slack_user_id AS slack_id, "
                "oc.start_date AS start_date, oc.end_date AS end_date",
                {"service": service},
            )
            if results:
                lines = [f"On-call for {service}:"]
                for r in results:
                    lines.append(f"  • {r['developer']} ({r['email']}) — {r.get('start_date', '')} to {r.get('end_date', '')}")
                return "\n".join(lines)
            return f"No on-call assignments found for '{service}'."

        elif intent == "team_info" and team:
            results = client.execute_query(
                "MATCH (d:Developer)-[:MEMBER_OF]->(t:Team {name: $team}) "
                "OPTIONAL MATCH (d)-[:HAS_SKILL]->(sk:Skill) "
                "RETURN d.name AS developer, d.email AS email, "
                "collect(DISTINCT sk.name) AS skills "
                "ORDER BY d.name",
                {"team": team},
            )
            if results:
                lines = [f"Team '{team}' members:"]
                for r in results:
                    skills = ", ".join(r.get("skills", []))
                    lines.append(f"  • {r['developer']} ({r['email']}) — Skills: {skills}")
                return "\n".join(lines)
            return f"No members found for team '{team}'."

        elif intent == "service_owner":
            # No specific service, list all
            results = client.execute_query(
                "MATCH (t:Team)-[:OWNS]->(s:Service) "
                "RETURN s.name AS service, t.name AS team ORDER BY s.name"
            )
            if results:
                lines = ["Service ownership:"]
                for r in results:
                    lines.append(f"  • {r['service']} → Team {r['team']}")
                return "\n".join(lines)

        # Fallback: general graph overview
        results = client.execute_query(
            "MATCH (n) RETURN DISTINCT labels(n) AS type, count(n) AS count"
        )
        lines = ["Knowledge graph overview:"]
        for r in results:
            lines.append(f"  • {r['type']}: {r['count']} nodes")
        return "\n".join(lines)

    except Exception as exc:
        logger.warning("RETRIEVER | Neo4j failed | error=%s", exc)
        return "Unable to query the knowledge graph at this time."

    finally:
        client.close()


async def retrieve_from_dynamo(question: str, intent: str, entities: dict[str, Any]) -> str:
    """Retrieve state from DynamoDB based on intent and entities."""
    from shared.dynamo_utils import DynamoClient
    import re

    dynamo = DynamoClient()

    try:
        if intent == "pr_status":
            pr_number = entities.get("pr_number")
            if not pr_number:
                pr_match = re.search(r"#?(\d+)", question)
                if pr_match:
                    pr_number = int(pr_match.group(1))

            if pr_number:
                state = dynamo.get_pr_state(pr_number, "")
                if state:
                    return (
                        f"PR #{pr_number}: {state.get('pr_title', 'N/A')}\n"
                        f"  Status: {state.get('status', 'unknown')}\n"
                        f"  Reviewer: {state.get('reviewer_name', 'not assigned')}\n"
                        f"  Service: {state.get('service_name', 'N/A')}\n"
                        f"  Jira: {state.get('jira_ticket_key', 'N/A')}\n"
                        f"  Created: {state.get('created_at', 'N/A')}"
                    )
                return f"No state found for PR #{pr_number}."

        elif intent == "deployment_history":
            dep_id = entities.get("deployment_id")
            if dep_id:
                state = dynamo.get_deployment(dep_id)
                if state:
                    return (
                        f"Deployment {dep_id}:\n"
                        f"  Status: {state.get('status', 'unknown')}\n"
                        f"  Service: {state.get('service_name', 'N/A')}\n"
                        f"  Updated: {state.get('updated_at', 'N/A')}"
                    )
                return f"No state found for deployment {dep_id}."

    except Exception as exc:
        logger.warning("RETRIEVER | DynamoDB failed | error=%s", exc)

    return "No relevant state data found."


async def retrieve_from_vector_store(question: str, entities: dict[str, Any]) -> str:
    """Search ChromaDB for semantically similar events and logs."""
    from shared.vector_store import VectorStore

    vs = VectorStore(collection_name="event_logs")

    try:
        # Build filter from entities
        where_filter = None
        service = entities.get("service_name")
        if service:
            where_filter = {"service_name": service}

        results = vs.similarity_search(query=question, k=5, filter=where_filter)

        if not results:
            return "No relevant events found in the event log archive."

        lines = ["Relevant events from the archive:"]
        for i, r in enumerate(results, 1):
            score = f"{r['score']:.2f}" if r.get("score") else "N/A"
            lines.append(f"  {i}. [score={score}] {r['text'][:200]}")

        return "\n".join(lines)

    except Exception as exc:
        logger.warning("RETRIEVER | Vector search failed | error=%s", exc)
        return "Vector search is currently unavailable."
