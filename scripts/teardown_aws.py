#!/usr/bin/env python3
"""
Artilery — AWS Infrastructure Teardown Script.

Cleanly deletes all Artilery AWS resources:
- Lambda functions
- DynamoDB tables
- S3 bucket (empties first)
- API Gateway HTTP APIs
- EventBridge rules
- SNS topics
- Secrets Manager secret
- CloudWatch alarms

Usage:
    python -m scripts.teardown_aws
    python -m scripts.teardown_aws --component lambda  # Teardown specific component
    python -m scripts.teardown_aws --dry-run            # Preview deletions
"""

from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger("artilery.scripts.teardown_aws")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

REGION = "us-east-1"

LAMBDA_FUNCTIONS = [
    "artilery-triage", "artilery-review", "artilery-ops",
    "artilery-chatbot", "artilery-api", "artilery-cloudwatch-bridge",
]

DYNAMODB_TABLES = [
    "artilery_pr_state", "artilery_agent_checkpoints",
    "artilery_idempotency", "artilery_chat_history",
]

CLOUDWATCH_ALARMS = [
    "artilery-agent-failures", "artilery-consumer-lag",
    "artilery-bedrock-latency", "artilery-lambda-errors",
]

EVENTBRIDGE_RULES = [
    "artilery-codedeploy-state-change", "artilery-daily-indexer",
]


def teardown_lambda(dry_run: bool) -> None:
    import boto3
    client = boto3.client("lambda", region_name=REGION)
    for name in LAMBDA_FUNCTIONS:
        try:
            client.get_function(FunctionName=name)
            if dry_run:
                logger.info("  [DRY RUN] Would delete Lambda: %s", name)
            else:
                client.delete_function(FunctionName=name)
                logger.info("  🗑️  Deleted Lambda: %s", name)
        except client.exceptions.ResourceNotFoundException:
            logger.info("  ⏭️  Lambda not found: %s", name)


def teardown_dynamodb(dry_run: bool) -> None:
    import boto3
    client = boto3.client("dynamodb", region_name=REGION)
    for name in DYNAMODB_TABLES:
        try:
            client.describe_table(TableName=name)
            if dry_run:
                logger.info("  [DRY RUN] Would delete DynamoDB table: %s", name)
            else:
                client.delete_table(TableName=name)
                logger.info("  🗑️  Deleted DynamoDB table: %s", name)
        except client.exceptions.ResourceNotFoundException:
            logger.info("  ⏭️  Table not found: %s", name)


def teardown_s3(dry_run: bool) -> None:
    import boto3
    s3 = boto3.client("s3", region_name=REGION)
    try:
        buckets = s3.list_buckets().get("Buckets", [])
        art_buckets = [b["Name"] for b in buckets if b["Name"].startswith("artilery-")]
        for bucket in art_buckets:
            if dry_run:
                logger.info("  [DRY RUN] Would delete S3 bucket: %s", bucket)
                continue
            # Empty bucket first
            s3r = boto3.resource("s3", region_name=REGION)
            bucket_obj = s3r.Bucket(bucket)
            bucket_obj.object_versions.all().delete()
            bucket_obj.objects.all().delete()
            s3.delete_bucket(Bucket=bucket)
            logger.info("  🗑️  Deleted S3 bucket: %s", bucket)
    except Exception as exc:
        logger.warning("  ⚠️  S3 teardown error: %s", exc)


def teardown_api_gateway(dry_run: bool) -> None:
    import boto3
    client = boto3.client("apigatewayv2", region_name=REGION)
    apis = client.get_apis().get("Items", [])
    for api in apis:
        if api["Name"].startswith("artilery"):
            if dry_run:
                logger.info("  [DRY RUN] Would delete API: %s (%s)", api["Name"], api["ApiId"])
            else:
                client.delete_api(ApiId=api["ApiId"])
                logger.info("  🗑️  Deleted API: %s", api["Name"])


