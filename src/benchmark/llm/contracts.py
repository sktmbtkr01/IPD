from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel, Field, model_validator

from benchmark.agents.contracts import LLMCallMetric, RunContext
from benchmark.core.schemas import FrozenModel


T = TypeVar("T", bound=BaseModel)


class TokenUsage(FrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_total(self):
        if self.total_tokens != self.input_tokens + self.output_tokens:
            raise ValueError("total_tokens mismatch")
        return self


class ProviderResponse(FrozenModel):
    output: dict[str, Any] | str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    cost_usd: float | None = Field(default=None, ge=0)
    provider_request_id: str | None = None
    finish_reason: str | None = None
    raw_text: str | None = None


class StructuredLLMResult(FrozenModel, Generic[T]):
    value: T
    raw_text: str | None = None
    usage: TokenUsage
    cost_usd: float | None = Field(default=None, ge=0)
    provider_request_id: str | None = None
    finish_reason: str | None = None
    call_metrics: tuple[LLMCallMetric, ...]


class RetryPolicy(FrozenModel):
    max_attempts: int = Field(default=3, ge=1)
    initial_backoff_seconds: float = Field(default=0.5, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1)
    max_backoff_seconds: float = Field(default=8.0, ge=0)

    def delay_before(self, attempt: int) -> float:
        """Delay before a retry whose next attempt number is ``attempt``."""
        if attempt <= 1:
            return 0.0
        delay = self.initial_backoff_seconds * self.backoff_multiplier ** (attempt - 2)
        return min(delay, self.max_backoff_seconds)


class LLMProviderError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool,
        provider_request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.provider_request_id = provider_request_id


class LLMExecutionError(Exception):
    def __init__(self, cause: LLMProviderError, call_metrics: tuple[LLMCallMetric, ...]) -> None:
        super().__init__(str(cause))
        self.cause = cause
        self.call_metrics = call_metrics


class RawLLMTransport(Protocol):
    async def generate(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[T],
        run_context: RunContext,
    ) -> ProviderResponse: ...


class LLMClient(Protocol):
    async def generate_structured(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[T],
        run_context: RunContext,
    ) -> StructuredLLMResult[T]: ...


AsyncSleep = Callable[[float], Awaitable[None]]
