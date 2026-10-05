"""
Artilery Shared Observability — Structured Logging, Metrics & Decorators.

Provides: configure_logging, StructuredFormatter, MetricsCollector,
          @log_execution, @track_metric decorators.

Used across all agents and the API layer for consistent observability.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter for production environments."""

    def __init__(self, service_name: str = "artilery") -> None:
        super().__init__()
        self._service = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": self._service,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
            }

        # Include extra fields if present
        for key in ("event_id", "agent", "topic", "bug_id", "pr_number", "deployment_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


def configure_logging(
    service_name: str = "artilery",
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """Configure application-wide logging.

    Args:
        service_name: Name embedded in structured logs.
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        json_format: Use JSON structured logging (production).
                     Set False for human-readable dev logs.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_format and os.environ.get("ARTILERY_ENV", "development") == "production":
        handler.setFormatter(StructuredFormatter(service_name))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    root_logger.addHandler(handler)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "botocore", "confluent_kafka", "neo4j"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class MetricsCollector:
    """Simple in-memory metrics collector for agent operations.

    In production, this would push to CloudWatch or Prometheus.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._timers: dict[str, list[float]] = {}

    def increment(self, metric: str, value: int = 1) -> None:
        self._counters[metric] = self._counters.get(metric, 0) + value

    def timer(self, metric: str) -> _Timer:
        return _Timer(metric, self)

    def record_duration(self, metric: str, duration: float) -> None:
        if metric not in self._timers:
            self._timers[metric] = []
        self._timers[metric].append(duration)

    def get_counter(self, metric: str) -> int:
        return self._counters.get(metric, 0)

    def get_avg_duration(self, metric: str) -> float:
        durations = self._timers.get(metric, [])
        return sum(durations) / len(durations) if durations else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "timers": {k: {"count": len(v), "avg_ms": sum(v) / len(v) * 1000 if v else 0} for k, v in self._timers.items()},
        }

    def reset(self) -> None:
        self._counters.clear()
        self._timers.clear()


class _Timer:
    """Context manager for timing operations."""

    def __init__(self, metric: str, collector: MetricsCollector) -> None:
        self._metric = metric
        self._collector = collector
        self._start: float = 0

    def __enter__(self) -> _Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        duration = time.perf_counter() - self._start
        self._collector.record_duration(self._metric, duration)


# Global metrics instance
metrics = MetricsCollector()


# ── Decorators ───────────────────────────────────────────────────────────────

def log_execution(
    agent: Optional[str] = None,
    log_args: bool = False,
) -> Any:
    """Decorator that logs function entry, exit, duration, and success/failure.

    Args:
        agent: Agent name for structured log context (e.g., "triage", "ops").
        log_args: If True, log the function arguments (be careful with large payloads).

    Usage:
        @log_execution(agent="triage")
        async def create_ticket(data):
            ...
    """
    def decorator(func: Any) -> Any:
        func_name = func.__name__
        _logger = logging.getLogger(f"artilery.{agent}" if agent else "artilery")

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            extra_args = f" | args={str(args)[:100]}" if log_args else ""
            _logger.info("ENTER | %s%s", func_name, extra_args)

            try:
                result = await func(*args, **kwargs)
                duration = time.perf_counter() - start
                _logger.info("EXIT  | %s | %.3fs | success", func_name, duration)
                metrics.record_duration(f"{func_name}.duration", duration)
                metrics.increment(f"{func_name}.success")
                return result
            except Exception as exc:
                duration = time.perf_counter() - start
                _logger.error("EXIT  | %s | %.3fs | FAILED | %s: %s", func_name, duration, type(exc).__name__, exc)
                metrics.increment(f"{func_name}.failure")
                metrics.increment("AgentFailures")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            extra_args = f" | args={str(args)[:100]}" if log_args else ""
            _logger.info("ENTER | %s%s", func_name, extra_args)

            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start
                _logger.info("EXIT  | %s | %.3fs | success", func_name, duration)
                metrics.record_duration(f"{func_name}.duration", duration)
                metrics.increment(f"{func_name}.success")
                return result
            except Exception as exc:
                duration = time.perf_counter() - start
                _logger.error("EXIT  | %s | %.3fs | FAILED | %s: %s", func_name, duration, type(exc).__name__, exc)
                metrics.increment(f"{func_name}.failure")
                metrics.increment("AgentFailures")
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def track_metric(
    metric_name: Optional[str] = None,
    namespace: str = "Artilery",
    push_to_cloudwatch: bool = False,
) -> Any:
    """Decorator that records metrics (duration, invocation count) and optionally pushes to CloudWatch.

    Args:
        metric_name: Metric name override. Defaults to function name.
        namespace: CloudWatch namespace.
        push_to_cloudwatch: If True, publishes to CloudWatch custom metrics.

    Usage:
        @track_metric(push_to_cloudwatch=True)
        async def diagnose_with_bedrock(data):
            ...
    """
    def decorator(func: Any) -> Any:
        name = metric_name or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                metrics.increment(f"{name}.invocations")
                metrics.record_duration(f"{name}.duration", time.perf_counter() - start)

                if push_to_cloudwatch:
                    _push_cloudwatch_metric(namespace, name, duration_ms)

                return result
            except Exception as exc:
                metrics.increment(f"{name}.errors")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start) * 1000
                metrics.increment(f"{name}.invocations")
                metrics.record_duration(f"{name}.duration", time.perf_counter() - start)

                if push_to_cloudwatch:
                    _push_cloudwatch_metric(namespace, name, duration_ms)

                return result
            except Exception as exc:
                metrics.increment(f"{name}.errors")
                raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _push_cloudwatch_metric(namespace: str, metric_name: str, value: float) -> None:
    """Push a single metric to CloudWatch (fire-and-forget)."""
    try:
        import boto3
        cw = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "us-east-1"))
        cw.put_metric_data(
            Namespace=namespace,
            MetricData=[{
                "MetricName": metric_name,
                "Value": value,
                "Unit": "Milliseconds",
                "Timestamp": datetime.now(timezone.utc),
                "Dimensions": [{"Name": "Environment", "Value": os.environ.get("ARTILERY_ENV", "development")}],
            }],
        )
    except Exception:
        pass  # Non-critical, don't break the app
