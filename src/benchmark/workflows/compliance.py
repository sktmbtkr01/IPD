from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from benchmark.agents.contracts import CallStatus, RunContext, RunResult, RunStatus
from benchmark.core.schemas import FrozenModel
from benchmark.workflows.contracts import CANONICAL_STAGES, STAGE_DEPENDENCIES


PROHIBITED_ADAPTER_IMPORTS = {
    "benchmark.data",
    "aiohttp",
    "boto3",
    "httpx",
    "requests",
    "urllib",
}


class ComplianceReport(FrozenModel):
    compliant: bool
    violations: tuple[str, ...]


class ParityReport(FrozenModel):
    controls_equal: bool
    stage_sets_equal: bool
    logical_call_counts_equal: bool
    final_actions_equal: bool
    first_divergence_stage: str | None = None
    violations: tuple[str, ...] = ()


def validate_run_compliance(result: RunResult, expected_context: RunContext) -> ComplianceReport:
    violations: list[str] = []
    if result.context != expected_context:
        violations.append("run context differs from the frozen expected context")
    if result.status != RunStatus.SUCCESS:
        violations.append("run did not finish successfully")
    successful_stages = [metric.stage for metric in result.stage_metrics if metric.status == RunStatus.SUCCESS]
    counts = Counter(successful_stages)
    if set(counts) != set(CANONICAL_STAGES):
        violations.append("successful stage set differs from canonical stages")
    duplicated = sorted(stage for stage, count in counts.items() if count != 1)
    if duplicated:
        violations.append(f"successful stages must execute exactly once: {duplicated}")
    call_stages = {metric.stage for metric in result.call_metrics if metric.status == CallStatus.SUCCESS}
    if call_stages != set(CANONICAL_STAGES):
        violations.append("every canonical stage must have a successful shared-LLM call")
    if result.metrics.logical_call_count != len(CANONICAL_STAGES):
        violations.append("logical call count differs from canonical stage count")
    if result.metrics.physical_attempt_count != len(result.call_metrics):
        violations.append("physical attempt count differs from call metrics")
    if result.metrics.total_tokens != sum(
        (metric.input_tokens or 0) + (metric.output_tokens or 0) for metric in result.call_metrics
    ):
        violations.append("run token total differs from call metrics")
    if result.metrics.completed_stage_count != len(CANONICAL_STAGES):
        violations.append("completed stage count differs from canonical stage count")
    return ComplianceReport(compliant=not violations, violations=tuple(violations))


def assert_run_compliance(result: RunResult, expected_context: RunContext) -> None:
    report = validate_run_compliance(result, expected_context)
    if not report.compliant:
        raise AssertionError("; ".join(report.violations))


def compare_run_parity(left: RunResult, right: RunResult) -> ParityReport:
    controls = (
        left.context.snapshot_hash,
        left.context.config_hash,
        left.context.prompt_bundle_hash,
        left.context.model_id,
        left.context.seed,
    ) == (
        right.context.snapshot_hash,
        right.context.config_hash,
        right.context.prompt_bundle_hash,
        right.context.model_id,
        right.context.seed,
    )
    left_hashes = _successful_stage_hashes(left)
    right_hashes = _successful_stage_hashes(right)
    stage_sets_equal = set(left_hashes) == set(right_hashes) == set(CANONICAL_STAGES)
    logical_equal = left.metrics.logical_call_count == right.metrics.logical_call_count
    first_divergence = next(
        (stage for stage in CANONICAL_STAGES if left_hashes.get(stage) != right_hashes.get(stage)), None
    )
    violations = []
    if not controls:
        violations.append("experimental controls differ")
    if not stage_sets_equal:
        violations.append("canonical successful stage sets differ")
    if not logical_equal:
        violations.append("logical call counts differ")
    return ParityReport(
        controls_equal=controls,
        stage_sets_equal=stage_sets_equal,
        logical_call_counts_equal=logical_equal,
        final_actions_equal=left.final_decision.action == right.final_decision.action,
        first_divergence_stage=first_divergence,
        violations=tuple(violations),
    )


def validate_dependency_graph() -> None:
    positions = {stage: index for index, stage in enumerate(CANONICAL_STAGES)}
    if tuple(STAGE_DEPENDENCIES) != CANONICAL_STAGES:
        raise ValueError("dependency graph keys must follow canonical stage order")
    for stage, dependencies in STAGE_DEPENDENCIES.items():
        unknown = [dependency for dependency in dependencies if dependency not in positions]
        if unknown:
            raise ValueError(f"{stage} has unknown dependencies: {unknown}")
        late = [dependency for dependency in dependencies if positions[dependency] >= positions[stage]]
        if late:
            raise ValueError(f"{stage} has non-prior dependencies: {late}")


def scan_adapter_source(path: Path) -> tuple[str, ...]:
    """Reject provider/data access in thin framework adapters."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    violations: list[str] = []
    for node in ast.walk(tree):
        names: tuple[str, ...] = ()
        if isinstance(node, ast.Import):
            names = tuple(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = (node.module,)
        for name in names:
            if any(name == blocked or name.startswith(blocked + ".") for blocked in PROHIBITED_ADAPTER_IMPORTS):
                violations.append(f"line {node.lineno}: prohibited adapter import {name}")
    return tuple(violations)


def _successful_stage_hashes(result: RunResult) -> dict[str, str | None]:
    return {
        metric.stage: metric.output_hash
        for metric in result.stage_metrics
        if metric.status == RunStatus.SUCCESS
    }
