from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from benchmark.agents.contracts import CallStatus, LLMCallMetric, RunContext
from benchmark.llm.contracts import (
    AsyncSleep,
    LLMExecutionError,
    LLMProviderError,
    ProviderResponse,
    RawLLMTransport,
    RetryPolicy,
    StructuredLLMResult,
    T,
)


class InstrumentedLLMClient:
    """One framework-neutral structured-output and accounting boundary."""

    def __init__(
        self,
        transport: RawLLMTransport,
        retry_policy: RetryPolicy | None = None,
        *,
        sleep: AsyncSleep = asyncio.sleep,
    ) -> None:
        self.transport = transport
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleep = sleep

    async def generate_structured(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[T],
        run_context: RunContext,
    ) -> StructuredLLMResult[T]:
        metrics: list[LLMCallMetric] = []
        last_error: LLMProviderError | None = None

        for attempt in range(1, self.retry_policy.max_attempts + 1):
            if attempt > 1:
                await self.sleep(self.retry_policy.delay_before(attempt))
            started_at = datetime.now(UTC)
            started_clock = perf_counter()
            response: ProviderResponse | None = None
            try:
                response = await self.transport.generate(
                    agent_name=agent_name,
                    system_prompt=system_prompt,
                    user_payload=user_payload,
                    output_schema=output_schema,
                    run_context=run_context,
                )
                value = self._validate_output(response.output, output_schema)
            except LLMProviderError as exc:
                last_error = exc
            except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
                last_error = LLMProviderError(
                    "STRUCTURED_OUTPUT_INVALID",
                    f"{output_schema.__name__} validation failed: {exc}",
                    retryable=True,
                    provider_request_id=(response.provider_request_id if response else None),
                )
            except (TimeoutError, asyncio.TimeoutError) as exc:
                last_error = LLMProviderError("LLM_TIMEOUT", str(exc) or "LLM request timed out", retryable=True)
            except Exception as exc:
                last_error = LLMProviderError("LLM_PROVIDER_ERROR", str(exc), retryable=False)
            else:
                metrics.append(
                    self._metric(
                        run_context, agent_name, attempt, started_at, started_clock,
                        response=response, status=CallStatus.SUCCESS,
                    )
                )
                return StructuredLLMResult[T](
                    value=value,
                    raw_text=response.raw_text,
                    usage=response.usage,
                    cost_usd=response.cost_usd,
                    provider_request_id=response.provider_request_id,
                    finish_reason=response.finish_reason,
                    call_metrics=tuple(metrics),
                )

            metrics.append(
                self._metric(
                    run_context, agent_name, attempt, started_at, started_clock,
                    response=response, status=CallStatus.FAILED, error=last_error,
                )
            )
            if not last_error.retryable or attempt == self.retry_policy.max_attempts:
                raise LLMExecutionError(last_error, tuple(metrics)) from last_error

        raise AssertionError("retry loop ended without returning or raising")

    @staticmethod
    def _validate_output(output: dict[str, Any] | str | BaseModel, output_schema: type[T]) -> T:
        if isinstance(output, BaseModel):
            payload: Any = output.model_dump(mode="python")
        elif isinstance(output, str):
            payload = json.loads(output)
        else:
            payload = output
        return output_schema.model_validate(payload)

    @staticmethod
    def _metric(
        context: RunContext,
        stage: str,
        attempt: int,
        started_at: datetime,
        started_clock: float,
        *,
        response: ProviderResponse | None,
        status: CallStatus,
        error: LLMProviderError | None = None,
    ) -> LLMCallMetric:
        finished_at = datetime.now(UTC)
        usage = response.usage if response else None
        return LLMCallMetric(
            call_id=str(uuid4()),
            run_id=context.run_id,
            stage=stage,
            attempt=attempt,
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=max(0.0, (perf_counter() - started_clock) * 1000),
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            cost_usd=response.cost_usd if response else None,
            status=status,
            error_type=error.code if error else None,
            provider_request_id=(response.provider_request_id if response else None)
            or (error.provider_request_id if error else None),
        )
