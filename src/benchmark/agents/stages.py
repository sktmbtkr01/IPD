from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel

from benchmark.agents.contracts import (
    AnalystReport,
    CallStatus,
    FinalDecision,
    LLMCallMetric,
    NormalizedError,
    ResearchArgument,
    ResearchManagerReport,
    ResearchSide,
    RiskProfile,
    RiskReport,
    RunContext,
    RunStatus,
    StageMetric,
    TraderPlan,
    WorkflowState,
)
from benchmark.agents.prompt_registry import PromptRegistry
from benchmark.core.hashing import canonical_json, content_hash
from benchmark.llm.contracts import LLMClient, LLMExecutionError
from benchmark.workflows.contracts import CANONICAL_STAGES, STAGE_DEPENDENCIES


ANALYST_STAGES = {
    "market_analyst",
    "news_analyst",
    "sentiment_analyst",
    "fundamentals_analyst",
}


class MarketAnalystOutput(AnalystReport):
    agent: Literal["market_analyst"]


class NewsAnalystOutput(AnalystReport):
    agent: Literal["news_analyst"]


class SentimentAnalystOutput(AnalystReport):
    agent: Literal["sentiment_analyst"]


class FundamentalsAnalystOutput(AnalystReport):
    agent: Literal["fundamentals_analyst"]


class BullResearchOutput(ResearchArgument):
    side: Literal[ResearchSide.BULL]


class BearResearchOutput(ResearchArgument):
    side: Literal[ResearchSide.BEAR]


class AggressiveRiskOutput(RiskReport):
    profile: Literal[RiskProfile.AGGRESSIVE]


class NeutralRiskOutput(RiskReport):
    profile: Literal[RiskProfile.NEUTRAL]


class ConservativeRiskOutput(RiskReport):
    profile: Literal[RiskProfile.CONSERVATIVE]


RISK_STAGE_PROFILES = {
    "risk_aggressive": RiskProfile.AGGRESSIVE,
    "risk_neutral": RiskProfile.NEUTRAL,
    "risk_conservative": RiskProfile.CONSERVATIVE,
}
OUTPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "market_analyst": MarketAnalystOutput,
    "news_analyst": NewsAnalystOutput,
    "sentiment_analyst": SentimentAnalystOutput,
    "fundamentals_analyst": FundamentalsAnalystOutput,
    "bull_researcher": BullResearchOutput,
    "bear_researcher": BearResearchOutput,
    "research_manager": ResearchManagerReport,
    "trader": TraderPlan,
    "risk_aggressive": AggressiveRiskOutput,
    "risk_neutral": NeutralRiskOutput,
    "risk_conservative": ConservativeRiskOutput,
    "portfolio_manager": FinalDecision,
}


@dataclass(frozen=True)
class StageExecution:
    stage: str
    output: BaseModel
    state: WorkflowState
    call_metrics: tuple[LLMCallMetric, ...]
    stage_metric: StageMetric


class StageExecutionError(Exception):
    def __init__(
        self,
        error: NormalizedError,
        call_metrics: tuple[LLMCallMetric, ...],
        stage_metric: StageMetric,
    ) -> None:
        super().__init__(error.message)
        self.error = error
        self.call_metrics = call_metrics
        self.stage_metric = stage_metric


