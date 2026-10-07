# PRD — Comparative Multi-Agent Orchestration for AI Trading Systems

## 1. Problem statement

Multi-agent financial systems are usually implemented using one orchestration framework. This makes it difficult to know whether framework-level behaviour — state handling, message routing, scheduling, retries, tool execution, and conversation semantics — changes the quality, cost, speed, reliability, or final decisions of the same logical trading workflow.

This project builds one multi-agent trading decision system three times:

- LangGraph
- CrewAI
- AutoGen

The experiment keeps the trading logic and model-side variables as constant as possible and measures framework-induced differences.

## 2. Research objective

Determine how the orchestration framework affects a realistic, stateful, multi-stage financial-agent workflow when all frameworks process the same point-in-time market evidence.

### Primary research questions

RQ1. Do the three frameworks produce the same BUY/HOLD/SELL decision for the same frozen market snapshot?

RQ2. How do they differ in end-to-end latency, token consumption, LLM cost, number of calls/retries, and workflow completion rate?

RQ3. Do framework differences materially change backtest performance?

RQ4. Where do behavioural divergences first appear in the workflow — analyst reports, Bull/Bear research, trader plan, risk analysis, or final portfolio decision?

## 3. Intended outcome

For each `(ticker, decision_date, framework, run_id)` the system must produce:

- Valid structured analyst outputs.
- Bull and Bear research arguments.
- Research-manager synthesis.
- Trader proposal.
- Three risk perspectives.
- Final portfolio-manager decision.
- Complete execution trace.
- Token/cost/latency/call metrics.
- Snapshot hash and prompt/config versions.

The final decision is:

```text
BUY | HOLD | SELL
```

The decision is then evaluated through a historical portfolio simulation, not simply compared to a supervised-learning label.

## 4. Users

### Primary

Research team implementing and evaluating the system.

### Secondary

Faculty/research reviewers who need reproducible evidence that framework comparisons were controlled.

## 5. In scope

### Data engineering

- Historical OHLCV retrieval.
- Technical-indicator computation.
- Historical company news.
- News/ticker sentiment.
- Point-in-time macroeconomic data.
- Historical prediction-market data when relevant.
- Point-in-time company fundamentals/filings.
- Caching and immutable snapshot generation.
- Data-quality and leakage validation.

### Multi-agent workflow

- Four specialist analysts.
- Bull/Bear research stage.
- Research manager.
- Trader.
- Three risk analysts.
- Portfolio manager.
- Shared structured state.

### Framework implementations

- LangGraph adapter.
- CrewAI adapter.
- AutoGen adapter.

### LLM

- One common LLM/provider configuration for final benchmark runs.
- Amazon Bedrock-compatible adapter is the preferred deployment path.
- Development may use a cheaper model, but final framework comparison must use one frozen model configuration.

### Evaluation

Financial metrics:
- Cumulative Return.
- Annualized Return.
- Sharpe Ratio.
- Maximum Drawdown.

Framework metrics:
- End-to-end latency.
- Input/output tokens.
- Estimated/direct LLM cost.
- Number of LLM calls.
- Number of failed calls/retries.
- Workflow success rate.
- Decision agreement.

Trace-level analysis:
- Stage-wise output agreement/divergence.
- First stage at which two framework executions materially diverge.

## 6. Out of scope for the first complete version

- High-frequency/intraday trading.
- Real-money execution.
- Broker integration.
- Portfolio optimization across dozens/hundreds of assets.
- Reinforcement learning.
- Fine-tuning an LLM.
- Training a stock prediction model.
- Scraping unreliable historical social-media archives.
- Allowing agents to browse arbitrary live web sources during benchmark runs.

These can be explored only after the controlled benchmark works.

## 7. Data-source requirements

### 7.1 Yahoo Finance

Purpose:
- Historical OHLCV.
- Price history used to compute technical indicators.
- Future realized prices used by the backtest evaluator.

Requirements:
- Historical range must include the lookback window needed by indicators.
- For decision date `t`, analyst features may use only observations available on or before the configured information cutoff.

### 7.2 Alpha Vantage

Purpose:
- Historical news.
- Ticker-specific article sentiment.

Use the historical time window parameters of the `NEWS_SENTIMENT` endpoint.

Store:
- title
- summary
- source
- URL/id when available
- publication timestamp
- relevance score
- ticker sentiment score
- ticker sentiment label

Never include articles published after the snapshot cutoff.

### 7.3 FRED / ALFRED

Purpose:
- Macro context such as inflation, unemployment, policy rates, Treasury/yield-related series, etc.

Requirement:
Historical runs must use real-time/vintage semantics. Do not query today's revised historical value and pretend it was known at date `t`.

For an as-of date, query values using `realtime_start`, `realtime_end`, or appropriate vintage-date handling.

### 7.4 Polymarket

Purpose:
- Market-implied probabilities for relevant macro/economic/political events that can reasonably affect the investment context.

Requirements:
- Use historical price/trade information.
- Preserve market/event identifiers.
- Do not choose markets using future knowledge.
- A deterministic market-selection/mapping policy must be defined.
- If no relevant historical market exists, store `available=false`.
- Polymarket must not block snapshot creation unless later explicitly made mandatory.

### 7.5 Fundamentals

Preferred historical source:
- SEC EDGAR filings for U.S. equities.

Requirement:
Use only filings that were publicly available by the decision cutoff.

Alpha Vantage fundamentals may be used as an augmentation only if historical availability semantics are verified for the chosen fields.

## 8. Point-in-time integrity

This is a hard requirement.

For a snapshot with cutoff timestamp `T`, no model-facing field may contain information first published after `T`.

