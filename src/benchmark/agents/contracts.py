from __future__ import annotations
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from pydantic import Field, field_validator, model_validator
from benchmark.core.schemas import FrozenDict, FrozenModel, MarketSnapshot, aware, frozen_dict

class Framework(StrEnum):
    LANGGRAPH="LANGGRAPH"; CREWAI="CREWAI"; AUTOGEN="AUTOGEN"; REFERENCE="REFERENCE"
class Action(StrEnum): BUY="BUY"; HOLD="HOLD"; SELL="SELL"
class ResearchSide(StrEnum): BULL="BULL"; BEAR="BEAR"
class RiskProfile(StrEnum): AGGRESSIVE="AGGRESSIVE"; NEUTRAL="NEUTRAL"; CONSERVATIVE="CONSERVATIVE"
class RiskStance(StrEnum): APPROVE="APPROVE"; MODIFY="MODIFY"; REJECT="REJECT"
class RunStatus(StrEnum): SUCCESS="SUCCESS"; FAILED="FAILED"
class CallStatus(StrEnum): SUCCESS="SUCCESS"; FAILED="FAILED"

class AnalystReport(FrozenModel):
    agent: Literal["market_analyst","news_analyst","sentiment_analyst","fundamentals_analyst"]
    thesis: str = Field(min_length=1)
    key_evidence: tuple[str,...]
    bullish_factors: tuple[str,...]
    bearish_factors: tuple[str,...]
    uncertainty: tuple[str,...]

class ResearchArgument(FrozenModel):
    side: ResearchSide
    thesis: str = Field(min_length=1)
    evidence: tuple[str,...]
    counterarguments: tuple[str,...]
    risks: tuple[str,...]

class ResearchManagerReport(FrozenModel):
    synthesis: str = Field(min_length=1)
    recommendation: Action
    reasons: tuple[str,...]
    unresolved_risks: tuple[str,...]

class TraderPlan(FrozenModel):
    proposed_action: Action
    rationale: str = Field(min_length=1)
    sizing: float | None = Field(default=None, ge=0, le=1)
    constraints: tuple[str,...]

class RiskReport(FrozenModel):
    profile: RiskProfile
    stance: RiskStance
    recommended_action: Action
    key_risks: tuple[str,...]
    rationale: str = Field(min_length=1)

class FinalDecision(FrozenModel):
    action: Action
    rationale: str = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)

class RunContext(FrozenModel):
    run_id: str; experiment_id: str; framework: Framework; framework_version: str
    model_id: str; snapshot_hash: str; config_hash: str; prompt_bundle_hash: str
    seed: int | None = None; code_version: str | None = None

class LLMCallMetric(FrozenModel):
    call_id: str; run_id: str; stage: str; attempt: int = Field(ge=1)
    started_at: datetime; finished_at: datetime; latency_ms: float = Field(ge=0)
    input_tokens: int | None = Field(default=None,ge=0); output_tokens: int | None = Field(default=None,ge=0)
    cost_usd: float | None = Field(default=None,ge=0); status: CallStatus
    error_type: str | None = None; provider_request_id: str | None = None
    _aware=field_validator("started_at","finished_at")(aware)
    @model_validator(mode="after")
    def chronology(self):
        if self.finished_at<self.started_at: raise ValueError("call finish precedes start")
        if self.status==CallStatus.SUCCESS and self.error_type is not None: raise ValueError("successful call cannot have error_type")
        return self

class StageMetric(FrozenModel):
    stage: str; started_at: datetime; finished_at: datetime
    duration_ms: float = Field(ge=0); llm_latency_ms: float = Field(ge=0)
    deterministic_ms: float = Field(ge=0); call_count: int = Field(ge=0)
    retry_count: int = Field(ge=0); validation_failures: int = Field(ge=0)
    input_state_hash: str; output_hash: str | None = None; status: RunStatus
    _aware=field_validator("started_at","finished_at")(aware)

class RunMetrics(FrozenModel):
    started_at: datetime; finished_at: datetime; end_to_end_ms: float = Field(ge=0)
    llm_latency_ms: float = Field(ge=0); deterministic_ms: float = Field(ge=0)
    orchestration_overhead_ms: float = Field(ge=0)
    input_tokens: int = Field(ge=0); output_tokens: int = Field(ge=0); total_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0); logical_call_count: int = Field(ge=0)
    physical_attempt_count: int = Field(ge=0); retry_count: int = Field(ge=0)
    validation_failure_count: int = Field(ge=0); completed_stage_count: int = Field(ge=0)
    _aware=field_validator("started_at","finished_at")(aware)
    @model_validator(mode="after")
    def totals(self):
        if self.total_tokens!=self.input_tokens+self.output_tokens: raise ValueError("total_tokens mismatch")
        if self.physical_attempt_count<self.logical_call_count: raise ValueError("attempts cannot be fewer than logical calls")
        return self

class NormalizedError(FrozenModel):
    code: Literal["DATA_UNAVAILABLE","DATA_SCHEMA_ERROR","PIT_VIOLATION","LLM_RATE_LIMIT","LLM_TIMEOUT",
      "LLM_PROVIDER_ERROR","STRUCTURED_OUTPUT_INVALID","FRAMEWORK_EXECUTION_ERROR","WORKFLOW_TIMEOUT","BACKTEST_CONFIG_ERROR"]
    stage: str | None = None; message: str; retryable: bool; details: dict[str,Any] = Field(default_factory=dict)

class WorkflowState(FrozenModel):
    snapshot: MarketSnapshot
    analyst_reports: dict[str,AnalystReport] = Field(default_factory=FrozenDict)
    bull_argument: ResearchArgument | None = None; bear_argument: ResearchArgument | None = None
    research_manager: ResearchManagerReport | None = None; trader: TraderPlan | None = None
    risk_reports: dict[RiskProfile,RiskReport] = Field(default_factory=FrozenDict); final_decision: FinalDecision | None = None
    _frozen_maps=field_validator("analyst_reports","risk_reports",mode="after")(frozen_dict)

class RunResult(FrozenModel):
    context: RunContext
    market_report: AnalystReport; news_report: AnalystReport; sentiment_report: AnalystReport; fundamentals_report: AnalystReport
    bull_argument: ResearchArgument; bear_argument: ResearchArgument; research_manager: ResearchManagerReport
    trader: TraderPlan; aggressive_risk: RiskReport; neutral_risk: RiskReport; conservative_risk: RiskReport
    final_decision: FinalDecision
    call_metrics: tuple[LLMCallMetric,...]; stage_metrics: tuple[StageMetric,...]; metrics: RunMetrics
    status: RunStatus; error: NormalizedError | None = None
    @model_validator(mode="after")
    def consistency(self):
        if self.context.snapshot_hash=="": raise ValueError("snapshot hash is required")
        if self.status==RunStatus.SUCCESS and self.error is not None: raise ValueError("successful run cannot contain error")
        expected=(RiskProfile.AGGRESSIVE,RiskProfile.NEUTRAL,RiskProfile.CONSERVATIVE)
        actual=(self.aggressive_risk.profile,self.neutral_risk.profile,self.conservative_risk.profile)
        if actual!=expected: raise ValueError("risk reports do not match required profiles")
        return self