def select_stage_input(stage: str, state: WorkflowState) -> dict[str, Any]:
    """Return the exact, minimum canonical payload permitted for one role."""
    if stage not in CANONICAL_STAGES:
        raise KeyError(f"unknown canonical stage: {stage}")
    _require_dependencies(stage, state)
    snapshot = state.snapshot
    identity = {
        "ticker": snapshot.ticker,
        "decision_date": snapshot.decision_date,
        "information_cutoff": snapshot.information_cutoff,
        "snapshot_hash": snapshot.snapshot_hash,
    }
    if stage == "market_analyst":
        return {**identity, "price_bars": snapshot.price_bars, "technicals": snapshot.technicals}
    if stage == "news_analyst":
        return {**identity, "news": snapshot.news}
    if stage == "sentiment_analyst":
        supporting_sentiment = tuple(
            {
                "id": item.id,
                "published_at": item.published_at,
                "ticker_relevance": item.ticker_relevance,
                "ticker_sentiment_score": item.ticker_sentiment_score,
                "ticker_sentiment_label": item.ticker_sentiment_label,
            }
            for item in snapshot.news
        )
        return {**identity, "sentiment": snapshot.sentiment, "supporting_sentiment": supporting_sentiment}
    if stage == "fundamentals_analyst":
        return {**identity, "fundamentals": snapshot.fundamentals}
    if stage in {"bull_researcher", "bear_researcher"}:
        return {"analyst_reports": _ordered_analyst_reports(state)}
    if stage == "research_manager":
        return {"bull_argument": state.bull_argument, "bear_argument": state.bear_argument}
    if stage == "trader":
        return {"research_manager": state.research_manager, "portfolio_constraints": ()}
    if stage in RISK_STAGE_PROFILES:
        return {"research_manager": state.research_manager, "trader": state.trader}
    return {
        "research_manager": state.research_manager,
        "trader": state.trader,
        "risk_reports": {
            profile.value: state.risk_reports[profile]
            for profile in (RiskProfile.AGGRESSIVE, RiskProfile.NEUTRAL, RiskProfile.CONSERVATIVE)
        },
    }


async def execute_stage(
    stage: str,
    state: WorkflowState,
    run_context: RunContext,
    llm_client: LLMClient,
    prompt_registry: PromptRegistry,
) -> StageExecution:
    started_at = datetime.now(UTC)
    started_clock = perf_counter()
    payload = select_stage_input(stage, state)
    input_hash = content_hash(payload)
    prompt = prompt_registry.load(stage)
    schema = OUTPUT_SCHEMAS[stage]
    try:
        result = await llm_client.generate_structured(
            agent_name=stage,
            system_prompt=prompt.text,
            user_payload=_json_payload(payload),
            output_schema=schema,
            run_context=run_context,
        )
        _validate_stage_identity(stage, result.value)
        updated = apply_stage_output(stage, state, result.value)
    except LLMExecutionError as exc:
        finished_at = datetime.now(UTC)
        llm_latency = sum(metric.latency_ms for metric in exc.call_metrics)
        stage_metric = _stage_metric(
            stage,
            started_at,
            started_clock,
            llm_latency,
            exc.call_metrics,
            input_hash,
            None,
            RunStatus.FAILED,
        )
        code = exc.cause.code if exc.cause.code in NormalizedError.model_fields["code"].annotation.__args__ else "LLM_PROVIDER_ERROR"
        raise StageExecutionError(
            NormalizedError(
                code=code,
                stage=stage,
                message=str(exc.cause),
                retryable=exc.cause.retryable,
                details={"attempts": len(exc.call_metrics)},
            ),
            exc.call_metrics,
            stage_metric.model_copy(update={"finished_at": finished_at}),
        ) from exc
    except Exception as exc:
        finished_at = datetime.now(UTC)
        stage_metric = _stage_metric(
            stage, started_at, started_clock, 0, (), input_hash, None, RunStatus.FAILED
        ).model_copy(update={"finished_at": finished_at})
        raise StageExecutionError(
            NormalizedError(
                code="FRAMEWORK_EXECUTION_ERROR",
                stage=stage,
                message=str(exc),
                retryable=False,
                details={"exception_type": type(exc).__name__},
            ),
            (),
            stage_metric,
        ) from exc

    llm_latency = sum(metric.latency_ms for metric in result.call_metrics)
    stage_metric = _stage_metric(
        stage,
        started_at,
        started_clock,
        llm_latency,
        result.call_metrics,
        input_hash,
        content_hash(result.value),
        RunStatus.SUCCESS,
    )
    return StageExecution(stage, result.value, updated, result.call_metrics, stage_metric)


