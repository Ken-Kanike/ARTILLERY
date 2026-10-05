#!/usr/bin/env python3
"""
Artilery — AWS Infrastructure Deployment Script.

Creates all AWS resources using boto3:
- Lambda functions (one per agent + API)
- DynamoDB tables (pr_state, checkpoints, idempotency, chat_history)
- S3 bucket (versioning, lifecycle, encryption)
- Secrets Manager secret
- API Gateway HTTP API
- EventBridge rules

All resources tagged: Project=Artilery, Environment=production.
Idempotent — safe to run multiple times.

Usage:
    python -m scripts.deploy_aws
    python -m scripts.deploy_aws --component lambda
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

logger = logging.getLogger("artilery.scripts.deploy_aws")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

TAGS = {"Project": "Artilery", "Environment": "production", "ManagedBy": "artilery-deploy-script"}
REGION = "us-east-1"

LAMBDA_CONFIGS = {
    "artilery-triage": {"memory": 512, "timeout": 300, "handler": "lambda_function.handler"},
    "artilery-review": {"memory": 512, "timeout": 300, "handler": "lambda_function.handler"},
    "artilery-ops": {"memory": 1024, "timeout": 300, "handler": "lambda_function.handler"},
    "artilery-chatbot": {"memory": 512, "timeout": 300, "handler": "lambda_function.handler"},
    "artilery-api": {"memory": 512, "timeout": 30, "handler": "lambda_function.handler"},
}

DYNAMODB_TABLES = [
    {"name": "artilery_pr_state", "pk": "pk", "sk": "sk", "gsi": [{"name": "gsi_service", "pk": "service_name"}]},
    {"name": "artilery_agent_checkpoints", "pk": "pk", "sk": "sk", "gsi": []},
    {"name": "artilery_idempotency", "pk": "pk", "sk": "sk", "ttl": "ttl", "gsi": []},
    {"name": "artilery_chat_history", "pk": "pk", "sk": "sk", "gsi": []},
]


def get_account_id() -> str:
    import boto3
    sts = boto3.client("sts", region_name=REGION)
    return sts.get_caller_identity()["Account"]


def create_dynamodb_tables() -> None:
    """Create all DynamoDB tables with PITR enabled."""
    import boto3
    dynamodb = boto3.client("dynamodb", region_name=REGION)

    for table_cfg in DYNAMODB_TABLES:
        name = table_cfg["name"]
        try:
            dynamodb.describe_table(TableName=name)
            logger.info("  ⏭️  DynamoDB table exists: %s", name)
        except dynamodb.exceptions.ResourceNotFoundException:
            key_schema = [{"AttributeName": table_cfg["pk"], "KeyType": "HASH"}]
            attr_defs = [{"AttributeName": table_cfg["pk"], "AttributeType": "S"}]
            if table_cfg.get("sk"):
                key_schema.append({"AttributeName": table_cfg["sk"], "KeyType": "RANGE"})
                attr_defs.append({"AttributeName": table_cfg["sk"], "AttributeType": "S"})

            kwargs: dict[str, Any] = {
                "TableName": name, "KeySchema": key_schema,
                "AttributeDefinitions": attr_defs,
                "BillingMode": "PAY_PER_REQUEST",
                "Tags": [{"Key": k, "Value": v} for k, v in TAGS.items()],
            }

            # Add GSIs
            if table_cfg.get("gsi"):
                gsi_list = []
                for gsi in table_cfg["gsi"]:
                    attr_defs.append({"AttributeName": gsi["pk"], "AttributeType": "S"})
                    gsi_list.append({
                        "IndexName": gsi["name"],
                        "KeySchema": [{"AttributeName": gsi["pk"], "KeyType": "HASH"}],
                        "Projection": {"ProjectionType": "ALL"},
                    })
                kwargs["GlobalSecondaryIndexes"] = gsi_list

            dynamodb.create_table(**kwargs)
            logger.info("  ✅ Created DynamoDB table: %s", name)

            # Enable PITR
            dynamodb.update_continuous_backups(
                TableName=name,
                PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
            )

            # Enable TTL if configured
            if table_cfg.get("ttl"):
                dynamodb.update_time_to_live(
                    TableName=name,
                    TimeToLiveSpecification={"Enabled": True, "AttributeName": table_cfg["ttl"]},
                )


def create_s3_bucket(account_id: str) -> str:
    """Create S3 bucket with versioning, encryption, and lifecycle."""
    import boto3
    s3 = boto3.client("s3", region_name=REGION)
    bucket_name = f"artilery-event-logs-{account_id}"

    try:
        s3.head_bucket(Bucket=bucket_name)
        logger.info("  ⏭️  S3 bucket exists: %s", bucket_name)
    except Exception:
        create_kwargs: dict[str, Any] = {"Bucket": bucket_name}
        if REGION != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
        s3.create_bucket(**create_kwargs)

        s3.put_bucket_versioning(Bucket=bucket_name, VersioningConfiguration={"Status": "Enabled"})
        s3.put_bucket_encryption(Bucket=bucket_name, ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        })
        s3.put_public_access_block(Bucket=bucket_name, PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
        })
        s3.put_bucket_lifecycle_configuration(Bucket=bucket_name, LifecycleConfiguration={
            "Rules": [{"ID": "glacier-90d", "Status": "Enabled", "Filter": {"Prefix": ""},
                       "Transitions": [{"Days": 90, "StorageClass": "GLACIER"}]}]
        })
        s3.put_bucket_tagging(Bucket=bucket_name, Tagging={
            "TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]
        })
        logger.info("  ✅ Created S3 bucket: %s", bucket_name)

    return bucket_name


def create_secrets_manager_secret() -> None:
    """Store environment config in Secrets Manager."""
    import boto3
    sm = boto3.client("secretsmanager", region_name=REGION)
    secret_name = "artilery/production"

    try:
        sm.describe_secret(SecretId=secret_name)
        logger.info("  ⏭️  Secret exists: %s", secret_name)
    except sm.exceptions.ResourceNotFoundException:
        sm.create_secret(
            Name=secret_name,
            Description="Artilery production environment configuration",
            SecretString=json.dumps({"placeholder": "Replace with real .env values"}),
            Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
        )
        logger.info("  ✅ Created secret: %s", secret_name)
        logger.info("     ⚠️  Update with: aws secretsmanager put-secret-value --secret-id %s --secret-string '{...}'", secret_name)


def create_lambda_functions(account_id: str) -> None:
    """Create Lambda functions for each agent."""
    import boto3
    lambda_client = boto3.client("lambda", region_name=REGION)
    role_arn = f"arn:aws:iam::{account_id}:role/artilery-lambda-role"

    for func_name, cfg in LAMBDA_CONFIGS.items():
        try:
            lambda_client.get_function(FunctionName=func_name)
            logger.info("  ⏭️  Lambda exists: %s", func_name)
        except lambda_client.exceptions.ResourceNotFoundException:
            logger.info("  📦 Creating Lambda: %s (ensure dist/%s.zip exists)", func_name, func_name.replace("artilery-", ""))
            try:
                agent_key = func_name.replace("artilery-", "")
                zip_path = f"dist/{agent_key}.zip"
                with open(zip_path, "rb") as f:
                    zip_content = f.read()

                lambda_client.create_function(
                    FunctionName=func_name,
                    Runtime="python3.13",
                    Role=role_arn,
                    Handler=cfg["handler"],
                    Code={"ZipFile": zip_content},
                    MemorySize=cfg["memory"],
                    Timeout=cfg["timeout"],
                    TracingConfig={"Mode": "Active"},
                    Tags=TAGS,
                    Environment={"Variables": {"ARTILERY_ENV": "production"}},
                )
                lambda_client.put_function_concurrency(
                    FunctionName=func_name, ReservedConcurrentExecutions=10,
                )
                logger.info("  ✅ Created Lambda: %s", func_name)
            except FileNotFoundError:
                logger.warning("  ⚠️  ZIP not found for %s — run scripts/package_lambda.py first", func_name)


def create_api_gateway(account_id: str) -> None:
    """Create API Gateway HTTP API."""
    import boto3
    apigw = boto3.client("apigatewayv2", region_name=REGION)

    apis = apigw.get_apis().get("Items", [])
    existing = [a for a in apis if a.get("Name") == "artilery-api"]

    if existing:
        logger.info("  ⏭️  API Gateway exists: artilery-api")
        return

    api = apigw.create_api(
        Name="artilery-api", ProtocolType="HTTP",
        Description="Artilery CI/CD API Gateway",
        Tags=TAGS,
    )
    api_id = api["ApiId"]

    lambda_arn = f"arn:aws:lambda:{REGION}:{account_id}:function:artilery-api"
    integration = apigw.create_integration(
        ApiId=api_id, IntegrationType="AWS_PROXY",
        IntegrationUri=lambda_arn, PayloadFormatVersion="2.0",
    )
    int_id = integration["IntegrationId"]

    for route in ["POST /webhook/github", "POST /chat", "GET /health", "GET /chat/history", "DELETE /chat/history"]:
        apigw.create_route(ApiId=api_id, RouteKey=route, Target=f"integrations/{int_id}")

    apigw.create_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
    logger.info("  ✅ Created API Gateway: %s | URL: https://%s.execute-api.%s.amazonaws.com", api_id, api_id, REGION)


def create_eventbridge_rules(account_id: str) -> None:
    """Create EventBridge rules for CodeDeploy and daily indexer."""
    import boto3
    events = boto3.client("events", region_name=REGION)

    # CodeDeploy state change → CloudWatch Bridge Lambda
    try:
        events.put_rule(
            Name="artilery-codedeploy-state-change",
            EventPattern=json.dumps({
                "source": ["aws.codedeploy"],
                "detail-type": ["CodeDeploy Deployment State-change Notification"],
            }),
            State="ENABLED",
            Description="Routes CodeDeploy events to Artilery CloudWatch Bridge Lambda",
            Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()],
        )
        lambda_arn = f"arn:aws:lambda:{REGION}:{account_id}:function:artilery-cloudwatch-bridge"
        events.put_targets(Rule="artilery-codedeploy-state-change", Targets=[{"Id": "cloudwatch-bridge", "Arn": lambda_arn}])
        logger.info("  ✅ EventBridge rule: artilery-codedeploy-state-change")
    except Exception as exc:
        logger.warning("  ⚠️  EventBridge CodeDeploy rule failed: %s", exc)

    # Daily event indexer
    try:
        events.put_rule(
            Name="artilery-daily-indexer",
            ScheduleExpression="cron(0 0 * * ? *)",
            State="ENABLED",
            Description="Daily event indexer for ChromaDB",
        )
        logger.info("  ✅ EventBridge rule: artilery-daily-indexer (daily midnight UTC)")
    except Exception as exc:
        logger.warning("  ⚠️  EventBridge indexer rule failed: %s", exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Artilery AWS infrastructure")
    parser.add_argument("--component", choices=["dynamodb", "s3", "secrets", "lambda", "apigw", "eventbridge"], help="Deploy specific component")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Artilery — AWS Deployment")
    logger.info("=" * 60)

    try:
        account_id = get_account_id()
        logger.info("AWS Account: %s | Region: %s", account_id, REGION)
    except Exception as exc:
        logger.error("Failed to get AWS account ID. Check credentials. Error: %s", exc)
        sys.exit(1)

    components = [args.component] if args.component else ["dynamodb", "s3", "secrets", "lambda", "apigw", "eventbridge"]

    if "dynamodb" in components:
        logger.info("\n📊 DynamoDB Tables")
        create_dynamodb_tables()
    if "s3" in components:
        logger.info("\n🗄️  S3 Bucket")
        create_s3_bucket(account_id)
    if "secrets" in components:
        logger.info("\n🔐 Secrets Manager")
        create_secrets_manager_secret()
    if "lambda" in components:
        logger.info("\n⚡ Lambda Functions")
        create_lambda_functions(account_id)
    if "apigw" in components:
        logger.info("\n🌐 API Gateway")
        create_api_gateway(account_id)
    if "eventbridge" in components:
        logger.info("\n📅 EventBridge Rules")
        create_eventbridge_rules(account_id)

    logger.info("\n" + "=" * 60)
    logger.info("✅ Deployment complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
