# IMPLEMENTATION_PLAN — Phase-by-Phase Build and Test Gates

The project must be built sequentially. Do not proceed to the next major phase until the current phase has passed its exit gate.

---

# Phase 0 — Freeze the engineering skeleton

## Goal

Create a clean repository, configuration system, typed schemas, logging, and tests before connecting APIs.

## Build

- Python project setup.
- Environment-variable loading.
- `configs/`.
- Canonical Pydantic/dataclass schemas from `DATA_CONTRACTS.md`.
- Structured logging.
- Hash utility.
- Run ID utility.
- Unit-test harness.

## Tests

- All schemas serialize/deserialize.
- Canonical JSON hashing is deterministic.
- Invalid BUY/HOLD/SELL values fail validation.
- Timezone-naive timestamps fail where prohibited.

## Exit gate

```text
pytest passes
+
a synthetic MarketSnapshot can be created, serialized, hashed, reloaded
```

Do not integrate any agent framework yet.

---

# Phase 1 — Yahoo price pipeline

## Goal

Prove historical market-data ingestion and leakage-safe technical preprocessing.

## Build

- Yahoo connector.
- Raw cache.
- OHLCV normalization.
- Indicator computation.
- Date/cutoff filtering.
- `MarketFeatures` generation.

## First test case

Use one ticker and one known historical date.

Example only:
```text
ticker = AAPL
decision_date = configurable historical date
lookback = 90 trading days
```

Do not hardcode the example in production config.

## Tests

- No returned bar exceeds cutoff.
- Indicators use only filtered bars.
- Same raw input creates same technical values.
- Missing trading days/weekends are handled.
- Re-fetch can load from cache.

## Exit gate

Print/save one deterministic market-only snapshot.

---

# Phase 2 — Historical news + sentiment

## Goal

Add real historical textual evidence without any live-data contamination.

## Build

Alpha Vantage `NEWS_SENTIMENT` connector.

For `(ticker, cutoff)`:
- query configured historical lookback window
- normalize article fields
- filter `published_at <= cutoff`
- deduplicate
- calculate deterministic sentiment aggregate
- persist raw and normalized results

## Agent-facing separation

News payload:
- title
- summary
- source
- timestamp
- relevance

Sentiment payload:
- ticker sentiment values
- aggregate statistics
- selected supporting observations

## Tests

- Inject a fake future article -> validator rejects/removes it.
- Deduplication works.
- Aggregate sentiment recomputes identically.
- Empty article window produces valid `available=false/empty` semantics rather than fabricated data.

## Exit gate

One snapshot contains:
```text
prices + technicals + news + sentiment
```

and passes leakage tests.

---

# Phase 3 — FRED/ALFRED macro pipeline

## Goal

Retrieve macro data as it was known on the historical date.

## Build

- FRED connector.
- Configurable series registry.
- Historical/vintage request handling.
- Normalized macro observations.

Start with a small, defensible set of series. Do not add dozens initially.

## Tests

For a series with known revisions:
- compare today's value vs historical vintage
- demonstrate that historical snapshot uses the historical known value

## Exit gate

Create a test artifact proving point-in-time macro retrieval works.

This phase is not complete just because the FRED API returns a number.

---

# Phase 4 — Fundamentals pipeline

## Goal

Provide the Fundamentals Analyst with point-in-time company information.

## Preferred implementation

SEC EDGAR.

## Build

- filing discovery
- filing/publication cutoff filter
- selected company facts / structured fields
- normalized `FundamentalsSnapshot`

## Tests

- a filing after cutoff is excluded
- latest eligible filing is reproducible
- unavailable facts remain null rather than being inferred

## Exit gate

One historical snapshot can prove which filing supplied each key fundamental value.

---

# Phase 5 — Polymarket historical context

## Goal

Add market-implied expectations without compromising reproducibility.

## Build

- Polymarket Data API client.
- Historical price/trade retrieval.
- Market/event metadata normalization.
- A deterministic relevance/mapping layer.

### Important

The mapping problem must be solved explicitly.

Do not write:
```text
ask LLM to search Polymarket for something relevant
```

during a benchmark.

Instead use:
- a curated market registry for the experimental period, or
- a deterministic keyword/category/date selection rule that can be replayed.

## Tests

- historical observation is at/before cutoff
- market was actually active/meaningful for that date
- no relevant market returns `available=false`
- same snapshot request yields same mapped market set

## Exit gate

