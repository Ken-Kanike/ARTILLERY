"""
Artilery Chatbot — Intent Classifier.

Uses AWS Bedrock to classify user questions into structured intents
with entity extraction and data source routing.

Includes in-memory TTL cache (60s) and keyword-based fallback.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.chatbot.intent_classifier")

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 60

DATA_SOURCE_MAP: dict[str, str] = {
    "service_owner": "neo4j",
    "pr_status": "dynamo",
    "deployment_history": "vector_search",
    "on_call": "neo4j",
    "team_info": "neo4j",
    "recent_issues": "vector_search",
    "general": "vector_search",
}

KEYWORD_MAP: dict[str, list[str]] = {
    "service_owner": ["who owns", "owner of", "who is responsible"],
    "pr_status": ["pr #", "pull request", "pr status"],
    "deployment_history": ["deploy", "rollback", "failure", "why did"],
    "on_call": ["on-call", "on call", "who is on call"],
    "team_info": ["team", "members", "who is on team"],
    "recent_issues": ["recent bugs", "recent issues", "issues for"],
}


def _get_from_cache(key: str) -> Optional[dict[str, Any]]:
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return val
        del _cache[key]
    return None


def _extract_entities(question: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    svc = re.search(r"\b([A-Z][a-z]+(?:[A-Z][a-z]+)+)\b", question)
    if svc:
        entities["service_name"] = svc.group(1)
    pr = re.search(r"#?(\d+)", question)
    if pr:
        entities["pr_number"] = int(pr.group(1))
    team = re.search(r"(?:team\s+)(\w+)", question, re.IGNORECASE)
    if team:
        entities["team_name"] = team.group(1)
    days = re.search(r"last\s+(\d+)\s+days?", question, re.IGNORECASE)
    if days:
        entities["days"] = int(days.group(1))
    dep = re.search(r"d-[A-Z0-9]+", question, re.IGNORECASE)
    if dep:
        entities["deployment_id"] = dep.group(0)
    return entities


def _classify_by_keywords(question: str) -> dict[str, Any]:
    q = question.lower()
    for intent, kws in KEYWORD_MAP.items():
        if any(kw in q for kw in kws):
            return {"intent": intent, "entities": _extract_entities(question), "data_source": DATA_SOURCE_MAP[intent]}
    return {"intent": "general", "entities": _extract_entities(question), "data_source": "vector_search"}


CLASSIFICATION_PROMPT = (
    "You are an intent classifier for Artilery, a DevOps CI/CD assistant.\n"
    "Classify the question into: service_owner, pr_status, deployment_history, "
    "on_call, team_info, recent_issues, or general.\n"
    "Extract entities: service_name, pr_number, team_name, days, deployment_id.\n"
    "Respond ONLY with JSON: {\"intent\": \"...\", \"entities\": {...}, \"data_source\": \"neo4j|dynamo|vector_search\"}\n\n"
    "Question: "
)


async def classify_intent(question: str) -> dict[str, Any]:
    """Classify user question intent. Uses Bedrock with keyword fallback."""
    cached = _get_from_cache(question)
    if cached:
        return cached
    try:
        result = await _classify_with_bedrock(question)
        _cache[question] = (time.time(), result)
        logger.info("INTENT | Bedrock | q=%s | intent=%s", question[:50], result["intent"])
        return result
    except Exception as exc:
        logger.warning("INTENT | Fallback | error=%s", exc)
        result = _classify_by_keywords(question)
        _cache[question] = (time.time(), result)
        return result


async def _classify_with_bedrock(question: str) -> dict[str, Any]:
    from shared.llm import invoke_llm
    response = await invoke_llm(
        prompt=CLASSIFICATION_PROMPT + question,
        system="You are an intent classifier. Respond ONLY with valid JSON.",
        max_tokens=256,
        temperature=0.1,
    )
    parsed = json.loads(response)
    intent = parsed.get("intent", "general")
    if intent not in DATA_SOURCE_MAP:
        intent = "general"
    return {
        "intent": intent,
        "entities": parsed.get("entities", {}),
        "data_source": parsed.get("data_source", DATA_SOURCE_MAP.get(intent, "vector_search")),
    }
