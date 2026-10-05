#!/usr/bin/env python3
"""
Artilery — Neo4j Seed Script.

Populates the Neo4j graph database with realistic dummy organization data
for development and testing. Uses MERGE statements for idempotency —
safe to run multiple times without creating duplicates.

Schema:
  (:Developer {id, name, slack_user_id, email, jira_account_id})
  (:Team {id, name, slack_channel_id})
  (:Service {id, name, repo_url, jira_component})
  (:Skill {name})
  (:Developer)-[:MEMBER_OF]->(:Team)
  (:Developer)-[:ON_CALL {start_date, end_date}]->(:Service)
  (:Developer)-[:HAS_SKILL]->(:Skill)
  (:Team)-[:OWNS]->(:Service)
  (:Service)-[:DEPENDS_ON]->(:Service)

Usage:
    python -m scripts.seed_neo4j
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone

from shared.config import get_settings

logger = logging.getLogger("artilery.scripts.seed_neo4j")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

# ── Seed Data ────────────────────────────────────────────────────────────────

TEAMS = [
    {"id": "team-backend", "name": "Backend", "slack_channel_id": "C0AS97KE5QA"},
    {"id": "team-platform", "name": "Platform", "slack_channel_id": "C0AS97KE5QA"},
    {"id": "team-frontend", "name": "Frontend", "slack_channel_id": "C0AS97KE5QA"},
]

DEVELOPERS = [
    {"id": "dev-001", "name": "Swarnim Bane", "slack_user_id": "U0ARTPL5MPH", "email": "swarnim.bane@company.com", "jira_account_id": "jira-swarnim-001", "team": "Backend", "skills": ["Python", "Kafka", "PostgreSQL"]},
    {"id": "dev-002", "name": "Arjun Mehta", "slack_user_id": "U0ARTPL5MPH", "email": "arjun.mehta@company.com", "jira_account_id": "jira-arjun-002", "team": "Backend", "skills": ["Python", "Java", "Redis"]},
    {"id": "dev-003", "name": "Priya Sharma", "slack_user_id": "U0ARTPL5MPH", "email": "priya.sharma@company.com", "jira_account_id": "jira-priya-003", "team": "Platform", "skills": ["DevOps", "Terraform", "AWS", "Python"]},
    {"id": "dev-004", "name": "Rohan Desai", "slack_user_id": "U0ARTPL5MPH", "email": "rohan.desai@company.com", "jira_account_id": "jira-rohan-004", "team": "Platform", "skills": ["DevOps", "Kubernetes", "Go"]},
    {"id": "dev-005", "name": "Ananya Iyer", "slack_user_id": "U0ARTPL5MPH", "email": "ananya.iyer@company.com", "jira_account_id": "jira-ananya-005", "team": "Frontend", "skills": ["TypeScript", "React", "GraphQL"]},
    {"id": "dev-006", "name": "Vikram Joshi", "slack_user_id": "U0ARTPL5MPH", "email": "vikram.joshi@company.com", "jira_account_id": "jira-vikram-006", "team": "Frontend", "skills": ["TypeScript", "Vue", "CSS"]},
    {"id": "dev-007", "name": "Neha Kulkarni", "slack_user_id": "U0ARTPL5MPH", "email": "neha.kulkarni@company.com", "jira_account_id": "jira-neha-007", "team": "Backend", "skills": ["Python", "Java", "Kafka", "DevOps"]},
    {"id": "dev-008", "name": "Aditya Patel", "slack_user_id": "U0ARTPL5MPH", "email": "aditya.patel@company.com", "jira_account_id": "jira-aditya-008", "team": "Platform", "skills": ["DevOps", "AWS", "Python", "Terraform"]},
]

SERVICES = [
    {"id": "svc-payment", "name": "PaymentService", "repo_url": "https://github.com/company/payment-service", "jira_component": "Payments", "owner_team": "Backend"},
    {"id": "svc-auth", "name": "AuthService", "repo_url": "https://github.com/company/auth-service", "jira_component": "Authentication", "owner_team": "Backend"},
    {"id": "svc-notification", "name": "NotificationService", "repo_url": "https://github.com/company/notification-service", "jira_component": "Notifications", "owner_team": "Platform"},
    {"id": "svc-gateway", "name": "APIGateway", "repo_url": "https://github.com/company/api-gateway", "jira_component": "Gateway", "owner_team": "Platform"},
    {"id": "svc-user", "name": "UserService", "repo_url": "https://github.com/company/user-service", "jira_component": "Users", "owner_team": "Frontend"},
]

# On-call: 1 developer per service (current rotation)
ON_CALL_ASSIGNMENTS = [
    {"developer_id": "dev-001", "service_name": "PaymentService"},
    {"developer_id": "dev-002", "service_name": "AuthService"},
    {"developer_id": "dev-003", "service_name": "NotificationService"},
    {"developer_id": "dev-004", "service_name": "APIGateway"},
    {"developer_id": "dev-005", "service_name": "UserService"},
]

SERVICE_DEPENDENCIES = [
    {"from": "APIGateway", "to": "AuthService"},
    {"from": "APIGateway", "to": "PaymentService"},
    {"from": "APIGateway", "to": "UserService"},
    {"from": "PaymentService", "to": "AuthService"},
    {"from": "NotificationService", "to": "UserService"},
]


def seed(uri: str, username: str, password: str) -> None:
    """Populate the Neo4j database with seed data."""
    from neo4j import GraphDatabase

    now = datetime.now(timezone.utc)
    on_call_start = (now - timedelta(days=3)).strftime("%Y-%m-%d")
    on_call_end = (now + timedelta(days=4)).strftime("%Y-%m-%d")

    driver = GraphDatabase.driver(uri, auth=(username, password))

    with driver.session() as session:
        # Create constraints for idempotency
        for label in ["Developer", "Team", "Service", "Skill"]:
            try:
                session.run(f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.id IS UNIQUE")
            except Exception:
                pass  # Constraint may already exist in community edition

        # Teams
        for team in TEAMS:
            session.run(
                "MERGE (t:Team {id: $id}) SET t.name = $name, t.slack_channel_id = $slack_channel_id",
                team,
            )
        logger.info("Created %d teams", len(TEAMS))

        # Developers + team membership + skills
        for dev in DEVELOPERS:
            session.run(
                "MERGE (d:Developer {id: $id}) "
                "SET d.name = $name, d.slack_user_id = $slack_user_id, "
                "d.email = $email, d.jira_account_id = $jira_account_id",
                dev,
            )
            session.run(
                "MATCH (d:Developer {id: $dev_id}), (t:Team {name: $team_name}) "
                "MERGE (d)-[:MEMBER_OF]->(t)",
                {"dev_id": dev["id"], "team_name": dev["team"]},
            )
            for skill in dev["skills"]:
                session.run(
                    "MERGE (s:Skill {name: $skill_name}) "
                    "WITH s "
                    "MATCH (d:Developer {id: $dev_id}) "
                    "MERGE (d)-[:HAS_SKILL]->(s)",
                    {"dev_id": dev["id"], "skill_name": skill},
                )
        logger.info("Created %d developers with skills and team memberships", len(DEVELOPERS))

        # Services + team ownership
        for svc in SERVICES:
            session.run(
                "MERGE (s:Service {id: $id}) "
                "SET s.name = $name, s.repo_url = $repo_url, s.jira_component = $jira_component",
                svc,
            )
            session.run(
                "MATCH (t:Team {name: $team_name}), (s:Service {id: $svc_id}) "
                "MERGE (t)-[:OWNS]->(s)",
                {"team_name": svc["owner_team"], "svc_id": svc["id"]},
            )
        logger.info("Created %d services with team ownership", len(SERVICES))

        # On-call assignments
        for assignment in ON_CALL_ASSIGNMENTS:
            session.run(
                "MATCH (d:Developer {id: $dev_id}), (s:Service {name: $svc_name}) "
                "MERGE (d)-[r:ON_CALL]->(s) "
                "SET r.start_date = $start, r.end_date = $end",
                {
                    "dev_id": assignment["developer_id"],
                    "svc_name": assignment["service_name"],
                    "start": on_call_start,
                    "end": on_call_end,
                },
            )
        logger.info("Created %d on-call assignments", len(ON_CALL_ASSIGNMENTS))

        # Service dependencies
        for dep in SERVICE_DEPENDENCIES:
            session.run(
                "MATCH (a:Service {name: $from_svc}), (b:Service {name: $to_svc}) "
                "MERGE (a)-[:DEPENDS_ON]->(b)",
                {"from_svc": dep["from"], "to_svc": dep["to"]},
            )
        logger.info("Created %d service dependencies", len(SERVICE_DEPENDENCIES))

        # Print summary
        result = session.run(
            "MATCH (d:Developer) RETURN count(d) AS devs "
            "UNION ALL MATCH (t:Team) RETURN count(t) AS devs "
            "UNION ALL MATCH (s:Service) RETURN count(s) AS devs "
            "UNION ALL MATCH (sk:Skill) RETURN count(sk) AS devs"
        )
        counts = [r["devs"] for r in result]

    driver.close()

    logger.info("=" * 50)
    logger.info("SEED COMPLETE")
    logger.info("  Developers: %d", counts[0] if len(counts) > 0 else 0)
    logger.info("  Teams: %d", counts[1] if len(counts) > 1 else 0)
    logger.info("  Services: %d", counts[2] if len(counts) > 2 else 0)
    logger.info("  Skills: %d", counts[3] if len(counts) > 3 else 0)
    logger.info("=" * 50)


def main() -> None:
    """Entry point for the seed script."""
    settings = get_settings()
    if not all([settings.NEO4J_URI, settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD]):
        logger.error("NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD must be set in .env")
        sys.exit(1)

    logger.info("Seeding Neo4j at %s ...", settings.NEO4J_URI)
    seed(settings.NEO4J_URI, settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)


if __name__ == "__main__":
    main()