Polymarket is optional. Failure to find a relevant market does not invalidate the snapshot unless the research design later says otherwise.

---

# Phase 6 — Snapshot Builder

## Goal

This is the most important data-engineering milestone.

Combine all validated source blocks into one immutable `MarketSnapshot`.

## Build

```python
build_snapshot(ticker, decision_date, config) -> MarketSnapshot
```

Steps:
1. resolve information cutoff
2. load/cache Yahoo data
3. compute technicals
4. load/filter Alpha Vantage news
5. aggregate sentiment
6. load point-in-time macro
7. load point-in-time fundamentals
8. load eligible Polymarket context
9. validate all timestamps
10. serialize canonically
11. hash
12. persist

## Tests

- snapshot rebuild from same cached inputs has identical hash
- future-data injection causes failure
- optional source outage is represented explicitly
- required source outage fails cleanly

## Exit gate

Generate a small snapshot grid, e.g.:
```text
1 ticker × 5 historical dates
```

All snapshots validate and have unique expected hashes.

**Stop here and manually inspect the data before building agents.**

---

# Phase 7 — LLM/Bedrock adapter

## Goal

Make one instrumented structured LLM call.

## Build

- common `LLMClient`
- Bedrock implementation
- structured-output parser
- token accounting
- latency timing
- cost calculation
- error normalization
- retry policy

## First agent

Implement only **Market Analyst**.

Input:
- one frozen snapshot's market block

Output:
- `AnalystReport`

## Tests

- schema-valid result
- tokens captured
- latency captured
- retry captured
- malformed structured response is handled
- prompt version/hash stored

## Exit gate

```text
snapshot -> Market Analyst -> valid report -> persisted trace
```

Do not build 12 agents before this works.

---

# Phase 8 — Four analyst agents

## Goal

Validate independent specialist reasoning.

## Build

- Market Analyst
- News Analyst
- Sentiment Analyst
- Fundamentals Analyst

Each must:
- receive only intended snapshot fields
- use versioned prompts
- return same `AnalystReport` contract

## Execution

They may run concurrently, but first validate them sequentially for debugging.

## Tests

- each agent sees only permitted fields
- no agent uses future prices
- all outputs validate
- call metrics are complete

## Exit gate

One date produces four persisted analyst reports.

---

# Phase 9 — Research + trader + risk + portfolio pipeline

## Goal

Complete the framework-neutral logical workflow.

## Build sequence

1. Bull Researcher.
2. Bear Researcher.
3. Research Manager.
4. Trader.
5. Aggressive Risk.
6. Neutral Risk.
7. Conservative Risk.
8. Portfolio Manager.

## Baseline call count

With one call per logical agent:
- 4 analysts
- 2 researchers
- 1 research manager
- 1 trader
- 3 risk analysts
- 1 portfolio manager

= approximately 12 logical LLM calls per complete decision.

Retries/debate loops increase this number and must be logged.

## Tests

Use one frozen snapshot repeatedly.

Verify:
- stage dependency order
- schemas
- no stage can mutate the snapshot
- final action is valid
- all calls trace to the same snapshot hash

## Exit gate

One complete canonical run returns a valid final decision.

At this point still use only one framework implementation.

---

# Phase 10 — First framework: LangGraph

## Goal

Implement the complete workflow in one framework and prove the graph/state model.

LangGraph is a sensible first implementation because the workflow maps naturally to an explicit DAG, but this is an engineering sequencing choice, not an assumption that it is better.

## Build

Map canonical stages onto LangGraph nodes/state.

Preserve:
- common prompts
- common schemas
- common LLM adapter
- common snapshot
- common metrics

## Tests

- node transitions
- parallel branches where enabled
- failure propagation
- output parity with canonical contracts

## Exit gate

Run:
```text
1 ticker × 3–5 snapshots
```

successfully and persist complete runs.

---

# Phase 11 — Framework parity layer

## Goal

Before adding CrewAI/AutoGen, freeze the contract that all implementations must obey.

Create tests that accept a framework runner and assert:

```text
same MarketSnapshot input type
same required stages
same output models
same prompt registry
same model adapter
same final decision enum
same trace fields
```

## Exit gate

LangGraph passes the generic parity test suite.

---

# Phase 12 — CrewAI implementation

Implement only orchestration-specific code.

Do not duplicate:
- data pipeline
- prompts
- schemas
- LLM pricing logic
- backtest code

## Exit gate

CrewAI passes the exact generic parity suite used for LangGraph.

---

# Phase 13 — AutoGen implementation

