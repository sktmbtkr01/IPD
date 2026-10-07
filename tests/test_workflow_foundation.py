import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from benchmark.agents.contracts import Framework, RunContext, WorkflowState
from benchmark.agents.prompt_registry import PromptRegistry
from benchmark.agents.stages import completed_stages, select_stage_input
from benchmark.core.hashing import calculate_snapshot_hash, content_hash
from benchmark.core.schemas import (
    FundamentalsSnapshot,
    MarketSnapshot,
    PriceBar,
    SentimentSummary,
    SourceMeta,
)
from benchmark.data.indicators import compute_technicals
from benchmark.execution.contracts import FailedRunArtifact
from benchmark.execution.environment import capture_environment
from benchmark.execution.run_store import RunStore
from benchmark.execution.runner import ExecutionService, PersistedWorkflowError
from benchmark.llm import (
    DeterministicFakeTransport,
    InstrumentedLLMClient,
    LLMProviderError,
    ProviderResponse,
    RetryPolicy,
    TokenUsage,
)
from benchmark.workflows.compliance import (
    assert_run_compliance,
    compare_run_parity,
    scan_adapter_source,
    validate_dependency_graph,
)
from benchmark.workflows.reference import ReferenceWorkflowRunner, WorkflowExecutionError


def frozen_snapshot() -> MarketSnapshot:
    bars = tuple(
        PriceBar(
            timestamp=datetime(2025, 1, 2, tzinfo=UTC) + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            adjusted_close=101 + index,
            volume=1_000 + index,
        )
        for index in range(60)
    )
    snapshot = MarketSnapshot(
        schema_version="1.1.0",
        ticker="AAPL",
        decision_date=datetime(2025, 4, 30, tzinfo=UTC).date(),
        information_cutoff=datetime(2025, 4, 30, 20, tzinfo=UTC),
        price_bars=bars,
        technicals=compute_technicals(bars),
        sentiment=SentimentSummary(available=False, article_count=0),
        fundamentals=FundamentalsSnapshot(available=False),
        source_meta={
            "fixture": SourceMeta(
                provider="fixture",
                retrieved_at=datetime(2025, 5, 1, tzinfo=UTC),
                request_key="fixture",
                available=True,
            )
        },
    )
    return snapshot.model_copy(update={"snapshot_hash": calculate_snapshot_hash(snapshot)})


def run_context(snapshot: MarketSnapshot, framework: Framework = Framework.REFERENCE, run_id="run-1"):
    return RunContext(
        run_id=run_id,
        experiment_id="foundation-test",
        framework=framework,
        framework_version="test-1",
        model_id="deterministic-fake",
        snapshot_hash=snapshot.snapshot_hash,
        config_hash=content_hash({"test": True}),
        prompt_bundle_hash=PromptRegistry().bundle_hash(),
        seed=42,
        code_version="test",
    )


def output_payloads():
    analyst = lambda agent: {
        "agent": agent,
        "thesis": f"{agent} thesis",
        "key_evidence": [f"{agent} evidence"],
        "bullish_factors": ["positive"],
        "bearish_factors": ["negative"],
        "uncertainty": ["uncertain"],
    }
    risk = lambda profile: {
        "profile": profile,
        "stance": "APPROVE",
        "recommended_action": "HOLD",
        "key_risks": ["uncertainty"],
        "rationale": "Risk is balanced.",
    }
    return {
        "market_analyst": analyst("market_analyst"),
        "news_analyst": analyst("news_analyst"),
        "sentiment_analyst": analyst("sentiment_analyst"),
        "fundamentals_analyst": analyst("fundamentals_analyst"),
        "bull_researcher": {
            "side": "BULL", "thesis": "Bull case", "evidence": ["positive"],
            "counterarguments": ["negative"], "risks": ["uncertainty"],
        },
        "bear_researcher": {
            "side": "BEAR", "thesis": "Bear case", "evidence": ["negative"],
            "counterarguments": ["positive"], "risks": ["uncertainty"],
        },
        "research_manager": {
            "synthesis": "Balanced", "recommendation": "HOLD", "reasons": ["mixed"],
            "unresolved_risks": ["uncertainty"],
        },
        "trader": {
            "proposed_action": "HOLD", "rationale": "Wait", "sizing": None,
            "constraints": ["No sizing policy"],
        },
        "risk_aggressive": risk("AGGRESSIVE"),
        "risk_neutral": risk("NEUTRAL"),
        "risk_conservative": risk("CONSERVATIVE"),
        "portfolio_manager": {"action": "HOLD", "rationale": "Evidence is balanced.", "confidence": 0.6},
    }


def response(payload, request_id="fake"):
    return ProviderResponse(
        output=payload,
        usage=TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        cost_usd=0.0001,
        provider_request_id=request_id,
    )


def runner_with(responses):
    transport = DeterministicFakeTransport(responses)
    client = InstrumentedLLMClient(
        transport, RetryPolicy(max_attempts=1, initial_backoff_seconds=0)
    )
    return ReferenceWorkflowRunner(client), transport


def all_responses():
    return {stage: response(payload, stage) for stage, payload in output_payloads().items()}


def test_minimum_input_selectors_do_not_leak_other_snapshot_domains():
    state = WorkflowState(snapshot=frozen_snapshot())
    market = select_stage_input("market_analyst", state)
    news = select_stage_input("news_analyst", state)
    fundamentals = select_stage_input("fundamentals_analyst", state)

    assert "news" not in market and "fundamentals" not in market
    assert "price_bars" not in news and "sentiment" not in news
    assert set(fundamentals) == {
        "ticker", "decision_date", "information_cutoff", "snapshot_hash", "fundamentals"
    }


