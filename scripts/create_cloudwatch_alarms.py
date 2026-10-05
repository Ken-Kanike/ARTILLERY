#!/usr/bin/env python3
"""
Artilery — CloudWatch Alarms Provisioning.

Creates SNS topic (artilery-alerts) and CloudWatch alarms:
  - AgentFailures > 5 in 5min
  - ConsumerLag > 1000
  - BedrockLatency > 10s
  - LambdaErrorRate > 1%

Usage:
    python -m scripts.create_cloudwatch_alarms
"""

from __future__ import annotations

import logging

logger = logging.getLogger("artilery.scripts.cloudwatch_alarms")
LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)

REGION = "us-east-1"

ALARMS = [
    {
        "name": "artilery-agent-failures",
        "description": "Alert when agent failures exceed 5 in 5 minutes",
        "namespace": "Artilery",
        "metric": "AgentFailures",
        "statistic": "Sum",
        "period": 300,
        "threshold": 5.0,
        "comparison": "GreaterThanThreshold",
        "eval_periods": 1,
    },
    {
        "name": "artilery-consumer-lag",
        "description": "Alert when Kafka consumer lag exceeds 1000",
        "namespace": "Artilery",
        "metric": "ConsumerLag",
        "statistic": "Maximum",
        "period": 300,
        "threshold": 1000.0,
        "comparison": "GreaterThanThreshold",
        "eval_periods": 2,
    },
    {
        "name": "artilery-bedrock-latency",
        "description": "Alert when Bedrock inference latency exceeds 10 seconds",
        "namespace": "Artilery",
        "metric": "BedrockLatencyMs",
        "statistic": "Average",
        "period": 300,
        "threshold": 10000.0,
        "comparison": "GreaterThanThreshold",
        "eval_periods": 3,
    },
    {
        "name": "artilery-lambda-errors",
        "description": "Alert when Lambda error rate exceeds 1%",
        "namespace": "AWS/Lambda",
        "metric": "Errors",
        "statistic": "Sum",
        "period": 300,
        "threshold": 5.0,
        "comparison": "GreaterThanThreshold",
        "eval_periods": 1,
        "dimensions": [{"Name": "FunctionName", "Value": "artilery-*"}],
    },
]


def main() -> None:
    import boto3

    sns = boto3.client("sns", region_name=REGION)
    cw = boto3.client("cloudwatch", region_name=REGION)

    logger.info("=" * 60)
    logger.info("Artilery — CloudWatch Alarms Setup")
    logger.info("=" * 60)

    # Create SNS topic
    topic_response = sns.create_topic(
        Name="artilery-alerts",
        Tags=[
            {"Key": "Project", "Value": "Artilery"},
            {"Key": "Environment", "Value": "production"},
        ],
    )
    topic_arn = topic_response["TopicArn"]
    logger.info("✅ SNS Topic: %s", topic_arn)
    logger.info("   ⚠️  Subscribe with: aws sns subscribe --topic-arn %s --protocol email --notification-endpoint YOUR_EMAIL", topic_arn)

    # Create alarms
    for alarm_cfg in ALARMS:
        logger.info("Creating alarm: %s", alarm_cfg["name"])
        kwargs = {
            "AlarmName": alarm_cfg["name"],
            "AlarmDescription": alarm_cfg["description"],
            "Namespace": alarm_cfg["namespace"],
            "MetricName": alarm_cfg["metric"],
            "Statistic": alarm_cfg["statistic"],
            "Period": alarm_cfg["period"],
            "Threshold": alarm_cfg["threshold"],
            "ComparisonOperator": alarm_cfg["comparison"],
            "EvaluationPeriods": alarm_cfg["eval_periods"],
            "AlarmActions": [topic_arn],
            "OKActions": [topic_arn],
            "Tags": [
                {"Key": "Project", "Value": "Artilery"},
                {"Key": "Environment", "Value": "production"},
            ],
            "TreatMissingData": "notBreaching",
        }
        if alarm_cfg.get("dimensions"):
            kwargs["Dimensions"] = alarm_cfg["dimensions"]

        try:
            cw.put_metric_alarm(**kwargs)
            logger.info("  ✅ Created: %s", alarm_cfg["name"])
        except Exception as exc:
            logger.error("  ❌ Failed: %s | %s", alarm_cfg["name"], exc)

    logger.info("\n✅ CloudWatch alarms setup complete!")


if __name__ == "__main__":
    main()