Same requirements as Phase 12.

## Exit gate

All three runners pass the same parity suite.

---

# Phase 14 — Controlled same-snapshot comparison

## Goal

Prove experimental control before backtesting.

Take one snapshot hash and run:

```text
LangGraph
CrewAI
AutoGen
```

Verify all three records contain:
- identical snapshot hash
- identical model id
- identical prompt bundle hash
- identical experiment config hash where framework-specific fields are excluded appropriately

Compare:
- final decision
- stage outputs
- call count
- token use
- latency
- failures

## Exit gate

Produce a comparison report for 1–5 dates.

If the inputs are not demonstrably identical, do not continue.

---

# Phase 15 — Backtest policy design

## Goal

Lock the financial simulation before running a large experiment.

The research team must decide:

- decision timing
- execution timing
- BUY semantics
- HOLD semantics
- SELL semantics
- long-only vs shorting
- position size
- capital allocation
- costs
- slippage
- benchmark
- rebalance schedule

This phase requires a written config/spec update.

## Important

Do not derive a "ground-truth BUY/HOLD/SELL label" unless the research explicitly decides to study classification accuracy.

The primary evaluation remains portfolio performance from the generated sequence of actions.

## Exit gate

A deterministic simulator can process a hand-written sequence of decisions and yield verifiable portfolio values.

---

# Phase 16 — Backtest engine

## Build

Inputs:
- saved decisions
- historical realized prices
- frozen backtest config

Outputs:
- position log
- transaction log
- daily/decision-date portfolio values
- equity curve
- financial metrics

## Tests

Create tiny synthetic price paths where expected results are calculable by hand.

Verify:
- cumulative return
- annualized return
- Sharpe implementation
- maximum drawdown
- transaction-cost application

## Exit gate

Reports are reproducible without any LLM/API calls.

---

# Phase 17 — Pilot experiment

## Suggested scale

Do not start with 252 dates.

Example pilot:
```text
1–3 tickers
10–30 decision dates
3 frameworks
1 frozen LLM model
```

The exact size is chosen based on API/data coverage and runtime.

## Measure

- snapshot source availability
- average calls/run
- token usage
- dollar cost
- latency
- failure rate
- final-decision distribution
- cross-framework agreement
- preliminary backtest metrics

## Exit gate

Answer:
1. Is the data pipeline reliable?
2. Is Bedrock cost acceptable?
3. Do all frameworks finish reliably?
4. Are prompts producing valid structured output?
5. Is experiment duration manageable?
6. Is decision frequency sufficient?

Only then choose full benchmark scale.

---

# Phase 18 — Full experiment

## Requirements

Freeze:
- git commit
- data schema version
- snapshot set
- prompt bundle
- model id
- inference params
- framework package versions
- experiment config
- backtest config

Generate all snapshots first.

Then run framework experiments against the frozen snapshot list.

Make runs resumable.

Do not rebuild source data mid-benchmark unless the entire affected experimental set is versioned as a new dataset release.

---

# Phase 19 — Research analysis

## Framework efficiency

Per framework:
- mean/median/p95 latency
- tokens per decision
- LLM cost per decision
- calls per decision
- retry/failure statistics
- workflow success rate

## Behavioural fidelity

Start with:
- exact final decision agreement
- pairwise agreement matrix
- stage-wise recommendation agreement where applicable

Then optionally add:
- embedding/categorical similarity of structured reasons
- first-divergence stage
- stability across repeated runs

Do not introduce a behavioural metric without defining it before interpreting results.

## Financial performance

Per framework:
- cumulative return
- annualized return
- Sharpe ratio
- maximum drawdown

Compare using the exact same snapshot/decision calendar and backtest rules.

---

# Phase 20 — Final reproducibility package

The final research artifact should contain:

- source code
- environment/package lock
- experiment configs
- prompt versions
- snapshot manifest + hashes
- run manifest
- decision outputs
- call metrics
- backtest results
- analysis notebooks/scripts
- documented failure cases

---

# Codex operating instructions

When implementing any phase:

1. Read the relevant documentation files.
2. Implement only the requested phase.
3. Do not pre-implement future phases unless required by an interface.
4. Do not invent unresolved research constants.
5. Add tests in the same phase.
6. Report assumptions explicitly.
7. Do not change canonical schemas silently.
8. Do not call an external API in unit tests.
9. Use fixtures/mocks for unit tests and separate integration tests for live providers.
10. Never allow benchmark framework code to fetch live market information.