def test_snapshot_and_workflow_mappings_are_deeply_immutable():
    snapshot = frozen_snapshot()
    state = WorkflowState(snapshot=snapshot)

    with pytest.raises(TypeError, match="immutable"):
        snapshot.source_meta["new"] = snapshot.source_meta["fixture"]
    with pytest.raises(TypeError, match="immutable"):
        state.analyst_reports["market_analyst"] = None


def test_reference_workflow_completes_all_stages_and_is_compliant():
    snapshot = frozen_snapshot()
    context = run_context(snapshot)
    runner, transport = runner_with(all_responses())

    result = asyncio.run(runner.run_workflow(snapshot, context))

    assert result.final_decision.action.value == "HOLD"
    assert result.metrics.logical_call_count == 12
    assert result.metrics.physical_attempt_count == 12
    assert result.metrics.total_tokens == 180
    assert len(completed_stages(WorkflowState(
        snapshot=snapshot,
        analyst_reports={
            "market_analyst": result.market_report,
            "news_analyst": result.news_report,
            "sentiment_analyst": result.sentiment_report,
            "fundamentals_analyst": result.fundamentals_report,
        },
        bull_argument=result.bull_argument,
        bear_argument=result.bear_argument,
        research_manager=result.research_manager,
        trader=result.trader,
        risk_reports={
            result.aggressive_risk.profile: result.aggressive_risk,
            result.neutral_risk.profile: result.neutral_risk,
            result.conservative_risk.profile: result.conservative_risk,
        },
        final_decision=result.final_decision,
    ))) == 12
    assert_run_compliance(result, context)
    assert len(transport.requests) == 12


def test_stage_identity_mismatch_is_rejected_as_structured_output_failure():
    configured = all_responses()
    configured["market_analyst"] = response(output_payloads()["news_analyst"])
    snapshot = frozen_snapshot()
    runner, _ = runner_with(configured)

    with pytest.raises(WorkflowExecutionError) as raised:
        asyncio.run(runner.run_workflow(snapshot, run_context(snapshot)))

    assert raised.value.error.code == "STRUCTURED_OUTPUT_INVALID"
    assert raised.value.error.stage == "market_analyst"


def test_failure_checkpoint_can_resume_without_repeating_completed_stages(tmp_path):
    configured = all_responses()
    configured["market_analyst"] = [
        LLMProviderError("LLM_TIMEOUT", "temporary", retryable=True),
        response(output_payloads()["market_analyst"]),
    ]
    snapshot = frozen_snapshot()
    context = run_context(snapshot)
    runner, transport = runner_with(configured)

    with pytest.raises(WorkflowExecutionError) as raised:
        asyncio.run(runner.run_workflow(snapshot, context))
    checkpoint = raised.value.checkpoint
    assert set(completed_stages(checkpoint.state)) == {
        "news_analyst", "sentiment_analyst", "fundamentals_analyst"
    }

    failure = FailedRunArtifact(
        context=context,
        error=raised.value.error,
        checkpoint=checkpoint,
        failed_at=datetime.now(UTC),
        environment=capture_environment(()),
    )
    store = RunStore(tmp_path)
    failure_path = store.save_failure(failure)
    checkpoint_path = store.save_checkpoint(checkpoint)
    assert failure_path.exists() and checkpoint_path.exists()

    result = asyncio.run(runner.run_workflow(snapshot, context, checkpoint))
    assert result.status.value == "SUCCESS"
    assert result.metrics.logical_call_count == 12
    assert result.metrics.physical_attempt_count == 13
    assert transport.calls["news_analyst"] == 1

    result_path = store.save_result(result)
    loaded = store.load_result(context.experiment_id, context.framework.value, context.run_id)
    assert result_path.exists() and loaded.result == result
    assert store.save_result(result) == result_path


def test_parity_report_distinguishes_controls_from_behavior():
    snapshot = frozen_snapshot()
    first_context = run_context(snapshot, Framework.LANGGRAPH, "run-langgraph")
    second_context = run_context(snapshot, Framework.CREWAI, "run-crewai")
    first, _ = runner_with(all_responses())
    second, _ = runner_with(all_responses())
    left = asyncio.run(first.run_workflow(snapshot, first_context))
    right = asyncio.run(second.run_workflow(snapshot, second_context))

    report = compare_run_parity(left, right)

    assert report.controls_equal and report.stage_sets_equal
    assert report.final_actions_equal
    assert report.first_divergence_stage is None


def test_execution_service_automatically_persists_failures(tmp_path):
    configured = all_responses()
    configured["market_analyst"] = LLMProviderError("LLM_TIMEOUT", "temporary", retryable=True)
    snapshot = frozen_snapshot()
    runner, _ = runner_with(configured)
    service = ExecutionService(runner, RunStore(tmp_path))

    with pytest.raises(PersistedWorkflowError) as raised:
        asyncio.run(service.execute(snapshot, run_context(snapshot)))

    assert raised.value.failure_path.exists()
    assert raised.value.checkpoint_path.exists()
    assert raised.value.error.code == "LLM_TIMEOUT"


def test_adapter_template_has_no_prohibited_provider_or_data_imports():
    import benchmark.workflows.adapter_template as adapter_template

    assert scan_adapter_source(__import__("pathlib").Path(adapter_template.__file__)) == ()
    validate_dependency_graph()
