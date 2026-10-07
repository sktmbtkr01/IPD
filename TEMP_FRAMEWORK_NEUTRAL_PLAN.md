# Temporary Plan — Framework-Neutral Core

This plan is temporary and should be replaced by a release checklist when the shared core is frozen.

## Goal

Publish a framework-neutral package that lets LangGraph, CrewAI, and AutoGen contributors implement only orchestration. Data, prompts, LLM access, agent behavior, validation, metrics, persistence, and parity rules remain shared.

## Gate 1 — Canonical contracts and metrics

Build:
- Agent and workflow enums.
- Structured models for all 12 logical agent outputs.
- Run context, workflow state, call/stage/run metrics, errors, and final run result.
- Framework runner protocol.

Exit gate:
- Round-trip serialization tests pass.
- Invalid actions, profiles, timestamps, durations, and metric values fail validation.
- A complete synthetic `RunResult` validates for every framework identifier.

## Gate 2 — Versioned prompt registry — COMPLETE

Build:
- One prompt file per logical role.
- Prompt loader with individual and bundle SHA-256 hashes.
- Required prompt sections: role, allowed evidence, task, output contract, uncertainty, no external facts, no future information.

Exit gate:
- All 12 prompts load.
- Prompt hashes are deterministic.
- Missing prompts fail closed; modified prompts change the bundle hash.

Implemented in `src/benchmark/agents/prompt_registry.py` and
`src/benchmark/agents/prompts/`. Every prompt carries an explicit version,
allowed-evidence boundary, structured-output contract, uncertainty handling,
and prohibitions on outside or future information.

## Gate 3 — Shared LLM boundary — COMPLETE

Build:
- `LLMClient` protocol.
- Structured result and normalized provider error models.
- Deterministic fake LLM for tests and contributor development.
- Bedrock adapter skeleton/config validation; no framework-native LLM clients.

Exit gate:
- One structured Market Analyst call validates.
- Tokens, latency, attempt number, status, and errors are recorded.
- Retry behavior is deterministic and tested.

Implemented in `src/benchmark/llm/`. Framework code targets the `LLMClient`
protocol and must not instantiate a provider SDK directly. The instrumented
client owns output validation, deterministic retry timing, and per-attempt
metrics. `DeterministicFakeTransport` supports credential-free development;
`BedrockTransport` isolates the future SDK-specific invoker behind a small
protocol and a stable request envelope.

## Gate 4 — Canonical stage functions — COMPLETE

Build:
- Minimum-input selectors for every role.
- Shared prompt + LLM + validation + metric wrapper.
- Pure stage functions for four analysts, Bull/Bear, Research Manager, Trader, three Risk Analysts, and Portfolio Manager.

Exit gate:
- Each stage receives only permitted state.
- All outputs validate with a fake LLM.
- Snapshot objects cannot be mutated.

Implemented in `src/benchmark/agents/stages.py`. Stage-specific output schemas
also freeze analyst identity, research side, and risk profile, preventing a valid
but misrouted response from crossing role boundaries.

## Gate 5 — Canonical workflow and state policy — COMPLETE

Build:
- Framework-neutral reference executor.
- Frozen dependency DAG.
- Explicit state transition and failure rules.
- Configured parallel groups without framework-specific behavior.

Exit gate:
- One frozen snapshot completes all stages.
- Exactly 12 logical calls are recorded with one successful call per role.
- Dependency and state-access tests pass.

Implemented in `src/benchmark/workflows/reference.py`. It is the semantic oracle
for framework adapters and executes only the three declared parallel groups.

## Gate 6 — Instrumentation and persistence — COMPLETE

Build:
- JSON run store with immutable run IDs.
- Call, stage, run, and orchestration-overhead metrics.
- Resume/failure metadata.
- Environment/package/framework version capture.

Exit gate:
- Saved run reloads as the same `RunResult`.
- Failed and successful runs are both persisted.
- Metrics can be aggregated without reading framework-native logs.

Implemented in `src/benchmark/execution/`. Artifacts are canonical JSON with
content hashes, safe paths, immutable collision checks, environment capture, and
resumable checkpoints. A resumed run retains failed attempts without repeating
already completed stages.

## Gate 7 — Adapter protocol and parity suite — COMPLETE

Build:
- One `FrameworkRunner` protocol.
- Generic compliance tests usable by LangGraph, CrewAI, and AutoGen.
- Guardrails preventing framework adapters from fetching market data or bypassing the shared LLM client.

Exit gate:
- Reference executor passes the parity suite.
- A minimal stub adapter demonstrates contributor integration.

Implemented in `src/benchmark/workflows/compliance.py` and
`adapter_template.py`. The compliance layer checks controls, stages, calls,
tokens, and common prohibited adapter imports. Behavioral utilities live in
`src/benchmark/analysis/`.

## Gate 8 — Repository release preparation — COMPLETE

Build:
- Contributor guide and adapter template.
- Dependency lock.
- Git repository and CI test workflow.
- Legally appropriate pilot snapshot distribution or download instructions.
- Frozen hashes for schemas, prompts, configuration, and snapshot manifest.

Exit gate:
- Fresh clone can run tests without provider credentials or network access.
- Contributors can implement an adapter without changing shared contracts.

Implemented through `README.md`, `CONTRIBUTING.md`, `requirements-lock.txt`,
`.env.example`, package-data configuration, offline CI, and the frozen
`configs/foundation_manifest.json`. The reviewed pilot inputs and snapshots are
tracked so contributors can execute identical framework runs without refetching data.

## Framework-wide cross-evaluation metrics

### Experimental-control checks
- Snapshot hash equality.
- Configuration hash equality.
- Prompt-bundle hash equality.
- Model ID and inference-parameter equality.
- Required stage and logical-call-count parity.

### Efficiency
- End-to-end wall-clock latency.
- Per-stage latency.
- Cumulative LLM request latency.
- Deterministic processing latency.
- Approximate orchestration overhead.
- Input, output, and total tokens.
- Direct or estimated LLM cost.
- Logical calls, physical attempts, retries, and repair calls.

### Reliability
- Workflow success rate.
- Stage completion rate.
- Structured-output validation failure rate.
- Retry and repair rate.
- Provider error, framework error, and timeout counts.
- Resume success and unrecovered failure counts.

### Behaviour
- Exact final BUY/HOLD/SELL agreement.
- Pairwise agreement matrix and Fleiss' kappa when applicable.
- Stage-level categorical agreement.
- First-divergence stage.
- Evidence-reference overlap.
- Rationale similarity only under a pre-declared method.
- Repeated-run decision stability.

### Financial evaluation (downstream)
- Cumulative return.
- Annualized return.
- Sharpe ratio.
- Maximum drawdown.
- Turnover, transaction cost, and trade count when the backtest policy is frozen.

Primary reporting must keep efficiency, reliability, behaviour, and financial performance separate; no single composite score should be introduced without a pre-registered weighting rule.