def teardown_eventbridge(dry_run: bool) -> None:
    import boto3
    client = boto3.client("events", region_name=REGION)
    for rule in EVENTBRIDGE_RULES:
        try:
            targets = client.list_targets_by_rule(Rule=rule).get("Targets", [])
            if targets and not dry_run:
                client.remove_targets(Rule=rule, Ids=[t["Id"] for t in targets])
            if dry_run:
                logger.info("  [DRY RUN] Would delete EventBridge rule: %s", rule)
            else:
                client.delete_rule(Name=rule)
                logger.info("  🗑️  Deleted EventBridge rule: %s", rule)
        except client.exceptions.ResourceNotFoundException:
            logger.info("  ⏭️  Rule not found: %s", rule)


def teardown_sns(dry_run: bool) -> None:
    import boto3
    client = boto3.client("sns", region_name=REGION)
    topics = client.list_topics().get("Topics", [])
    for topic in topics:
        arn = topic["TopicArn"]
        if "artilery" in arn:
            if dry_run:
                logger.info("  [DRY RUN] Would delete SNS topic: %s", arn)
            else:
                client.delete_topic(TopicArn=arn)
                logger.info("  🗑️  Deleted SNS topic: %s", arn)


def teardown_cloudwatch(dry_run: bool) -> None:
    import boto3
    client = boto3.client("cloudwatch", region_name=REGION)
    for alarm in CLOUDWATCH_ALARMS:
        try:
            if dry_run:
                logger.info("  [DRY RUN] Would delete alarm: %s", alarm)
            else:
                client.delete_alarms(AlarmNames=[alarm])
                logger.info("  🗑️  Deleted alarm: %s", alarm)
        except Exception as exc:
            logger.warning("  ⚠️  Alarm delete failed: %s | %s", alarm, exc)


def teardown_secrets(dry_run: bool) -> None:
    import boto3
    client = boto3.client("secretsmanager", region_name=REGION)
    try:
        client.describe_secret(SecretId="artilery/production")
        if dry_run:
            logger.info("  [DRY RUN] Would delete secret: artilery/production")
        else:
            client.delete_secret(SecretId="artilery/production", ForceDeleteWithoutRecovery=True)
            logger.info("  🗑️  Deleted secret: artilery/production")
    except client.exceptions.ResourceNotFoundException:
        logger.info("  ⏭️  Secret not found")


def main() -> None:
    parser = argparse.ArgumentParser(description="Teardown Artilery AWS resources")
    parser.add_argument("--component", choices=["lambda", "dynamodb", "s3", "apigw", "eventbridge", "sns", "cloudwatch", "secrets"])
    parser.add_argument("--dry-run", action="store_true", help="Preview deletions without executing")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Artilery — AWS Teardown%s", " (DRY RUN)" if args.dry_run else "")
    logger.info("=" * 60)

    if not args.dry_run:
        confirm = input("⚠️  This will DELETE all Artilery AWS resources. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            logger.info("Aborted.")
            sys.exit(0)

    components = [args.component] if args.component else ["lambda", "dynamodb", "s3", "apigw", "eventbridge", "sns", "cloudwatch", "secrets"]

    component_map = {
        "lambda": ("⚡ Lambda Functions", teardown_lambda),
        "dynamodb": ("📊 DynamoDB Tables", teardown_dynamodb),
        "s3": ("🗄️  S3 Buckets", teardown_s3),
        "apigw": ("🌐 API Gateway", teardown_api_gateway),
        "eventbridge": ("📅 EventBridge Rules", teardown_eventbridge),
        "sns": ("📢 SNS Topics", teardown_sns),
        "cloudwatch": ("📈 CloudWatch Alarms", teardown_cloudwatch),
        "secrets": ("🔐 Secrets Manager", teardown_secrets),
    }

    for comp in components:
        label, func = component_map[comp]
        logger.info("\n%s", label)
        func(args.dry_run)

    logger.info("\n" + "=" * 60)
    logger.info("✅ Teardown complete!")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
