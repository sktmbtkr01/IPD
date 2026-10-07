from __future__ import annotations

import asyncio
from typing import Any, Protocol

from pydantic import Field

from benchmark.agents.contracts import RunContext
from benchmark.core.schemas import FrozenModel
from benchmark.llm.contracts import LLMProviderError, ProviderResponse, T, TokenUsage


class BedrockConfig(FrozenModel):
    model_id: str = Field(min_length=1)
    region: str = Field(min_length=1)
    temperature: float = Field(default=0.0, ge=0, le=1)
    max_tokens: int = Field(default=2048, ge=1)
    input_cost_per_million: float | None = Field(default=None, ge=0)
    output_cost_per_million: float | None = Field(default=None, ge=0)


class BedrockInvoker(Protocol):
    """Small SDK seam; an application adapter can implement it with boto3."""

    async def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...


class BedrockTransport:
    """Converts the benchmark request into a stable, model-agnostic Bedrock envelope."""

    def __init__(self, config: BedrockConfig, invoker: BedrockInvoker) -> None:
        self.config = config
        self.invoker = invoker

    async def generate(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[T],
        run_context: RunContext,
    ) -> ProviderResponse:
        request = {
            "model_id": self.config.model_id,
            "region": self.config.region,
            "system_prompt": system_prompt,
            "user_payload": user_payload,
            "output_json_schema": output_schema.model_json_schema(),
            "inference": {
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            },
            "metadata": {
                "run_id": run_context.run_id,
                "experiment_id": run_context.experiment_id,
                "agent_name": agent_name,
                "snapshot_hash": run_context.snapshot_hash,
                "prompt_bundle_hash": run_context.prompt_bundle_hash,
            },
        }
        try:
            raw = await self.invoker.invoke(request)
        except (TimeoutError, asyncio.TimeoutError) as exc:
            raise LLMProviderError("LLM_TIMEOUT", str(exc) or "Bedrock request timed out", retryable=True) from exc
        except LLMProviderError:
            raise
        except Exception as exc:
            raise LLMProviderError("LLM_PROVIDER_ERROR", str(exc), retryable=False) from exc

        try:
            usage_raw = raw.get("usage", {})
            input_tokens = int(usage_raw.get("input_tokens", 0))
            output_tokens = int(usage_raw.get("output_tokens", 0))
            usage = TokenUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            )
            cost = self._estimate_cost(input_tokens, output_tokens)
            return ProviderResponse(
                output=raw["output"],
                usage=usage,
                cost_usd=cost,
                provider_request_id=raw.get("request_id"),
                finish_reason=raw.get("finish_reason"),
                raw_text=raw.get("raw_text"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                "LLM_PROVIDER_ERROR",
                f"invalid Bedrock invoker response: {exc}",
                retryable=False,
                provider_request_id=raw.get("request_id") if isinstance(raw, dict) else None,
            ) from exc

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.config.input_cost_per_million is None or self.config.output_cost_per_million is None:
            return None
        return (
            input_tokens * self.config.input_cost_per_million
            + output_tokens * self.config.output_cost_per_million
        ) / 1_000_000