def apply_stage_output(stage: str, state: WorkflowState, output: BaseModel) -> WorkflowState:
    _validate_stage_identity(stage, output)
    if stage in ANALYST_STAGES:
        reports = dict(state.analyst_reports)
        reports[stage] = AnalystReport.model_validate(output.model_dump(mode="python"))
        return state.model_copy(update={"analyst_reports": reports})
    field_updates: dict[str, Any]
    if stage == "bull_researcher":
        field_updates = {"bull_argument": ResearchArgument.model_validate(output.model_dump(mode="python"))}
    elif stage == "bear_researcher":
        field_updates = {"bear_argument": ResearchArgument.model_validate(output.model_dump(mode="python"))}
    elif stage == "research_manager":
        field_updates = {"research_manager": ResearchManagerReport.model_validate(output.model_dump(mode="python"))}
    elif stage == "trader":
        field_updates = {"trader": TraderPlan.model_validate(output.model_dump(mode="python"))}
    elif stage in RISK_STAGE_PROFILES:
        reports = dict(state.risk_reports)
        reports[RISK_STAGE_PROFILES[stage]] = RiskReport.model_validate(output.model_dump(mode="python"))
        field_updates = {"risk_reports": reports}
    elif stage == "portfolio_manager":
        field_updates = {"final_decision": FinalDecision.model_validate(output.model_dump(mode="python"))}
    else:
        raise KeyError(f"unknown canonical stage: {stage}")
    return state.model_copy(update=field_updates)


def completed_stages(state: WorkflowState) -> tuple[str, ...]:
    completed: list[str] = []
    completed.extend(stage for stage in CANONICAL_STAGES[:4] if stage in state.analyst_reports)
    if state.bull_argument is not None:
        completed.append("bull_researcher")
    if state.bear_argument is not None:
        completed.append("bear_researcher")
    if state.research_manager is not None:
        completed.append("research_manager")
    if state.trader is not None:
        completed.append("trader")
    completed.extend(stage for stage, profile in RISK_STAGE_PROFILES.items() if profile in state.risk_reports)
    if state.final_decision is not None:
        completed.append("portfolio_manager")
    return tuple(stage for stage in CANONICAL_STAGES if stage in completed)


def _ordered_analyst_reports(state: WorkflowState) -> dict[str, AnalystReport]:
    return {stage: state.analyst_reports[stage] for stage in CANONICAL_STAGES[:4]}


def _require_dependencies(stage: str, state: WorkflowState) -> None:
    available = set(completed_stages(state))
    missing = [dependency for dependency in STAGE_DEPENDENCIES[stage] if dependency not in available]
    if missing:
        raise ValueError(f"stage {stage} missing dependencies: {missing}")


def _validate_stage_identity(stage: str, output: BaseModel) -> None:
    if stage in ANALYST_STAGES and (not isinstance(output, AnalystReport) or output.agent != stage):
        raise ValueError(f"{stage} returned the wrong analyst identity")
    if stage == "bull_researcher" and (
        not isinstance(output, ResearchArgument) or output.side != ResearchSide.BULL
    ):
        raise ValueError("bull_researcher returned the wrong research side")
    if stage == "bear_researcher" and (
        not isinstance(output, ResearchArgument) or output.side != ResearchSide.BEAR
    ):
        raise ValueError("bear_researcher returned the wrong research side")
    if stage in RISK_STAGE_PROFILES and (
        not isinstance(output, RiskReport) or output.profile != RISK_STAGE_PROFILES[stage]
    ):
        raise ValueError(f"{stage} returned the wrong risk profile")


def _json_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json(payload))


def _stage_metric(
    stage: str,
    started_at: datetime,
    started_clock: float,
    llm_latency_ms: float,
    calls: tuple[LLMCallMetric, ...],
    input_hash: str,
    output_hash: str | None,
    status: RunStatus,
) -> StageMetric:
    finished_at = datetime.now(UTC)
    duration_ms = max(0.0, (perf_counter() - started_clock) * 1000)
    return StageMetric(
        stage=stage,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        llm_latency_ms=llm_latency_ms,
        deterministic_ms=max(0.0, duration_ms - llm_latency_ms),
        call_count=len(calls),
        retry_count=max(0, len(calls) - 1),
        validation_failures=sum(
            metric.error_type == "STRUCTURED_OUTPUT_INVALID" for metric in calls if metric.status == CallStatus.FAILED
        ),
        input_state_hash=input_hash,
        output_hash=output_hash,
        status=status,
    )
