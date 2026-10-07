# Multi-Agent Trading Framework Benchmark

This repository is the framework-neutral foundation for a controlled comparison
of LangGraph, CrewAI, and AutoGen using the same point-in-time trading workflow.
The framework is the experimental variable; snapshots, prompts, schemas, model
boundary, retry rules, workflow dependencies, and measurement are shared.

## What is complete

- Point-in-time AAPL ingestion, preprocessing, audit, immutable snapshots, and hashes.
- Twelve versioned, hashed role prompts with common safety policies.
- Shared structured-output LLM boundary, deterministic fake transport, and Bedrock seam.
- Canonical minimum-input stage functions and six-layer reference executor.
- Immutable success, failure, and resumable-checkpoint artifacts.
- Cross-framework compliance, parity, efficiency, reliability, and behavior utilities.
- Frozen foundation manifest, locked test dependencies, and offline CI.

Framework-specific LangGraph, CrewAI, and AutoGen scheduling belongs in thin
adapters and is intentionally not part of this shared core.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
benchmark-foundation verify --project-root .
pytest -q
```

Tests and the deterministic fake LLM require no API credentials or network access.

## Canonical workflow

```text
Market / News / Sentiment / Fundamentals Analysts  (parallel)
                         |
              Bull / Bear Researchers             (parallel)
                         |
                 Research Manager
                         |
                       Trader
                         |
       Aggressive / Neutral / Conservative Risk    (parallel)
                         |
                 Portfolio Manager
                         |
                  BUY / HOLD / SELL
```

The dependency graph is frozen in `src/benchmark/workflows/contracts.py`.
Every role receives only the fields selected in `src/benchmark/agents/stages.py`.

## Repository boundaries

- `benchmark.data`: external acquisition and point-in-time normalization only.
- `benchmark.agents`: shared schemas, prompts, and canonical stage behavior.
- `benchmark.llm`: the only permitted model/provider boundary.
- `benchmark.workflows`: canonical execution and thin framework adapters.
- `benchmark.execution`: immutable artifacts, checkpoints, and metrics.
- `benchmark.analysis`: framework agreement and behavioral comparisons.

Framework adapters must never import provider/data connectors or instantiate an
independent LLM SDK. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Pilot snapshot policy

The current small pilot dataset is committed so contributors can reproduce framework
runs without spending API quota. It includes the reviewed raw cache, normalized data,
three frozen AAPL snapshots, and their manifests. `configs/snapshot_manifest.json`
contains the approved identities and expected counts. Before adding data from a new
provider, review its redistribution terms and scan it for secrets. Never commit `.env`
or credential-bearing request URLs.

## Frozen identity

`configs/foundation_manifest.json` freezes prompt hashes, schema hashes, workflow
topology, experiment/data configuration, and the snapshot manifest. Any intentional
foundation change requires review and manifest regeneration. CI fails when it is stale.

The broader research rationale remains in `README_PROJECT.md`, `PRD.md`,
`ARCHITECTURE.md`, and `DATA_CONTRACTS.md`.
