#!/usr/bin/env python3
"""
Artilery — AWS Lambda Packaging Script.

Creates deployment ZIP packages for each agent and the FastAPI API.
Each package includes: shared/ + agents/{name}/ + lambda_function.py wrapper.

Output: dist/{agent_name}.zip

Usage:
    python -m scripts.package_lambda
    python -m scripts.package_lambda --agent triage
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

logger = logging.getLogger("artilery.scripts.package_lambda")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

PROJECT_ROOT = Path(__file__).parent.parent
DIST_DIR = PROJECT_ROOT / "dist"

AGENTS = {
    "triage": {
        "dirs": ["shared", "agents/__init__.py", "agents/triage"],
        "handler": "lambda_function.handler",
        "cmd": "python -m agents.triage.agent",
    },
    "review": {
        "dirs": ["shared", "agents/__init__.py", "agents/review"],
        "handler": "lambda_function.handler",
        "cmd": "python -m agents.review.agent",
    },
    "ops": {
        "dirs": ["shared", "agents/__init__.py", "agents/ops"],
        "handler": "lambda_function.handler",
        "cmd": "python -m agents.ops.agent",
    },
    "chatbot": {
        "dirs": ["shared", "agents/__init__.py", "agents/chatbot"],
        "handler": "lambda_function.handler",
        "cmd": "python -m agents.chatbot.agent",
    },
    "api": {
        "dirs": ["shared", "agents", "api", "lambda_functions"],
        "handler": "lambda_function.handler",
        "cmd": "uvicorn api.main:app",
    },
}

LAMBDA_WRAPPER_TEMPLATE = '''"""
Artilery — Lambda Function Entry Point for {agent_name}.

Routes events from Kafka MSK triggers or API Gateway to the appropriate agent.
"""

import json
import logging

logger = logging.getLogger("artilery.lambda.{agent_name}")
logging.basicConfig(level=logging.INFO)

{agent_import}


def handler(event, context):
    """AWS Lambda handler."""
    logger.info("Lambda invoked | agent={agent_name} | source=%s", event.get("source", "unknown"))

    # API Gateway → FastAPI (Mangum)
    if "httpMethod" in event or "requestContext" in event:
        from mangum import Mangum
        from api.main import app
        mangum_handler = Mangum(app)
        return mangum_handler(event, context)

    # Kafka MSK trigger → process records
    if "records" in event:
        for topic, messages in event["records"].items():
            for msg in messages:
                try:
                    value = json.loads(msg.get("value", "{{}}"))
                    logger.info("Processing Kafka record | topic=%s", topic)
                    {agent_call}
                except Exception as exc:
                    logger.error("Failed to process record | error=%s", exc)

        return {{"statusCode": 200, "body": "processed"}}

    # Direct invocation
    try:
        {agent_call}
        return {{"statusCode": 200, "body": "ok"}}
    except Exception as exc:
        logger.error("Direct invocation failed | error=%s", exc)
        return {{"statusCode": 500, "body": str(exc)}}
'''

AGENT_IMPORTS = {
    "triage": "from agents.triage.agent import run_triage\nimport asyncio",
    "review": "from agents.review.agent import run_review\nimport asyncio",
    "ops": "from agents.ops.agent import run_ops\nimport asyncio",
    "chatbot": "from agents.chatbot.agent import ask\nimport asyncio",
    "api": "",
}

AGENT_CALLS = {
    "triage": "asyncio.run(run_triage(value))",
    "review": "asyncio.run(run_review(value))",
    "ops": "asyncio.run(run_ops(value))",
    "chatbot": "asyncio.run(ask(value.get('query', '')))",
    "api": "pass  # Handled by Mangum above",
}


def package_agent(agent_name: str) -> Path:
    """Package a single agent into a Lambda deployment ZIP."""
    logger.info("Packaging %s...", agent_name)
    config = AGENTS[agent_name]

    build_dir = DIST_DIR / f"build_{agent_name}"
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True)

    # Copy source directories
    for src in config["dirs"]:
        src_path = PROJECT_ROOT / src
        dest_path = build_dir / src
        if src_path.is_file():
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dest_path)
        elif src_path.is_dir():
            shutil.copytree(src_path, dest_path, dirs_exist_ok=True,
                           ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))

    # Generate lambda_function.py wrapper
    wrapper = LAMBDA_WRAPPER_TEMPLATE.format(
        agent_name=agent_name,
        agent_import=AGENT_IMPORTS[agent_name],
        agent_call=AGENT_CALLS[agent_name],
    )
    (build_dir / "lambda_function.py").write_text(wrapper)

    # Install dependencies
    logger.info("Installing dependencies for %s...", agent_name)
    deps_dir = build_dir / "python_deps"
    subprocess.run([
        sys.executable, "-m", "pip", "install",
        "-r", str(PROJECT_ROOT / "requirements.txt"),
        "-t", str(deps_dir),
        "--quiet", "--no-cache-dir",
    ], check=True)

    # Create ZIP
    DIST_DIR.mkdir(exist_ok=True)
    zip_path = DIST_DIR / f"{agent_name}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(build_dir):
            for f in files:
                file_path = Path(root) / f
                arcname = file_path.relative_to(build_dir)
                zf.write(file_path, arcname)

    # Cleanup build dir
    shutil.rmtree(build_dir)

    size_mb = zip_path.stat().st_size / (1024 * 1024)
    logger.info("✅ %s packaged | %s | %.1f MB", agent_name, zip_path, size_mb)
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Package Artilery agents for Lambda")
    parser.add_argument("--agent", choices=list(AGENTS.keys()), help="Package specific agent")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Artilery — Lambda Packaging")
    logger.info("=" * 60)

    agents_to_package = [args.agent] if args.agent else list(AGENTS.keys())

    for name in agents_to_package:
        try:
            package_agent(name)
        except Exception as exc:
            logger.error("❌ Failed to package %s: %s", name, exc)

    logger.info("Packaging complete!")


if __name__ == "__main__":
    main()
