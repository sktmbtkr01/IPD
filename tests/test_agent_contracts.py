from datetime import date,datetime,timedelta,timezone
import pytest
from pydantic import ValidationError
from benchmark.agents.contracts import *
from benchmark.core.schemas import *
from benchmark.workflows.contracts import CANONICAL_STAGES,STAGE_DEPENDENCIES

NOW=datetime(2026,1,1,tzinfo=timezone.utc)

def analyst(name): return AnalystReport(agent=name,thesis="thesis",key_evidence=("e",),bullish_factors=(),bearish_factors=(),uncertainty=())
def metric(stage): return LLMCallMetric(call_id=stage,run_id="run",stage=stage,attempt=1,started_at=NOW,finished_at=NOW+timedelta(milliseconds=1),latency_ms=1,input_tokens=10,output_tokens=5,cost_usd=0.01,status="SUCCESS")
def stage_metric(stage): return StageMetric(stage=stage,started_at=NOW,finished_at=NOW+timedelta(milliseconds=1),duration_ms=1,llm_latency_ms=1,deterministic_ms=0,call_count=1,retry_count=0,validation_failures=0,input_state_hash="i",output_hash="o",status="SUCCESS")

def complete_result():
    reports=[analyst(x) for x in ("market_analyst","news_analyst","sentiment_analyst","fundamentals_analyst")]
    bull=ResearchArgument(side="BULL",thesis="bull",evidence=("e",),counterarguments=(),risks=())
    bear=ResearchArgument(side="BEAR",thesis="bear",evidence=("e",),counterarguments=(),risks=())
    manager=ResearchManagerReport(synthesis="balanced",recommendation="HOLD",reasons=("r",),unresolved_risks=())
    trader=TraderPlan(proposed_action="HOLD",rationale="r",constraints=())
    risks=[RiskReport(profile=p,stance="APPROVE",recommended_action="HOLD",key_risks=(),rationale="r") for p in RiskProfile]
    calls=tuple(metric(x) for x in CANONICAL_STAGES); stages=tuple(stage_metric(x) for x in CANONICAL_STAGES)
    totals=RunMetrics(started_at=NOW,finished_at=NOW+timedelta(milliseconds=12),end_to_end_ms=12,llm_latency_ms=12,
      deterministic_ms=0,orchestration_overhead_ms=0,input_tokens=120,output_tokens=60,total_tokens=180,cost_usd=.12,
      logical_call_count=12,physical_attempt_count=12,retry_count=0,validation_failure_count=0,completed_stage_count=12)
    return RunResult(context=RunContext(run_id="run",experiment_id="exp",framework="REFERENCE",framework_version="1",
      model_id="fake",snapshot_hash="snapshot",config_hash="config",prompt_bundle_hash="prompts"),
      market_report=reports[0],news_report=reports[1],sentiment_report=reports[2],fundamentals_report=reports[3],
      bull_argument=bull,bear_argument=bear,research_manager=manager,trader=trader,aggressive_risk=risks[0],neutral_risk=risks[1],
      conservative_risk=risks[2],final_decision=FinalDecision(action="HOLD",rationale="r"),call_metrics=calls,
      stage_metrics=stages,metrics=totals,status="SUCCESS")

def test_complete_run_result_round_trips():
    result=complete_result(); assert RunResult.model_validate_json(result.model_dump_json())==result
    assert len(result.call_metrics)==12 and len(CANONICAL_STAGES)==12

def test_invalid_action_fails():
    with pytest.raises(ValidationError): FinalDecision(action="WAIT",rationale="x")

def test_token_total_must_match():
    with pytest.raises(ValidationError,match="total_tokens mismatch"):
        RunMetrics(started_at=NOW,finished_at=NOW,end_to_end_ms=0,llm_latency_ms=0,deterministic_ms=0,orchestration_overhead_ms=0,
          input_tokens=1,output_tokens=1,total_tokens=3,cost_usd=0,logical_call_count=0,physical_attempt_count=0,retry_count=0,
          validation_failure_count=0,completed_stage_count=0)

def test_call_chronology_is_validated():
    with pytest.raises(ValidationError,match="finish precedes"):
        LLMCallMetric(call_id="x",run_id="r",stage="s",attempt=1,started_at=NOW,finished_at=NOW-timedelta(seconds=1),latency_ms=1,status="FAILED")

def test_dependency_graph_references_known_stages():
    assert tuple(STAGE_DEPENDENCIES)==CANONICAL_STAGES
    assert all(dep in CANONICAL_STAGES for deps in STAGE_DEPENDENCIES.values() for dep in deps)
