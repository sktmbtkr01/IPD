from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from benchmark.agents.contracts import RunContext
from benchmark.llm.contracts import ProviderResponse, T


class DeterministicFakeTransport:
    """Scripted offline transport for workflow tests and contributor examples."""

    def __init__(self, responses: dict[str, ProviderResponse | Exception | Iterable[Any]]) -> None:
        self._responses: dict[str, deque[ProviderResponse | Exception]] = {}
        for stage, configured in responses.items():
            if isinstance(configured, (ProviderResponse, Exception)):
                values = [configured]
            else:
                values = list(configured)
            if not values:
                raise ValueError(f"fake response queue is empty for {stage}")
            self._responses[stage] = deque(values)
        self.calls: dict[str, int] = defaultdict(int)
        self.requests: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        agent_name: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        output_schema: type[T],
        run_context: RunContext,
    ) -> ProviderResponse:
        if agent_name not in self._responses:
            raise KeyError(f"no fake response configured for {agent_name}")
        queue = self._responses[agent_name]
        self.calls[agent_name] += 1
        self.requests.append(
            {
                "agent_name": agent_name,
                "system_prompt": system_prompt,
                "user_payload": deepcopy(user_payload),
                "output_schema": output_schema.__name__,
                "run_id": run_context.run_id,
            }
        )
        value = queue[0] if len(queue) == 1 else queue.popleft()
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, ProviderResponse):
            raise TypeError(f"fake response for {agent_name} must be ProviderResponse or Exception")
        return value
