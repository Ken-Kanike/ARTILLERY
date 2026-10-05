#!/usr/bin/env python3
"""
Artilery — Local Infrastructure Setup.

Initializes all local Docker services after `docker compose up -d`:
  1. Creates DynamoDB tables in local DynamoDB
  2. Creates S3 bucket in LocalStack
  3. Creates Kafka topics in local Kafka
  4. Seeds Neo4j with sample data
  5. Verifies all connections

Usage:
    docker compose up -d
    python -m scripts.setup_local
"""

from __future__ import annotations

import logging
import sys
import time

logger = logging.getLogger("artilery.scripts.setup_local")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)


def wait_for_service(name: str, check_fn, retries: int = 15, delay: float = 2.0) -> bool:
    """Wait for a service to become available."""
    for attempt in range(1, retries + 1):
        try:
            check_fn()
            logger.info("  ✅ %s is ready", name)
            return True
        except Exception as exc:
            if attempt < retries:
                logger.info("  ⏳ Waiting for %s... (attempt %d/%d)", name, attempt, retries)
                time.sleep(delay)
            else:
                logger.error("  ❌ %s not available after %d attempts: %s", name, retries, exc)
                return False
    return False


def check_kafka() -> None:
    """Verify Kafka is reachable."""
    from confluent_kafka.admin import AdminClient
    from shared.config import get_settings
    settings = get_settings()
    admin = AdminClient(settings.get_kafka_config())
    metadata = admin.list_topics(timeout=5)
    assert metadata is not None


def check_neo4j() -> None:
    """Verify Neo4j is reachable."""
    from neo4j import GraphDatabase
    from shared.config import get_settings
    settings = get_settings()
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD))
    with driver.session() as session:
        session.run("RETURN 1")
    driver.close()


def check_dynamodb() -> None:
    """Verify local DynamoDB is reachable."""
    import boto3
    from shared.config import get_settings
    settings = get_settings()
    client = boto3.client(
        "dynamodb", region_name=settings.AWS_REGION,
        endpoint_url=settings.DYNAMODB_ENDPOINT_URL or "http://localhost:8000",
        aws_access_key_id="local", aws_secret_access_key="local",
    )
    client.list_tables()


def check_minio() -> None:
    """Verify MinIO (S3) is reachable."""
    import boto3
    from shared.config import get_settings
    settings = get_settings()
    client = boto3.client(
        "s3", region_name=settings.AWS_REGION,
        endpoint_url=settings.S3_ENDPOINT_URL or "http://localhost:9000",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or "minioadmin",
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or "minioadmin",
    )
    client.list_buckets()


def create_dynamodb_tables() -> None:
    """Create DynamoDB tables in local instance."""
    import boto3
    from shared.config import get_settings
    settings = get_settings()

    client = boto3.client(
        "dynamodb", region_name=settings.AWS_REGION,
        endpoint_url=settings.DYNAMODB_ENDPOINT_URL or "http://localhost:8000",
        aws_access_key_id="local", aws_secret_access_key="local",
    )

    table_name = settings.DYNAMODB_TABLE_NAME or "artilery_state"
    existing = client.list_tables().get("TableNames", [])

    if table_name in existing:
        logger.info("  ⏭️  DynamoDB table exists: %s", table_name)
        return

    client.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    logger.info("  ✅ Created DynamoDB table: %s", table_name)


def create_s3_bucket() -> None:
    """Create S3 bucket in LocalStack."""
    import boto3
    from shared.config import get_settings
    settings = get_settings()

    client = boto3.client(
        "s3", region_name=settings.AWS_REGION,
        endpoint_url=settings.S3_ENDPOINT_URL or "http://localhost:9000",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID or "minioadmin",
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or "minioadmin",
    )

    bucket = settings.S3_BUCKET_NAME or "artilery-event-logs"
    try:
        client.head_bucket(Bucket=bucket)
        logger.info("  ⏭️  S3 bucket exists: %s", bucket)
    except Exception:
        client.create_bucket(Bucket=bucket)
        logger.info("  ✅ Created S3 bucket: %s", bucket)


def create_kafka_topics() -> None:
    """Create Kafka topics using the existing script logic."""
    from shared.kafka_utils import create_topics

    core_topics = [
        "bug.ingested", "ticket.created", "pr.opened", "pr.review.requested",
        "pr.reviewed", "pr.approved", "deploy.triggered", "deploy.failed",
        "deploy.succeeded", "ticket.resolved",
    ]
    dlq_topics = [f"{t}.dlq" for t in core_topics]
    all_topics = core_topics + dlq_topics

    results = create_topics(topics=all_topics, num_partitions=3, replication_factor=1)

    created = sum(1 for r in results.values() if r == "created")
    existing = sum(1 for r in results.values() if r == "already_exists")
    logger.info("  ✅ Topics: %d created, %d already existed", created, existing)


def seed_neo4j() -> None:
    """Seed Neo4j with sample organization data."""
    from shared.config import get_settings
    from scripts.seed_neo4j import seed

    settings = get_settings()
    seed(settings.NEO4J_URI, settings.NEO4J_USERNAME, settings.NEO4J_PASSWORD)


def main() -> None:
    logger.info("=" * 60)
    logger.info("Artilery — Local Setup")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Make sure Docker containers are running:")
    logger.info("  docker compose up -d")
    logger.info("")

    # Step 1: Wait for all services
    logger.info("📡 Step 1: Checking service availability...")
    services_ok = all([
        wait_for_service("Kafka", check_kafka),
        wait_for_service("Neo4j", check_neo4j),
        wait_for_service("DynamoDB Local", check_dynamodb),
        wait_for_service("MinIO (S3)", check_minio),
    ])

    if not services_ok:
        logger.error("\n❌ Some services are not running. Start them with: docker compose up -d")
        sys.exit(1)

    # Step 2: Create DynamoDB tables
    logger.info("\n📊 Step 2: Creating DynamoDB tables...")
    create_dynamodb_tables()

    # Step 3: Create S3 bucket
    logger.info("\n🗄️  Step 3: Creating S3 bucket...")
    create_s3_bucket()

    # Step 4: Create Kafka topics
    logger.info("\n📨 Step 4: Creating Kafka topics...")
    create_kafka_topics()

    # Step 5: Seed Neo4j
    logger.info("\n🕸️  Step 5: Seeding Neo4j graph...")
    seed_neo4j()

    # Done
    logger.info("\n" + "=" * 60)
    logger.info("✅ LOCAL SETUP COMPLETE!")
    logger.info("=" * 60)
    logger.info("")
    logger.info("You can now run the system:")
    logger.info("  Terminal 1: python -m agents.triage.agent")
    logger.info("  Terminal 2: python -m agents.review.agent")
    logger.info("  Terminal 3: python -m agents.ops.agent")
    logger.info("  Terminal 4: uvicorn api.main:app --reload")
    logger.info("")
    logger.info("Test the flow:")
    logger.info("  python -m scripts.test_event_flow")
    logger.info("")
    logger.info("Chatbot:")
    logger.info("  curl -X POST http://localhost:8000/chat \\")
    logger.info('    -H "Content-Type: application/json" \\')
    logger.info('    -d \'{"query": "Who owns PaymentService?"}\'')
    logger.info("")


if __name__ == "__main__":
    main()
