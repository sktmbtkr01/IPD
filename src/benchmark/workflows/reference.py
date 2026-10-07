from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter

from benchmark.agents.contracts import (
    RiskProfile,
    RunContext,
    RunMetrics,
    RunResult,
    RunStatus,
    WorkflowState,
)
from benchmark.agents.prompt_registry import PromptRegistry
from benchmark.agents.stages import (
    StageExecution,
    StageExecutionError,
    apply_stage_output,
    completed_stages,
    execute_stage,
)
from benchmark.core.hashing import content_hash
from benchmark.core.schemas import MarketSnapshot
from benchmark.execution.contracts import WorkflowCheckpoint
from benchmark.llm.contracts import LLMClient
from benchmark.workflows.contracts import CANONICAL_STAGES


EXECUTION_LAYERS = (
    ("market_analyst", "news_analyst", "sentiment_analyst", "fundamentals_analyst"),
    ("bull_researcher", "bear_researcher"),
    ("research_manager",),
    ("trader",),
    ("risk_aggressive", "risk_neutral", "risk_conservative"),
    ("portfolio_manager",),
)


class WorkflowExecutionError(Exception):
    def __init__(self, cause: StageExecutionError, checkpoint: WorkflowCheckpoint) -> None:
        super().__init__(str(cause))
        self.error = cause.error
        self.checkpoint = checkpoint


