"""
Artilery Shared LLM Utilities — Unified LLM Interface.

Provides a unified interface for LLM inference that automatically
routes between:
  - Google Gemini 2.5 Flash (primary — free API tier)
  - AWS Bedrock (production mode)
  - Ollama (fallback if Gemini key not set)

This ensures agents work identically in both modes.

Usage:
    from shared.llm import invoke_llm

    response = await invoke_llm(
        prompt="Classify this bug...",
        system="You are a triage assistant.",
        max_tokens=1024,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from shared.config import get_settings

logger = logging.getLogger("artilery.llm")


async def invoke_llm(
    prompt: str,
    system: Optional[str] = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str:
    """Invoke the configured LLM.

    Routing priority:
      1. Gemini 2.5 Flash (if GEMINI_API_KEY is set)
      2. Bedrock (if production mode)
      3. Ollama (local fallback)

    Args:
        prompt: The user prompt / main instruction.
        system: Optional system prompt for role/behavior framing.
        max_tokens: Maximum response tokens.
        temperature: Sampling temperature.

    Returns:
        The LLM response text.
    """
    settings = get_settings()

    # Priority 1: Gemini (free, fast, works everywhere)
    if settings.GEMINI_API_KEY:
        return await _invoke_gemini(prompt, system, max_tokens, temperature)

    # Priority 2: Bedrock (production)
    if not settings.is_local:
        return await _invoke_bedrock(prompt, system, max_tokens, temperature)

    # Priority 3: Ollama (local fallback)
    return await _invoke_ollama(prompt, system, max_tokens, temperature)


async def _invoke_gemini(
    prompt: str,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
) -> str:
    """Invoke Google Gemini 2.5 Flash via the google-genai SDK."""
    from google import genai
    from google.genai import types

    settings = get_settings()
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    # Build the full prompt with system instruction prepended
    full_prompt = prompt
    if system:
        full_prompt = f"{system}\n\n{prompt}"

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(
                max_output_tokens=max_tokens,
                temperature=temperature,
            ),
        )
        result = response.text or ""
        logger.info(
            "LLM | gemini | model=%s | prompt_len=%d | response_len=%d",
            settings.GEMINI_MODEL, len(full_prompt), len(result),
        )
        return result
    except Exception as exc:
        logger.error("LLM | Gemini error: %s", exc)
        # Fall back to Ollama if Gemini fails
        logger.info("LLM | Falling back to Ollama...")
        return await _invoke_ollama(prompt, system, max_tokens, temperature)


async def _invoke_ollama(
    prompt: str,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
) -> str:
    """Invoke Ollama local LLM."""
    import httpx

    settings = get_settings()
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"

    payload: dict[str, Any] = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    if system:
        payload["system"] = system

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            result = data.get("response", "")
            logger.info(
                "LLM | ollama | model=%s | prompt_len=%d | response_len=%d",
                settings.OLLAMA_MODEL, len(prompt), len(result),
            )
            return result
    except httpx.ConnectError:
        logger.warning(
            "LLM | Ollama not running at %s — returning fallback response.",
            settings.OLLAMA_BASE_URL,
        )
        return _fallback_response(prompt)
    except Exception as exc:
        logger.error("LLM | Ollama error: %s", exc)
        return _fallback_response(prompt)


async def _invoke_bedrock(
    prompt: str,
    system: Optional[str],
    max_tokens: int,
    temperature: float,
) -> str:
    """Invoke AWS Bedrock Claude."""
    import boto3

    settings = get_settings()
    client = boto3.client(
        "bedrock-runtime",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )

    messages = [{"role": "user", "content": prompt}]
    body: dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }
    if system:
        body["system"] = system

    response = client.invoke_model(
        modelId=settings.AWS_BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    logger.info(
        "LLM | bedrock | model=%s | prompt_len=%d | response_len=%d",
        settings.AWS_BEDROCK_MODEL_ID, len(prompt), len(text),
    )
    return text


def _fallback_response(prompt: str) -> str:
    """Generate a structured fallback when no LLM is available.

    This ensures agents don't crash — they produce a reasonable
    placeholder response that can be reviewed.
    """
    prompt_lower = prompt.lower()

    # Intent classification fallback
    if "classify" in prompt_lower and "intent" in prompt_lower:
        return "general"

    # Bug diagnosis fallback
    if "diagnose" in prompt_lower or "root cause" in prompt_lower:
        return json.dumps({
            "root_cause": "Automated diagnosis unavailable — LLM not configured",
            "remediation": "Manual investigation required",
            "confidence": 0.1,
            "auto_fixable": False,
            "severity": "unknown",
        })

    # Default
    return (
        "I'm running in local mode without an LLM backend. "
        "To enable AI responses, either:\n"
        "1. Set GEMINI_API_KEY in .env (free from https://aistudio.google.com/apikey)\n"
        "2. Install Ollama (https://ollama.com) and run: ollama pull llama3.2\n"
        "3. Configure AWS Bedrock credentials in .env\n\n"
        f"Your query: {prompt[:200]}"
    )
