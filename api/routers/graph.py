"""
Artilery API — Neo4j Graph Data Router.

GET  /graph/services       — All services with dependencies
GET  /graph/teams           — All teams with members
GET  /graph/oncall          — On-call assignments
GET  /graph/full            — Full graph data for visualization
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from shared.neo4j_utils import Neo4jClient

logger = logging.getLogger("artilery.api.graph")

router = APIRouter(prefix="/graph")


@router.get("/full")
async def get_full_graph() -> dict[str, Any]:
    """Return the full Neo4j graph as nodes and edges for visualization."""
    neo4j = Neo4jClient()
    try:
        # Get all nodes
        nodes_result = neo4j.execute_query(
            "MATCH (n) RETURN elementId(n) AS id, labels(n) AS labels, properties(n) AS props"
        )

        # Get all relationships
        rels_result = neo4j.execute_query(
            "MATCH (a)-[r]->(b) RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type"
        )

        nodes = []
        for record in nodes_result:
            label = record["labels"][0] if record["labels"] else "Unknown"
            props = record["props"]
            name = props.get("name", props.get("title", f"Node-{record['id']}"))
            nodes.append({
                "id": str(record["id"]),
                "label": label,
                "name": name,
                "properties": {k: str(v) for k, v in props.items()},
            })

        edges = []
        for record in rels_result:
            edges.append({
                "source": str(record["source"]),
                "target": str(record["target"]),
                "type": record["type"],
            })

        return {"nodes": nodes, "edges": edges}
    except Exception as exc:
        logger.error("Graph full query failed: %s", exc)
        return {"nodes": [], "edges": [], "error": str(exc)}
    finally:
        neo4j.close()


@router.get("/services")
async def get_services() -> dict[str, Any]:
    """Return all services with their dependencies."""
    neo4j = Neo4jClient()
    try:
        services = neo4j.execute_query(
            """
            MATCH (s:Service)
            OPTIONAL MATCH (s)-[:DEPENDS_ON]->(dep:Service)
            OPTIONAL MATCH (d:Developer)-[:ON_CALL]->(s)
            OPTIONAL MATCH (t:Team)-[:OWNS]->(s)
            RETURN s.name AS name,
                   collect(DISTINCT dep.name) AS dependencies,
                   collect(DISTINCT d.name) AS oncall,
                   collect(DISTINCT t.name) AS teams
            """
        )
        # Remove null values from lists
        cleaned = []
        for r in services:
            cleaned.append({
                "name": r["name"],
                "dependencies": [d for d in r["dependencies"] if d],
                "oncall": [o for o in r["oncall"] if o],
                "teams": [t for t in r["teams"] if t],
            })
        return {"services": cleaned}
    except Exception as exc:
        logger.error("Services query failed: %s", exc)
        return {"services": [], "error": str(exc)}
    finally:
        neo4j.close()


@router.get("/teams")
async def get_teams() -> dict[str, Any]:
    """Return all teams with members and owned services."""
    neo4j = Neo4jClient()
    try:
        teams = neo4j.execute_query(
            """
            MATCH (t:Team)
            OPTIONAL MATCH (d:Developer)-[:MEMBER_OF]->(t)
            OPTIONAL MATCH (t)-[:OWNS]->(s:Service)
            RETURN t.name AS name,
                   collect(DISTINCT {name: d.name, email: d.email, role: d.role}) AS members,
                   collect(DISTINCT s.name) AS services
            """
        )
        cleaned = []
        for r in teams:
            cleaned.append({
                "name": r["name"],
                "members": [m for m in r["members"] if m.get("name")],
                "services": [s for s in r["services"] if s],
            })
        return {"teams": cleaned}
    except Exception as exc:
        logger.error("Teams query failed: %s", exc)
        return {"teams": [], "error": str(exc)}
    finally:
        neo4j.close()


@router.get("/oncall")
async def get_oncall() -> dict[str, Any]:
    """Return on-call assignments."""
    neo4j = Neo4jClient()
    try:
        oncall = neo4j.execute_query(
            """
            MATCH (d:Developer)-[:ON_CALL]->(s:Service)
            OPTIONAL MATCH (d)-[:MEMBER_OF]->(t:Team)
            RETURN d.name AS developer, d.email AS email,
                   s.name AS service, t.name AS team
            """
        )
        return {"oncall": [dict(r) for r in oncall]}
    except Exception as exc:
        logger.error("On-call query failed: %s", exc)
        return {"oncall": [], "error": str(exc)}
    finally:
        neo4j.close()