class ReferenceWorkflowRunner:
    """Canonical executor used as the semantic oracle for framework adapters."""

    def __init__(self, llm_client: LLMClient, prompt_registry: PromptRegistry | None = None) -> None:
        self.llm_client = llm_client
        self.prompt_registry = prompt_registry or PromptRegistry()

    async def run_workflow(
        self,
        snapshot: MarketSnapshot,
        run_context: RunContext,
        checkpoint: WorkflowCheckpoint | None = None,
    ) -> RunResult:
        self._validate_identity(snapshot, run_context, checkpoint)
        started_clock = perf_counter()
        if checkpoint is None:
            started_at = datetime.now(UTC)
            state = WorkflowState(snapshot=snapshot)
            call_metrics = []
            stage_metrics = []
            resume_count = 0
            previous_elapsed_ms = 0.0
        else:
            started_at = checkpoint.started_at
            state = checkpoint.state
            call_metrics = list(checkpoint.call_metrics)
            stage_metrics = list(checkpoint.stage_metrics)
            resume_count = checkpoint.resume_count + 1
            previous_elapsed_ms = checkpoint.elapsed_ms

        for layer in EXECUTION_LAYERS:
            pending = tuple(stage for stage in layer if stage not in completed_stages(state))
            if not pending:
                continue
            results = await asyncio.gather(
                *(
                    execute_stage(stage, state, run_context, self.llm_client, self.prompt_registry)
                    for stage in pending
                ),
                return_exceptions=True,
            )
            failures: list[StageExecutionError] = []
            successes: dict[str, StageExecution] = {}
            for stage, result in zip(pending, results, strict=True):
                if isinstance(result, StageExecutionError):
                    failures.append(result)
                    call_metrics.extend(result.call_metrics)
                    stage_metrics.append(result.stage_metric)
                elif isinstance(result, Exception):
                    # execute_stage is expected to normalize every exception.
                    raise AssertionError(f"unnormalized stage error in {stage}: {result}") from result
                else:
                    successes[stage] = result
            for stage in pending:
                if stage in successes:
                    result = successes[stage]
                    state = apply_stage_output(stage, state, result.output)
                    call_metrics.extend(result.call_metrics)
                    stage_metrics.append(result.stage_metric)
            if failures:
                checkpoint_value = WorkflowCheckpoint(
                    context=run_context,
                    state=state,
                    call_metrics=tuple(call_metrics),
                    stage_metrics=tuple(stage_metrics),
                    started_at=started_at,
                    elapsed_ms=previous_elapsed_ms + max(0.0, (perf_counter() - started_clock) * 1000),
                    resume_count=resume_count,
                )
                first = min(failures, key=lambda failure: CANONICAL_STAGES.index(failure.error.stage or ""))
                raise WorkflowExecutionError(first, checkpoint_value) from first

        finished_at = datetime.now(UTC)
        end_to_end_ms = previous_elapsed_ms + max(0.0, (perf_counter() - started_clock) * 1000)
        metrics = self._aggregate_metrics(started_at, finished_at, end_to_end_ms, call_metrics, stage_metrics)
        return self._build_result(run_context, state, tuple(call_metrics), tuple(stage_metrics), metrics)

    def _validate_identity(
        self,
        snapshot: MarketSnapshot,
        context: RunContext,
        checkpoint: WorkflowCheckpoint | None,
    ) -> None:
        if not snapshot.snapshot_hash:
            raise ValueError("workflow requires a frozen snapshot_hash")
        if context.snapshot_hash != snapshot.snapshot_hash:
            raise ValueError("run context snapshot_hash does not match snapshot")
        if context.prompt_bundle_hash != self.prompt_registry.bundle_hash():
            raise ValueError("run context prompt_bundle_hash does not match prompt registry")
        if checkpoint is not None:
            if checkpoint.context != context:
                raise ValueError("checkpoint context does not match requested run")
            if checkpoint.state.snapshot != snapshot:
                raise ValueError("checkpoint snapshot does not match requested snapshot")
            completed = completed_stages(checkpoint.state)
            metric_stages = tuple(metric.stage for metric in checkpoint.stage_metrics if metric.status == RunStatus.SUCCESS)
            if len(metric_stages) != len(set(metric_stages)) or set(completed) != set(metric_stages):
                raise ValueError("checkpoint completed state and successful stage metrics differ")

    @staticmethod
    def _aggregate_metrics(started_at, finished_at, end_to_end_ms, calls, stages) -> RunMetrics:
        input_tokens = sum(metric.input_tokens or 0 for metric in calls)
        output_tokens = sum(metric.output_tokens or 0 for metric in calls)
        llm_latency_ms = sum(metric.latency_ms for metric in calls)
        deterministic_ms = sum(metric.deterministic_ms for metric in stages)
        critical_stage_path_ms = sum(
            max(
                (metric.duration_ms for metric in stages if metric.stage in layer),
                default=0.0,
            )
            for layer in EXECUTION_LAYERS
        )
        return RunMetrics(
            started_at=started_at,
            finished_at=finished_at,
            end_to_end_ms=end_to_end_ms,
            llm_latency_ms=llm_latency_ms,
            deterministic_ms=deterministic_ms,
            # Layer maxima approximate useful critical-path work without double
            # counting concurrent stage durations. The remainder is scheduler,
            # state-merge, and event-loop overhead.
            orchestration_overhead_ms=max(0.0, end_to_end_ms - critical_stage_path_ms),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=sum(metric.cost_usd or 0 for metric in calls),
            logical_call_count=len({metric.stage for metric in stages}),
            physical_attempt_count=len(calls),
            retry_count=sum(metric.retry_count for metric in stages),
            validation_failure_count=sum(metric.validation_failures for metric in stages),
            completed_stage_count=len({metric.stage for metric in stages if metric.status == RunStatus.SUCCESS}),
        )

    @staticmethod
    def _build_result(context, state, calls, stages, metrics) -> RunResult:
        missing = [stage for stage in CANONICAL_STAGES if stage not in completed_stages(state)]
        if missing:
            raise ValueError(f"cannot build successful result; missing stages: {missing}")
        return RunResult(
            context=context,
            market_report=state.analyst_reports["market_analyst"],
            news_report=state.analyst_reports["news_analyst"],
            sentiment_report=state.analyst_reports["sentiment_analyst"],
            fundamentals_report=state.analyst_reports["fundamentals_analyst"],
            bull_argument=state.bull_argument,
            bear_argument=state.bear_argument,
            research_manager=state.research_manager,
            trader=state.trader,
            aggressive_risk=state.risk_reports[RiskProfile.AGGRESSIVE],
            neutral_risk=state.risk_reports[RiskProfile.NEUTRAL],
            conservative_risk=state.risk_reports[RiskProfile.CONSERVATIVE],
            final_decision=state.final_decision,
            call_metrics=calls,
            stage_metrics=stages,
            metrics=metrics,
            status=RunStatus.SUCCESS,
        )


def checkpoint_hash(checkpoint: WorkflowCheckpoint) -> str:
    return content_hash(checkpoint)
