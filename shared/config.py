"""
Artilery Shared Configuration — Environment Variable Loading & Validation.

Uses Pydantic Settings to load, type-check, and validate all environment
variables required across the Artilery platform. Each variable is optional
at load time but validated at runtime via the validate() method so that
agents fail fast with descriptive errors rather than cryptic KeyErrors deep
in business logic.

Supports two modes:
  - LOCAL: Docker-based infra (Kafka, Neo4j, DynamoDB, LocalStack) — no cloud accounts
  - CLOUD: Confluent Cloud, Neo4j Aura, AWS, Jira, Notion, Slack

Usage:
    from shared.config import get_settings
    settings = get_settings()
    settings.validate()  # raises ValueError if required vars are missing
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("artilery.config")


class ArtilerySettings(BaseSettings):
    """Central configuration for all Artilery services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Mode ─────────────────────────────────────────────────────────────
    ARTILERY_ENV: str = Field(
        default="local",
        description="Environment mode: 'local' (Docker infra) or 'production' (cloud services)",
    )

    # ── Confluent Cloud (Kafka) — used in production mode ────────────────
    CONFLUENT_BOOTSTRAP_SERVERS: Optional[str] = Field(
        default=None,
        description="Confluent Cloud bootstrap servers (e.g. pkc-xxxxx.us-east-1.aws.confluent.cloud:9092)",
    )
    CONFLUENT_API_KEY: Optional[str] = Field(
        default=None,
        description="Confluent Cloud API key",
    )
    CONFLUENT_API_SECRET: Optional[str] = Field(
        default=None,
        description="Confluent Cloud API secret",
    )

    # ── Local Kafka ─────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = Field(
        default="localhost:9092",
        description="Local Kafka bootstrap servers (used when ARTILERY_ENV=local)",
    )

    # ── Neo4j AuraDB ────────────────────────────────────────────────────
    NEO4J_URI: Optional[str] = Field(
        default=None,
        description="Neo4j connection URI (e.g. neo4j+s://xxxx.databases.neo4j.io)",
    )
    NEO4J_USERNAME: Optional[str] = Field(
        default=None,
        description="Neo4j username",
    )
    NEO4J_PASSWORD: Optional[str] = Field(
        default=None,
        description="Neo4j password",
    )

    # ── AWS ──────────────────────────────────────────────────────────────
    AWS_ACCESS_KEY_ID: Optional[str] = Field(
        default=None,
        description="AWS IAM access key ID",
    )
    AWS_SECRET_ACCESS_KEY: Optional[str] = Field(
        default=None,
        description="AWS IAM secret access key",
    )
    AWS_REGION: str = Field(
        default="us-east-1",
        description="AWS region for all service calls",
    )
    AWS_BEDROCK_MODEL_ID: str = Field(
        default="anthropic.claude-3-sonnet-20240229-v1:0",
        description="AWS Bedrock model ID for AI diagnosis and chatbot",
    )

    # ── AWS S3 ───────────────────────────────────────────────────────────
    S3_BUCKET_NAME: Optional[str] = Field(
        default=None,
        description="S3 bucket name for event logs, deployment logs, and diagnoses",
    )

    # ── AWS DynamoDB ─────────────────────────────────────────────────────
    DYNAMODB_TABLE_NAME: Optional[str] = Field(
        default=None,
        description="DynamoDB table name prefix for state storage",
    )

    # ── Local Endpoints ──────────────────────────────────────────────────
    DYNAMODB_ENDPOINT_URL: Optional[str] = Field(
        default=None,
        description="DynamoDB endpoint URL (for local DynamoDB: http://localhost:8000)",
    )
    S3_ENDPOINT_URL: Optional[str] = Field(
        default=None,
        description="S3 endpoint URL (for LocalStack: http://localhost:4566)",
    )

    # ── Ollama (Local LLM) ──────────────────────────────────────────────
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        description="Ollama API base URL for local LLM inference",
    )
    OLLAMA_MODEL: str = Field(
        default="llama3.2",
        description="Ollama model name for local inference",
    )

    # ── Gemini (Local LLM — Free Tier) ──────────────────────────────────
    GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google Gemini API key (free from aistudio.google.com)",
    )
    GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model name",
    )

    # ── Slack ────────────────────────────────────────────────────────────
    SLACK_BOT_TOKEN: Optional[str] = Field(
        default=None,
        description="Slack Bot User OAuth Token (xoxb-...)",
    )

    # ── Jira ─────────────────────────────────────────────────────────────
    JIRA_URL: Optional[str] = Field(
        default=None,
        description="Jira instance URL (e.g. https://your-org.atlassian.net)",
    )
    JIRA_USERNAME: Optional[str] = Field(
        default=None,
        description="Jira username (email)",
    )
    JIRA_API_TOKEN: Optional[str] = Field(
        default=None,
        description="Jira API token",
    )
    JIRA_PROJECT_KEY: Optional[str] = Field(
        default=None,
        description="Jira project key (e.g. PROJ)",
    )

    # ── Notion ───────────────────────────────────────────────────────────
    NOTION_TOKEN: Optional[str] = Field(
        default=None,
        description="Notion internal integration token",
    )
    NOTION_DATABASE_ID: Optional[str] = Field(
        default=None,
        description="Notion database ID for ticket mirroring",
    )

    # ── GitHub ───────────────────────────────────────────────────────────
    GITHUB_WEBHOOK_SECRET: Optional[str] = Field(
        default=None,
        description="GitHub webhook HMAC secret for signature validation",
    )

    # ── Artilery Internal ────────────────────────────────────────────────
    DEFAULT_SLACK_CHANNEL: Optional[str] = Field(
        default=None,
        description="Fallback Slack channel ID when no on-call owner is found",
    )

    # ── Helpers ──────────────────────────────────────────────────────────

    @property
    def is_local(self) -> bool:
        """Check if running in local mode."""
        return self.ARTILERY_ENV == "local"

    def get_kafka_config(self) -> dict[str, str]:
        """Return Kafka connection config dict for producers/consumers.

        Local mode: plain TCP to localhost:9092 (Docker Kafka).
        Production: SASL_SSL to Confluent Cloud.
        """
        if self.is_local:
            return {
                "bootstrap.servers": self.KAFKA_BOOTSTRAP_SERVERS,
            }

        return {
            "bootstrap.servers": self.CONFLUENT_BOOTSTRAP_SERVERS or "",
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": self.CONFLUENT_API_KEY or "",
            "sasl.password": self.CONFLUENT_API_SECRET or "",
        }

    # ── Validation ───────────────────────────────────────────────────────

    # Variables required for the platform to function in production.
    _REQUIRED_VARS_PRODUCTION: list[str] = [
        "CONFLUENT_BOOTSTRAP_SERVERS",
        "CONFLUENT_API_KEY",
        "CONFLUENT_API_SECRET",
    ]

    # Local mode only needs Docker running — no cloud vars required.
    _REQUIRED_VARS_LOCAL: list[str] = []

    # Variables required per agent (checked contextually).
    _AGENT_REQUIRED: dict[str, list[str]] = {
        "triage": [
            "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
        ],
        "review": [
            "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
        ],
        "ops": [],
        "chatbot": [
            "NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD",
        ],
    }

    def validate(self, agent: str | None = None) -> None:
        """Validate that all required environment variables are set.

        Args:
            agent: Optional agent name to validate agent-specific vars.
                   One of: 'triage', 'review', 'ops', 'chatbot'.

        Raises:
            ValueError: With a descriptive message listing all missing vars.
        """
        missing: list[str] = []

        # Check platform-level requirements based on mode.
        required = self._REQUIRED_VARS_LOCAL if self.is_local else self._REQUIRED_VARS_PRODUCTION
        for var_name in required:
            if getattr(self, var_name, None) is None:
                missing.append(var_name)

        # Check agent-specific requirements (only in production mode).
        if not self.is_local and agent and agent in self._AGENT_REQUIRED:
            for var_name in self._AGENT_REQUIRED[agent]:
                if getattr(self, var_name, None) is None:
                    missing.append(var_name)

        if missing:
            missing_list = "\n  - ".join(missing)
            raise ValueError(
                f"Artilery configuration error — the following required "
                f"environment variables are missing or empty:\n  - {missing_list}\n\n"
                f"Copy .env.example to .env and fill in the values. "
                f"See README.md for credential setup instructions."
            )

        logger.info(
            "Configuration validated | mode=%s%s",
            self.ARTILERY_ENV,
            f" | agent={agent}" if agent else "",
        )


@lru_cache(maxsize=1)
def get_settings() -> ArtilerySettings:
    """Return a cached singleton of ArtilerySettings.

    The settings object is created once and reused for the lifetime of the
    process. Uses lru_cache to avoid re-reading .env on every call.
    """
    return ArtilerySettings()
