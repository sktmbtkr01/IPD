import asyncio

import pytest
from pydantic import ValidationError

from benchmark.agents.contracts import AnalystReport, CallStatus, Framework, RunContext
from benchmark.llm import (
    BedrockConfig,
    BedrockTransport,
    DeterministicFakeTransport,
    InstrumentedLLMClient,
    LLMExecutionError,
    LLMProviderError,
    ProviderResponse,
    RetryPolicy,
    TokenUsage,
)


def context() -> RunContext:
    return RunContext(
        run_id="run-1",
        experiment_id="experiment-1",
        framework=Framework.REFERENCE,
        framework_version="1.0.0",
        model_id="test-model",
        snapshot_hash="a" * 64,
        config_hash="b" * 64,
        prompt_bundle_hash="c" * 64,
        seed=7,
        code_version="test",
    )


def report_payload():
    return {
        "agent": "market_analyst",
        "thesis": "Momentum is mixed.",
        "key_evidence": ["RSI is neutral"],
        "bullish_factors": ["Positive return"],
        "bearish_factors": ["Elevated volatility"],
        "uncertainty": ["Short sample"],
    }


def provider_response(output=None) -> ProviderResponse:
    return ProviderResponse(
        output=output or report_payload(),
        usage=TokenUsage(input_tokens=100, output_tokens=40, total_tokens=140),
        cost_usd=0.001,
        provider_request_id="request-1",
        finish_reason="stop",
    )


def run_call(client: InstrumentedLLMClient):
    return asyncio.run(
        client.generate_structured(
            agent_name="market_analyst",
            system_prompt="fixed prompt",
            user_payload={"snapshot_hash": "a" * 64},
            output_schema=AnalystReport,
            run_context=context(),
        )
    )


def test_valid_structured_call_records_usage_cost_and_metric():
    transport = DeterministicFakeTransport({"market_analyst": provider_response()})
    result = run_call(InstrumentedLLMClient(transport))

    assert result.value == AnalystReport.model_validate(report_payload())
    assert result.usage.total_tokens == 140
    assert result.cost_usd == 0.001
    assert len(result.call_metrics) == 1
    assert result.call_metrics[0].status == CallStatus.SUCCESS
    assert result.call_metrics[0].provider_request_id == "request-1"
    assert transport.requests[0]["output_schema"] == "AnalystReport"


def test_invalid_structured_output_retries_then_succeeds():
    transport = DeterministicFakeTransport(
        {"market_analyst": [provider_response({"agent": "market_analyst"}), provider_response()]}
    )
    delays: list[float] = []

    async def record_delay(delay: float):
        delays.append(delay)

    client = InstrumentedLLMClient(
        transport,
        RetryPolicy(max_attempts=2, initial_backoff_seconds=0.25),
        sleep=record_delay,
    )
    result = run_call(client)

    assert transport.calls["market_analyst"] == 2
    assert [metric.status for metric in result.call_metrics] == [CallStatus.FAILED, CallStatus.SUCCESS]
    assert result.call_metrics[0].error_type == "STRUCTURED_OUTPUT_INVALID"
    assert delays == [0.25]


def test_retryable_provider_error_retries():
    transient = LLMProviderError("LLM_RATE_LIMIT", "slow down", retryable=True)
    transport = DeterministicFakeTransport({"market_analyst": [transient, provider_response()]})
    client = InstrumentedLLMClient(
        transport,
        RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
    )

    result = run_call(client)

    assert result.call_metrics[0].error_type == "LLM_RATE_LIMIT"
    assert result.call_metrics[1].status == CallStatus.SUCCESS


def test_exhausted_retries_preserve_all_attempt_metrics():
    transient = LLMProviderError("LLM_TIMEOUT", "timeout", retryable=True)
    transport = DeterministicFakeTransport({"market_analyst": [transient, transient]})
    client = InstrumentedLLMClient(
        transport,
        RetryPolicy(max_attempts=2, initial_backoff_seconds=0),
    )

    with pytest.raises(LLMExecutionError) as raised:
        run_call(client)

    assert raised.value.cause.code == "LLM_TIMEOUT"
    assert len(raised.value.call_metrics) == 2
    assert all(metric.status == CallStatus.FAILED for metric in raised.value.call_metrics)


def test_non_retryable_error_stops_immediately():
    fatal = LLMProviderError("LLM_PROVIDER_ERROR", "bad request", retryable=False)
    transport = DeterministicFakeTransport({"market_analyst": [fatal, provider_response()]})

    with pytest.raises(LLMExecutionError) as raised:
        run_call(InstrumentedLLMClient(transport))

    assert len(raised.value.call_metrics) == 1
    assert transport.calls["market_analyst"] == 1


class RecordingInvoker:
    def __init__(self):
        self.request = None

    async def invoke(self, request):
        self.request = request
        return {
            "output": report_payload(),
            "usage": {"input_tokens": 1_000, "output_tokens": 500},
            "request_id": "bedrock-1",
            "finish_reason": "end_turn",
        }


def test_bedrock_transport_passes_schema_controls_and_estimates_cost():
    invoker = RecordingInvoker()
    transport = BedrockTransport(
        BedrockConfig(
            model_id="provider.model-v1",
            region="us-east-1",
            temperature=0,
            max_tokens=512,
            input_cost_per_million=2,
            output_cost_per_million=4,
        ),
        invoker,
    )
    response = asyncio.run(
        transport.generate(
            agent_name="market_analyst",
            system_prompt="fixed prompt",
            user_payload={"data": "fixed"},
            output_schema=AnalystReport,
            run_context=context(),
        )
    )

    assert invoker.request["inference"] == {"temperature": 0.0, "max_tokens": 512}
    assert invoker.request["output_json_schema"]["title"] == "AnalystReport"
    assert invoker.request["metadata"]["snapshot_hash"] == "a" * 64
    assert response.usage.total_tokens == 1_500
    assert response.cost_usd == pytest.approx(0.004)


def test_bedrock_config_rejects_invalid_controls():
    with pytest.raises(ValidationError):
        BedrockConfig(model_id="model", region="region", temperature=1.1)
    with pytest.raises(ValidationError):
        BedrockConfig(model_id="model", region="region", max_tokens=0)
