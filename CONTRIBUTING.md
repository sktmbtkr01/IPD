# Contributor Guide: Framework Adapters

## Objective

Implement orchestration for one framework without changing the experiment. The
adapter may schedule canonical stages and translate framework events, but it may
not redefine agent behavior, inputs, outputs, retries, model access, or metrics.

## Required adapter interface

Implement the `FrameworkRunner` protocol:

```python
async def run_workflow(snapshot: MarketSnapshot, run_context: RunContext) -> RunResult:
    ...
```

Start from `benchmark.workflows.adapter_template.FrameworkAdapterTemplate`.

## Mandatory shared components

Use these directly:

- `PromptRegistry` for all system prompts and the bundle hash.
- `select_stage_input` for minimum permitted role inputs.
- `execute_stage` for prompt loading, the shared LLM call, validation, and metrics.
- `apply_stage_output` for canonical state transitions.
- `InstrumentedLLMClient` for retries, token/cost accounting, and provider errors.
- `RunResult`, `RunMetrics`, and `RunStore` for output and persistence.

Do not copy these functions into an adapter. Import them so fixes apply equally to
all frameworks.

## Frozen execution policy

The six layers are:

1. Four analysts in parallel.
2. Bull and Bear researchers in parallel.
3. Research Manager.
4. Trader.
5. Three Risk Analysts in parallel.
6. Portfolio Manager.

Each logical role runs exactly once in a successful non-resumed run. Framework
message history must not be passed as extra agent context. Framework-level automatic
retries, tool use, memory, delegation, browsing, and model fallback must be disabled.
Retries belong to the shared LLM client.

## Prohibited adapter behavior

- Importing `benchmark.data` or HTTP/provider SDKs.
- Fetching live or historical data.
- Calling a framework-native LLM client directly.
- Editing prompts or appending framework-specific semantic instructions.
- Passing fields beyond `select_stage_input`.
- Recalculating indicators, sentiment, fundamentals, tokens, pricing, or cost.
- Suppressing failed calls/runs or changing BUY/HOLD/SELL outputs.

`scan_adapter_source` rejects common provider/data imports. Review still must verify
semantic compliance because static checks cannot prove absence of every side effect.

## Required tests for each adapter

Run the generic assertions with the deterministic fake transport:

1. All 12 outputs validate.
2. `assert_run_compliance(result, context)` passes.
3. Exactly 12 logical stages and successful calls are present.
4. Snapshot, config, prompt, model, and seed controls match the requested context.
5. A provider failure is retained, persisted, and resumable without rerunning completed stages.
6. `scan_adapter_source(Path(adapter_module.__file__))` returns no violations.
7. `compare_run_parity(adapter_result, reference_result)` reports equal controls and stage sets.

Behavioral output hashes are allowed to differ when the framework truly changes
execution behavior; that difference is measured, not silently normalized away.

## Pull-request checklist

- Framework package/version is recorded.
- No foundation manifest change unless the research contract intentionally changed.
- No secrets, unreviewed provider data, or generated run artifacts are committed.
- Additions to the tracked pilot data have been checked for redistribution terms and credential-bearing URLs.
- Offline tests pass without credentials.
- Framework-specific limitations are documented.
