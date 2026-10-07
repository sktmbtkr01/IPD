# Multi-Agent Trading Framework Benchmark — Codex Context

## Purpose

This repository implements a controlled research benchmark that reproduces the same multi-agent trading workflow in **LangGraph, CrewAI, and AutoGen** and compares how the orchestration framework affects:

1. Final trading decisions.
2. Trading/backtest performance.
3. Latency, token usage, LLM cost, tool/data access overhead, retries, and workflow success.
4. Behavioural consistency across repeated identical inputs.

The trading system is the workload used to evaluate orchestration frameworks. The project is **not primarily a stock-price prediction model**.

## Core experimental invariant

For a valid cross-framework comparison, the following must be held constant:

- Ticker and decision date.
- Frozen point-in-time input snapshot.
- Underlying LLM/model version.
- Model parameters where supported.
- Prompts and prompt versions.
- Agent roles.
- Logical workflow.
- Tool/data outputs.
- Output schemas.
- Backtest rules.
- Retry policy as far as the frameworks permit.

The primary variable is the orchestration framework.

## Current architecture

```text
Historical data sources
        |
        v
Point-in-time data ingestion
        |
        v
Normalization + preprocessing
        |
        v
Frozen MarketSnapshot + content hash
        |
        +----------------------+----------------------+
        |                      |                      |
        v                      v                      v
   LangGraph                CrewAI                 AutoGen
        |                      |                      |
        +----------------------+----------------------+
                               |
                               v
                   Structured final decision
                      BUY / HOLD / SELL
                               |
                               v
                      Backtest simulator
                               |
                               v
                Financial + framework metrics
```

Within each framework, the logical agent workflow is:

```text
Market Analyst --------\
News Analyst -----------+--> shared analyst evidence
Sentiment Analyst ------+
Fundamentals Analyst ---/
                         |
                         v
                Bull Researcher
                Bear Researcher
                         |
                         v
                Research Manager
                         |
                         v
                     Trader
                         |
                         v
          Aggressive Risk Analyst
          Neutral Risk Analyst
          Conservative Risk Analyst
                         |
                         v
                Portfolio Manager
                         |
                         v
                BUY / HOLD / SELL
```

## Input stack

### Core sources

- **Yahoo Finance** — historical OHLCV / price data.
- **Alpha Vantage NEWS_SENTIMENT** — timestamped historical company news and ticker-specific sentiment.
- **FRED / ALFRED semantics** — macroeconomic data as known on the historical decision date.
- **Polymarket** — historical prediction-market probabilities/trades where a relevant market can be mapped to the macro/market context.
- **SEC EDGAR** — recommended point-in-time source for company filings/fundamentals.

### Important input rule

Agents must **not fetch live external data during benchmark execution**.

All external data is collected first, normalized into a `MarketSnapshot`, frozen, persisted, and hashed. Every framework receives exactly the same snapshot.

If a source has no trustworthy historical data for a given date, represent it as unavailable. Never substitute current data into a historical run.

## News vs sentiment

Both can come from Alpha Vantage, but they serve different agents.

- **News Analyst:** reasons over article title, summary, source, publication timestamp, and relevance.
- **Sentiment Analyst:** reasons over ticker-specific sentiment scores/labels, aggregate sentiment, news volume, and optionally earnings-call sentiment.

The same article feed may support both agents, but each receives only the fields relevant to its role.

## Development strategy

Build and validate the project strictly phase by phase.

1. Project skeleton + schemas.
2. Historical data ingestion.
3. Point-in-time preprocessing + frozen snapshots.
4. Single-agent/LLM adapter.
5. One complete framework implementation.
6. Framework-neutral workflow contract.
7. Implement the other two frameworks.
8. Instrumentation.
9. Backtest engine.
10. Pilot benchmark.
11. Full experiment.
12. Analysis/report generation.

Do not start the three framework implementations before the snapshot pipeline is validated.

## Critical unresolved research decisions

These must be explicitly decided before the corresponding phase is implemented:

- Exact stock universe.
- Historical date range.
- Decision frequency (daily vs every N trading days).
- Exact execution timing (e.g. decision after market close and trade next open).
- Meaning of SELL (exit long position vs short position).
- Position sizing.
- Transaction cost/slippage assumptions.
- Holding/rebalancing rules.
- Final LLM/model and inference parameters.
- Number of Bull/Bear debate rounds.
- Whether Polymarket is mandatory or optional per snapshot.
- Exact behavioural-fidelity metric beyond final decision agreement.

Do not silently invent these values in code. Put them in configuration once the research team locks them.

## Files to read

1. `PRD.md` — research/product requirements and success criteria.
2. `ARCHITECTURE.md` — technical architecture and component contracts.
3. `DATA_CONTRACTS.md` — canonical data schemas and point-in-time rules.
4. `IMPLEMENTATION_PLAN.md` — phase-by-phase build order, tests, and exit gates.
