"""
Artilery Shared Neo4j Utilities — Graph Database Query Helpers.

Provides a Neo4jClient class for executing Cypher queries against
Neo4j AuraDB. Used by the Triage Agent (owner lookup), Review Agent
(reviewer assignment), and Chatbot Agent (knowledge graph queries).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.neo4j")


class Neo4jClient:
    """Neo4j AuraDB client with connection pooling and query execution."""

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self._uri = uri or settings.NEO4J_URI
        self._username = username or settings.NEO4J_USERNAME
        self._password = password or settings.NEO4J_PASSWORD
        self._driver: Any = None
        logger.info("Neo4jClient initialized | uri=%s", self._uri)

    def __enter__(self) -> Neo4jClient:
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def connect(self) -> None:
        """Establish connection to Neo4j."""
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(
            self._uri,
            auth=(self._username, self._password),
        )
        logger.info("Neo4j connection established")

    def close(self) -> None:
        """Close the Neo4j driver."""
        if self._driver:
            self._driver.close()
            logger.info("Neo4j connection closed")

    def _ensure_connected(self) -> None:
        """Ensure the driver is connected."""
        if self._driver is None:
            self.connect()

    def execute_query(self, query: str, params: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
        """Execute a Cypher query and return results as list of dicts."""
        self._ensure_connected()
        with self._driver.session() as session:
            result = session.run(query, parameters=params or {})
            return [record.data() for record in result]

    def get_service_owner(self, service_name: str) -> dict[str, Any]:
        """Find the on-call developer for a service.

        Primary: Developer currently ON_CALL for the Service.
        Fallback: First MEMBER_OF the team that OWNS the service (team lead).

        Returns dict with: developer_name, developer_id, slack_user_id,
                          jira_account_id, email, team_name, slack_channel_id
        """
        self._ensure_connected()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Primary: on-call developer
        on_call_query = """
        MATCH (d:Developer)-[r:ON_CALL]->(s:Service {name: $service_name})
        WHERE r.start_date <= $today AND r.end_date >= $today
        MATCH (d)-[:MEMBER_OF]->(t:Team)-[:OWNS]->(s)
        RETURN d.name AS developer_name, d.id AS developer_id,
               d.slack_user_id AS slack_user_id, d.jira_account_id AS jira_account_id,
               d.email AS email, t.name AS team_name, t.slack_channel_id AS slack_channel_id
        LIMIT 1
        """
        results = self.execute_query(on_call_query, {"service_name": service_name, "today": today})
        if results:
            logger.info("Found on-call owner for %s: %s", service_name, results[0]["developer_name"])
            return results[0]

        # Fallback: team lead (first member of owning team)
        fallback_query = """
        MATCH (t:Team)-[:OWNS]->(s:Service {name: $service_name})
        MATCH (d:Developer)-[:MEMBER_OF]->(t)
        RETURN d.name AS developer_name, d.id AS developer_id,
               d.slack_user_id AS slack_user_id, d.jira_account_id AS jira_account_id,
               d.email AS email, t.name AS team_name, t.slack_channel_id AS slack_channel_id
        LIMIT 1
        """
        results = self.execute_query(fallback_query, {"service_name": service_name})
        if results:
            logger.warning("No on-call for %s, falling back to team lead: %s", service_name, results[0]["developer_name"])
            return results[0]

        logger.error("No owner found for service: %s", service_name)
        return {}

    def get_reviewer_for_service(
        self,
        service_name: str,
        exclude_developer_id: str,
        file_extensions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Find the best reviewer for a service, excluding the PR author.

        Scoring:
        1. Developers with skills matching the file types (+2 per match)
        2. Developers NOT currently on-call (+1, they have bandwidth)
        3. Developers with more ON_CALL history (+1 per past rotation = seniority)
        """
        self._ensure_connected()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Map file extensions to skill names
        ext_to_skill: dict[str, str] = {
            ".py": "Python", ".java": "Java", ".go": "Go",
            ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "TypeScript",
            ".tf": "DevOps", ".yml": "DevOps", ".yaml": "DevOps",
            ".Dockerfile": "DevOps", ".css": "CSS", ".graphql": "GraphQL",
        }
        required_skills: list[str] = []
        if file_extensions:
            for ext in file_extensions:
                skill = ext_to_skill.get(ext)
                if skill and skill not in required_skills:
                    required_skills.append(skill)

        query = """
        MATCH (t:Team)-[:OWNS]->(s:Service {name: $service_name})
        MATCH (d:Developer)-[:MEMBER_OF]->(t)
        WHERE d.id <> $exclude_id
        OPTIONAL MATCH (d)-[:HAS_SKILL]->(sk:Skill)
        WHERE sk.name IN $required_skills
        OPTIONAL MATCH (d)-[oc:ON_CALL]->(any_svc:Service)
        WHERE oc.start_date <= $today AND oc.end_date >= $today
        WITH d, t,
             count(DISTINCT sk) AS skill_matches,
             count(DISTINCT oc) AS active_on_calls
        OPTIONAL MATCH (d)-[hist:ON_CALL]->(:Service)
        WITH d, t, skill_matches, active_on_calls,
             count(DISTINCT hist) AS on_call_history
        RETURN d.name AS reviewer_name, d.id AS reviewer_id,
               d.slack_user_id AS reviewer_slack_id,
               d.jira_account_id AS reviewer_jira_id,
               d.email AS reviewer_email,
               t.name AS team_name,
               skill_matches * 2 + CASE WHEN active_on_calls = 0 THEN 1 ELSE 0 END + on_call_history AS score
        ORDER BY score DESC
        LIMIT 1
        """
        results = self.execute_query(query, {
            "service_name": service_name,
            "exclude_id": exclude_developer_id,
            "required_skills": required_skills or ["Python"],
            "today": today,
        })
        if results:
            logger.info("Assigned reviewer for %s: %s (score=%d)", service_name, results[0]["reviewer_name"], results[0]["score"])
            return results[0]

        logger.warning("No reviewer found for service: %s", service_name)
        return {}

    def get_team_members(self, team_name: str) -> list[dict[str, Any]]:
        """Get all members of a team."""
        return self.execute_query(
            "MATCH (d:Developer)-[:MEMBER_OF]->(t:Team {name: $team}) RETURN d.name AS name, d.slack_user_id AS slack_user_id, d.email AS email",
            {"team": team_name},
        )

    def get_on_call(self, service_name: str) -> dict[str, Any]:
        """Get the current on-call developer for a service."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        results = self.execute_query(
            "MATCH (d:Developer)-[r:ON_CALL]->(s:Service {name: $svc}) WHERE r.start_date <= $today AND r.end_date >= $today RETURN d.name AS name, d.slack_user_id AS slack_user_id, r.start_date AS start_date, r.end_date AS end_date",
            {"svc": service_name, "today": today},
        )
        return results[0] if results else {}

    def health_check(self) -> bool:
        """Verify Neo4j connectivity."""
        try:
            self.execute_query("RETURN 1 AS ok")
            return True
        except Exception as exc:
            logger.error("Neo4j health check failed | error=%s", exc)
            return False
