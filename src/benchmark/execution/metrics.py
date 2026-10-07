from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from benchmark.agents.contracts import RunResult, RunStatus
from benchmark.workflows.contracts import CANONICAL_STAGES


def run_metric_row(result: RunResult) -> dict[str, Any]:
    metrics = result.metrics
    return {
        "run_id": result.context.run_id,
        "experiment_id": result.context.experiment_id,
        "framework": result.context.framework.value,
        "framework_version": result.context.framework_version,
        "model_id": result.context.model_id,
        "snapshot_hash": result.context.snapshot_hash,
        "config_hash": result.context.config_hash,
        "prompt_bundle_hash": result.context.prompt_bundle_hash,
        "status": result.status.value,
        "final_action": result.final_decision.action.value,
        **metrics.model_dump(mode="json"),
    }


def call_metric_rows(result: RunResult) -> tuple[dict[str, Any], ...]:
    common = {
        "experiment_id": result.context.experiment_id,
        "framework": result.context.framework.value,
        "model_id": result.context.model_id,
        "snapshot_hash": result.context.snapshot_hash,
    }
    return tuple({**common, **metric.model_dump(mode="json")} for metric in result.call_metrics)


def stage_metric_rows(result: RunResult) -> tuple[dict[str, Any], ...]:
    common = {
        "run_id": result.context.run_id,
        "experiment_id": result.context.experiment_id,
        "framework": result.context.framework.value,
        "snapshot_hash": result.context.snapshot_hash,
    }
    return tuple({**common, **metric.model_dump(mode="json")} for metric in result.stage_metrics)


def aggregate_run_results(results: Iterable[RunResult]) -> dict[str, Any]:
    values = tuple(results)
    if not values:
        return {
            "run_count": 0,
            "success_rate": 0.0,
            "decision_counts": {},
            "mean_end_to_end_ms": None,
            "mean_total_tokens": None,
            "mean_cost_usd": None,
        }
    successes = [result for result in values if result.status == RunStatus.SUCCESS]
    return {
        "run_count": len(values),
        "success_rate": len(successes) / len(values),
        "decision_counts": dict(Counter(result.final_decision.action.value for result in successes)),
        "mean_end_to_end_ms": sum(result.metrics.end_to_end_ms for result in values) / len(values),
        "mean_total_tokens": sum(result.metrics.total_tokens for result in values) / len(values),
        "mean_cost_usd": sum(result.metrics.cost_usd for result in values) / len(values),
        "mean_retry_count": sum(result.metrics.retry_count for result in values) / len(values),
        "required_stage_count": len(CANONICAL_STAGES),
    }
