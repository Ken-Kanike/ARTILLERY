"""
Artilery API — Chat Router.

POST /chat           — Ask the chatbot a question
GET  /chat/history   — Get chat history for a session
DELETE /chat/history — Clear chat history
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.chatbot.agent import ask
from shared.dynamo_utils import DynamoClient

logger = logging.getLogger("artilery.api.chat")

router = APIRouter(prefix="/chat")


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""
    query: str = Field(..., description="The user's question", min_length=1, max_length=2000)
    session_id: str = Field(default="default", description="Session ID for conversation history")
    history: Optional[list[dict[str, Any]]] = Field(default=None, description="Previous chat turns")


class ChatResponse(BaseModel):
    """Response body for the chat endpoint."""
    answer: str
    sources: list[str] = []
    intent: str = ""
    session_id: str = ""


class HistoryResponse(BaseModel):
    """Response body for the chat history endpoint."""
    session_id: str
    turns: list[dict[str, Any]] = []


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Ask the Artilery chatbot a question.

    Uses RAG over Neo4j knowledge graph, S3 event logs, and DynamoDB state
    to generate context-aware answers via AWS Bedrock.
    """
    logger.info("CHAT | query=%s | session=%s", request.query[:80], request.session_id)

    result = await ask(
        query=request.query,
        session_id=request.session_id,
        history=request.history,
    )

    return ChatResponse(
        answer=result["answer"],
        sources=result.get("sources", []),
        intent=result.get("intent", ""),
        session_id=result.get("session_id", request.session_id),
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(session_id: str = "default", limit: int = 20) -> HistoryResponse:
    """Retrieve chat history for a session."""
    dynamo = DynamoClient()
    turns = dynamo.get_chat_history(session_id, limit=limit)
    return HistoryResponse(session_id=session_id, turns=turns)


@router.delete("/history")
async def clear_history(session_id: str = "default") -> dict[str, str]:
    """Clear chat history for a session."""
    dynamo = DynamoClient()
    dynamo.delete_chat_history(session_id)
    return {"status": "cleared", "session_id": session_id}