Every snapshot must include:

- ticker
- decision date
- information cutoff timestamp
- source retrieval metadata
- source availability flags
- normalized data
- schema version
- content hash

### Failure policy

If a source fails:

- Retry according to the ingestion retry policy.
- If the source is optional, record failure and continue with `available=false`.
- If the source is required, fail snapshot creation.
- Never silently replace missing historical data with current data.

## 9. Agent requirements

### Market Analyst

Input:
- OHLCV-derived summary/features.
- Technical indicators.
- Recent returns/volatility/volume context.

Output:
- market trend
- technical evidence
- bullish signals
- bearish signals
- uncertainty
- concise structured report

### News Analyst

Input:
- Timestamp-filtered historical articles.

Output:
- important events
- likely market impact
- supporting article references/ids
- uncertainty
- concise structured report

### Sentiment Analyst

Input:
- Ticker-level historical sentiment values.
- Aggregate sentiment statistics.
- News-volume/context features.
- Optional historical earnings-call sentiment.

Output:
- sentiment direction
- sentiment strength
- supporting evidence
- contradictions
- uncertainty

### Fundamentals Analyst

Input:
- Point-in-time company financial/filing data.

Output:
- financial health
- valuation/fundamental evidence
- positives
- risks
- uncertainty

### Bull Researcher

Input:
- All four analyst reports.

Task:
Construct the strongest evidence-grounded bullish thesis. Must not invent new external facts.

### Bear Researcher

Input:
- All four analyst reports.

Task:
Construct the strongest evidence-grounded bearish thesis. Must not invent new external facts.

### Research Manager

Input:
- Analyst reports.
- Bull thesis.
- Bear thesis.

Output:
- synthesis
- recommendation
- key reasons
- unresolved risks

### Trader

Input:
- Research-manager output.
- Relevant portfolio state if enabled.

Output:
- proposed BUY/HOLD/SELL action
- rationale
- optional sizing field only if sizing has been formally defined

### Risk Analysts

Three roles:
- Aggressive
- Neutral
- Conservative

Input:
- Trader proposal.
- Research evidence.
- Configured portfolio/risk state.

Output:
- approve/modify/reject stance
- risk rationale
- main downside scenarios

### Portfolio Manager

Input:
- Trader proposal.
- Three risk reports.
- Core research evidence.

Output:
- final BUY/HOLD/SELL
- concise rationale
- confidence field only if confidence calibration/meaning is formally defined

## 10. Structured-output requirement

All agent outputs must validate against framework-neutral schemas.

No benchmark result may rely on scraping arbitrary prose to determine the final action.

If structured generation fails:
1. record failure
2. apply configured retry/repair policy
3. record every additional LLM call
4. fail the workflow if the maximum attempts are exhausted

## 11. Framework equivalence requirement

Each implementation must map onto the same logical DAG and schemas.

Allowed differences:
- Native framework syntax.
- Native state/checkpoint implementation.
- Native scheduling implementation.
- Framework-required message wrappers.

Not allowed:
- Different prompts.
- Different source data.
- Different agents.
- Different analyst responsibilities.
- Extra reasoning agents in only one framework.
- Different LLM model.
- Different output schema.
- Different debate rounds.

Any unavoidable framework-specific divergence must be explicitly logged.

## 12. Instrumentation

Record per workflow:
- start/end timestamps
- total duration
- framework
- model
- snapshot hash
- config hash
- prompt version
- workflow success/failure

Record per LLM call:
- agent/stage
- call index
- start/end timestamps
- input tokens
- output tokens
- model
- cost
- retry number
- status/error

Record per stage:
- input state hash where practical
- structured output
- validation result

## 13. Backtesting requirements

The backtest engine must consume saved final decisions. It must not rerun the LLM when calculating reports.

Backtest configuration must explicitly define:
- execution timing
- position semantics
- SELL semantics
- position sizing
- transaction costs
- slippage
- rebalancing frequency
- benchmark if used

These are currently research decisions and must not be hardcoded by Codex until specified.

### Backtesting output

Per framework:
- equity curve
- cumulative return
- annualized return
- Sharpe ratio
- maximum drawdown
- trade/decision log

Optional later:
- hit rate
- alpha vs benchmark
- turnover
- decision-conditioned forward returns

## 14. Experiment modes

### Smoke

1 ticker × 1–3 dates.

Goal:
Verify end-to-end correctness.

### Pilot

1–3 tickers × approximately 10–30 decision dates.

Goal:
Measure cost, runtime, data availability, schema reliability, and framework parity.

### Full benchmark

Defined only after pilot results.

Do not assume 252 LLM decision dates are necessary. Decision-date sampling (for example every N trading days) is a legitimate experimental configuration as long as it is identical across frameworks and documented.

## 15. Acceptance criteria

The project is ready for full benchmarking only when:

- Historical snapshots are reproducible from persisted data.
- No known look-ahead leakage remains in core data sources.
- Identical snapshot hashes reach all frameworks.
- All frameworks implement the same logical stages.
- Every stage validates against the same schema.
- Token/cost/latency metrics are captured.
- A failed run can be diagnosed from logs.
- Backtest metrics can be regenerated from saved decisions without rerunning LLMs.
- Smoke and pilot experiments complete successfully.

## 16. Research-quality safeguards

- Persist raw source payloads or minimally sufficient source artifacts where permitted.
- Persist normalized snapshots separately.
- Version schemas.
- Version prompts.
- Hash configuration.
- Freeze model identifier for final experiment.
- Never overwrite previous benchmark runs.
- Use run IDs.
- Make experiments resumable.
- Ensure failures remain part of the framework reliability statistics rather than silently disappearing.
