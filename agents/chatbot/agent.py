"""
Artilery Chatbot Agent — RAG-Powered Knowledge Q&A.

Provides conversational Q&A over:
1. Neo4j knowledge graph (team structure, service ownership, on-call)
2. S3 event logs (deployment history, triage decisions) via ChromaDB
3. DynamoDB state (PR status, agent checkpoints)

Uses AWS Bedrock for LLM inference, intent classification, and synthesis.
Hybrid retrieval: intent-based routing to structured + vector data sources.

Entrypoint: python -m agents.chatbot.agent
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.chatbot import intent_classifier, retrievers
from agents.chatbot import tools as chat_tools
from shared.config import get_settings
from shared.dynamo_utils import DynamoClient

logger = logging.getLogger("artilery.chatbot.agent")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


class ChatState(TypedDict):
    session_id: str
    user_query: str
    intent: dict[str, Any]
    context: list[dict[str, Any]]
    retrieved_context: str
    neo4j_results: list[dict[str, Any]]
    s3_events: list[dict[str, Any]]
    dynamo_state: dict[str, Any]
    answer: str
    sources: list[str]
    error: Optional[str]


# ── Nodes ────────────────────────────────────────────────────────────────────

async def classify_node(state: ChatState) -> ChatState:
    """Classify the user's intent using Bedrock with keyword fallback."""
    logger.info("CHATBOT | Classifying intent | query=%s", state["user_query"][:80])
    try:
        intent_result = await intent_classifier.classify_intent(state["user_query"])
    except Exception as exc:
        logger.warning("CHATBOT | Intent classification failed: %s", exc)
        intent_result = {"intent": "general", "entities": {}, "data_source": "vector_search"}

    logger.info("CHATBOT | Intent: %s | data_source=%s", intent_result["intent"], intent_result["data_source"])
    return {**state, "intent": intent_result}


async def retrieve_node(state: ChatState) -> ChatState:
    """Route to correct retriever(s) based on intent data_source."""
    logger.info("CHATBOT | Retrieving context...")
    intent_info = state["intent"]
    data_source = intent_info.get("data_source", "vector_search")
    intent = intent_info.get("intent", "general")
    entities = intent_info.get("entities", {})
    query = state["user_query"]

    context_parts: list[str] = []
    sources: list[str] = []

    try:
        # Structured sources (Neo4j / DynamoDB)
        if data_source == "neo4j":
            neo4j_text = await retrievers.retrieve_from_neo4j(query, intent, entities)
            if neo4j_text:
                context_parts.append(neo4j_text)
                sources.append("Neo4j Knowledge Graph")

        elif data_source == "dynamo":
            dynamo_text = await retrievers.retrieve_from_dynamo(query, intent, entities)
            if dynamo_text:
                context_parts.append(dynamo_text)
                sources.append("DynamoDB State Store")

        # Vector search — always add for deployment/issue queries
        if data_source == "vector_search" or intent in ("deployment_history", "recent_issues", "general"):
            vector_text = await retrievers.retrieve_from_vector_store(query, entities)
            if vector_text and "No relevant events" not in vector_text:
                context_parts.append(vector_text)
                sources.append("ChromaDB Event Archive")

    except Exception as exc:
        logger.warning("CHATBOT | Retrieval error: %s", exc)

    retrieved = "\n\n".join(context_parts) if context_parts else "No specific context available."
    return {**state, "retrieved_context": retrieved, "sources": sources}


async def generate_answer_node(state: ChatState) -> ChatState:
    """Generate answer using Bedrock with retrieved context."""
    logger.info("CHATBOT | Generating answer with Bedrock...")
    try:
        answer, extra_sources = await chat_tools.generate_answer(
            query=state["user_query"],
            neo4j_context=state.get("neo4j_results", []),
            event_context=state.get("s3_events", []),
            state_context=state.get("dynamo_state", {}),
            chat_history=state.get("context", []),
            retrieved_text=state.get("retrieved_context", ""),
        )
        sources = list(set(state.get("sources", []) + extra_sources))
        return {**state, "answer": answer, "sources": sources, "error": None}
    except Exception as exc:
        logger.error("CHATBOT | Answer generation failed: %s", exc)
        # Fallback: return retrieved context directly
        ctx = state.get("retrieved_context", "")
        if ctx and ctx != "No specific context available.":
            return {**state, "answer": f"Based on available data:\n\n{ctx}", "error": None}
        return {**state, "answer": f"I encountered an error: {str(exc)[:100]}. Please try again.", "error": str(exc)}


async def format_response_node(state: ChatState) -> ChatState:
    """Format the answer into clean markdown with source citations."""
    answer = state["answer"]
    sources = state.get("sources", [])

    if sources:
        citation = "\n\n---\n📚 **Sources:** " + ", ".join(sources)
        answer = answer.rstrip() + citation

    return {**state, "answer": answer}


async def save_history_node(state: ChatState) -> ChatState:
    """Save the conversation turn to DynamoDB."""
    try:
        dynamo = DynamoClient()
        dynamo.save_chat_turn(state["session_id"], "user", state["user_query"])
        dynamo.save_chat_turn(state["session_id"], "assistant", state["answer"])
    except Exception as exc:
        logger.warning("CHATBOT | Failed to save history: %s", exc)
    return state


# ── Graph ────────────────────────────────────────────────────────────────────

def compile() -> Any:
    graph = StateGraph(ChatState)

    graph.add_node("classify", classify_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("format_response", format_response_node)
    graph.add_node("save_history", save_history_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "retrieve")
    graph.add_edge("retrieve", "generate_answer")
    graph.add_edge("generate_answer", "format_response")
    graph.add_edge("format_response", "save_history")
    graph.add_edge("save_history", END)

    return graph.compile()


async def ask(
    query: str,
    session_id: str = "default",
    history: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Run the chatbot agent with a user query.

    Returns dict with {answer, sources, intent, session_id}.
    """
    initial: ChatState = {
        "session_id": session_id,
        "user_query": query,
        "intent": {},
        "context": history or [],
        "retrieved_context": "",
        "neo4j_results": [],
        "s3_events": [],
        "dynamo_state": {},
        "answer": "",
        "sources": [],
        "error": None,
    }

    app = compile()
    result = await app.ainvoke(initial)

    return {
        "answer": result["answer"],
        "sources": result["sources"],
        "intent": result["intent"].get("intent", "") if isinstance(result["intent"], dict) else result["intent"],
        "session_id": session_id,
    }


# Keep backward compat for classify_intent used in tests
def classify_intent(query: str) -> str:
    """Simple keyword-based intent classifier (backward compat)."""
    result = intent_classifier._classify_by_keywords(query)
    return result["intent"]
