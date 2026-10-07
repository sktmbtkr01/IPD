# DATA_CONTRACTS — Canonical Schemas and Point-in-Time Rules

This file defines framework-neutral contracts. Codex should implement these as typed models (for example Pydantic models) before building framework graphs.

Field names below are illustrative but should remain stable once implemented.

## 1. Shared conventions

- Timestamps: timezone-aware ISO-8601.
- Decision timezone: configurable, default research target is U.S. equities.
- Numeric missing values: `null`, never magic numbers.
- Every source block has `available`.
- Every externally sourced record preserves source and timestamp metadata.
- Every snapshot has `schema_version`.
- Every snapshot is canonicalized before hashing.

---

## 2. Source metadata

```python
class SourceMeta:
    provider: str
    retrieved_at: datetime
    request_key: str
    source_timestamp: datetime | None
    available: bool
    error: str | None
```

---

## 3. Price bar

```python
class PriceBar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float | None
    volume: float
```

Rule:
`timestamp <= information_cutoff` for every model-facing price bar.

---

## 4. Technical features

```python
class TechnicalFeatures:
    as_of: datetime
    sma_20: float | None
    sma_50: float | None
    ema_20: float | None
    rsi_14: float | None
    macd: float | None
    macd_signal: float | None
    bollinger_upper: float | None
    bollinger_lower: float | None
    atr_14: float | None
    realized_volatility: float | None
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
```

The exact final feature set is versioned. Do not silently change it mid-experiment.

---

## 5. News item

```python
class NewsItem:
    id: str
    title: str
    summary: str | None
    source: str
    url: str | None
    published_at: datetime
    ticker_relevance: float | None
    ticker_sentiment_score: float | None
    ticker_sentiment_label: str | None
```

Hard rule:
`published_at <= information_cutoff`.

Deduplication key should prefer provider id/url; otherwise use normalized title + timestamp/source.

---

## 6. Sentiment summary

```python
class SentimentSummary:
    available: bool
    article_count: int
    weighted_mean: float | None
    median: float | None
    bullish_fraction: float | None
    neutral_fraction: float | None
    bearish_fraction: float | None
    strongest_positive_news_id: str | None
    strongest_negative_news_id: str | None
```

All aggregates are deterministic functions of the same filtered `NewsItem[]`.

---

## 7. Macro observation

```python
class MacroObservation:
    series_id: str
    label: str
    observation_date: date
    value: float | None
    realtime_start: date | None
    realtime_end: date | None
    units: str | None
```

Hard rule:
The value must reflect information available at the historical cutoff, not the latest revised value queried today.

---

## 8. Prediction-market observation

```python
class PredictionMarketObservation:
    available: bool
    event_id: str | None
    market_id: str | None
    condition_id: str | None
    token_id: str | None
    question: str | None
    outcome: str | None
    probability: float | None
    observed_at: datetime | None
    relevance_rule: str | None
```

Rules:
- `observed_at <= information_cutoff`.
- Mapping to a market/event must follow a pre-defined deterministic policy.
- No relevant market -> `available=false`.
- Do not manufacture a probability.

---

## 9. Fundamentals

```python
class FundamentalFact:
    name: str
    value: float | str | None
    period_end: date | None
    filing_date: date | None
    accession_id: str | None
    source: str

class FundamentalsSnapshot:
    available: bool
    facts: list[FundamentalFact]
    latest_filing_date: date | None
```

Hard rule:
`filing_date <= decision cutoff date` for all SEC-derived facts.

---

## 10. Market snapshot

```python
class MarketSnapshot:
    schema_version: str
    ticker: str
    decision_date: date
    information_cutoff: datetime

    price_bars: list[PriceBar]
    technicals: TechnicalFeatures

    news: list[NewsItem]
    sentiment: SentimentSummary

    macro: list[MacroObservation]
    prediction_markets: list[PredictionMarketObservation]
    fundamentals: FundamentalsSnapshot

    source_meta: dict[str, SourceMeta]

    snapshot_hash: str
```

Hash rule:
Exclude only fields that are inherently non-deterministic and irrelevant to content identity, such as `retrieved_at`, if the team chooses. Document the exact canonicalization rule.

---

## 11. Analyst report

```python
class AnalystReport:
    agent: str
    thesis: str
    key_evidence: list[str]
    bullish_factors: list[str]
    bearish_factors: list[str]
    uncertainty: list[str]
```

`key_evidence` should reference canonical ids/field names where practical rather than vague uncited claims.

---

## 12. Research debate outputs

```python
class ResearchArgument:
    side: Literal["BULL", "BEAR"]
    thesis: str
    evidence: list[str]
    counterarguments: list[str]
    risks: list[str]

class ResearchManagerReport:
    synthesis: str
    recommendation: Literal["BUY", "HOLD", "SELL"]
    reasons: list[str]
    unresolved_risks: list[str]
```

The Research Manager recommendation is intermediate, not the final system output.

---

## 13. Trader plan

```python
class TraderPlan:
    proposed_action: Literal["BUY", "HOLD", "SELL"]
    rationale: str
    sizing: float | None
    constraints: list[str]
```

`sizing` remains null until a formal position-sizing policy exists.

---

## 14. Risk report

```python
class RiskReport:
    profile: Literal["AGGRESSIVE", "NEUTRAL", "CONSERVATIVE"]
    stance: Literal["APPROVE", "MODIFY", "REJECT"]
    recommended_action: Literal["BUY", "HOLD", "SELL"]
    key_risks: list[str]
    rationale: str
```

---

## 15. Final decision

```python
class FinalDecision:
    action: Literal["BUY", "HOLD", "SELL"]
    rationale: str
    confidence: float | None
```

Do not use `confidence` in evaluation until its interpretation/calibration is explicitly defined.

---

## 16. Run context

```python
class RunContext:
    run_id: str
    experiment_id: str
    framework: Literal["LANGGRAPH", "CREWAI", "AUTOGEN"]
    model_id: str
    snapshot_hash: str
    config_hash: str
    prompt_bundle_hash: str
    seed: int | None
```

---

## 17. LLM call metric

```python
class LLMCallMetric:
    call_id: str
    run_id: str
    stage: str
    attempt: int
    started_at: datetime
    finished_at: datetime
    latency_ms: float
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    status: str
    error_type: str | None
```

---

## 18. Run result

```python
class RunResult:
    context: RunContext

    market_report: AnalystReport
    news_report: AnalystReport
    sentiment_report: AnalystReport
    fundamentals_report: AnalystReport

    bull_argument: ResearchArgument
    bear_argument: ResearchArgument
    research_manager: ResearchManagerReport
    trader: TraderPlan

    aggressive_risk: RiskReport
    neutral_risk: RiskReport
    conservative_risk: RiskReport

    final_decision: FinalDecision

    call_metrics: list[LLMCallMetric]
    status: str
    error: str | None
```

---

## 19. Leakage tests

Create automated tests that intentionally fail when:

- a price bar timestamp exceeds cutoff
- a news timestamp exceeds cutoff
- a fundamental filing date exceeds cutoff
- a Polymarket observation exceeds cutoff
- a macro query is missing point-in-time/vintage semantics where required
- future realized price data appears anywhere in `MarketSnapshot`

These tests are release blockers.
