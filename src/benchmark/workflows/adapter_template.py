from __future__ import annotations

from benchmark.agents.contracts import RunContext, RunResult
from benchmark.agents.prompt_registry import PromptRegistry
from benchmark.core.schemas import MarketSnapshot
from benchmark.llm.contracts import LLMClient
from benchmark.workflows.reference import ReferenceWorkflowRunner


class FrameworkAdapterTemplate:
    """Executable example of the only boundary a framework adapter should expose.

    Replace the delegated reference scheduling with framework-native scheduling,
    while retaining the injected LLM client, prompt registry, stage functions,
    state contracts, and returned RunResult unchanged.
    """

    def __init__(self, llm_client: LLMClient, prompt_registry: PromptRegistry | None = None) -> None:
        self._runner = ReferenceWorkflowRunner(llm_client, prompt_registry)

    async def run_workflow(self, snapshot: MarketSnapshot, run_context: RunContext) -> RunResult:
        return await self._runner.run_workflow(snapshot, run_context)
