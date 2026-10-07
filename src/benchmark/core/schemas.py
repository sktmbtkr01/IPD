from __future__ import annotations
from datetime import date, datetime
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

def aware(v: datetime | None):
    if v is not None and (v.tzinfo is None or v.utcoffset() is None): raise ValueError("timestamp must be timezone-aware")
    return v


class FrozenDict(dict):
    """JSON-compatible mapping that rejects mutation after validation."""

    @staticmethod
    def _immutable(*args: Any, **kwargs: Any) -> None:
        raise TypeError("mapping is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable


def frozen_dict(value: dict) -> FrozenDict:
    return value if isinstance(value, FrozenDict) else FrozenDict(value)

class FrozenModel(BaseModel): model_config = ConfigDict(frozen=True, extra="forbid")

class SourceMeta(FrozenModel):
    provider: str; retrieved_at: datetime; request_key: str; source_timestamp: datetime | None = None
    available: bool; error: str | None = None
    _a = field_validator("retrieved_at", "source_timestamp")(aware)

class PriceBar(FrozenModel):
    timestamp: datetime; open: float; high: float; low: float; close: float
    adjusted_close: float | None = None; volume: float = Field(ge=0)
    _a = field_validator("timestamp")(aware)
    @model_validator(mode="after")
    def ohlc(self):
        if self.high < max(self.open, self.close, self.low): raise ValueError("invalid high")
        if self.low > min(self.open, self.close, self.high): raise ValueError("invalid low")
        return self

class TechnicalFeatures(FrozenModel):
    version: str = "1.0.0"; as_of: datetime; sma_20: float | None = None; sma_50: float | None = None; ema_20: float | None = None
    rsi_14: float | None = None; macd: float | None = None; macd_signal: float | None = None
    bollinger_upper: float | None = None; bollinger_lower: float | None = None; atr_14: float | None = None
    realized_volatility: float | None = None; return_1d: float | None = None
    return_5d: float | None = None; return_20d: float | None = None
    _a = field_validator("as_of")(aware)

class NewsItem(FrozenModel):
    id: str; title: str; summary: str | None = None; source: str; url: str | None = None
    published_at: datetime; ticker_relevance: float | None = None
    ticker_sentiment_score: float | None = None; ticker_sentiment_label: str | None = None
    _a = field_validator("published_at")(aware)

class SentimentSummary(FrozenModel):
    available: bool; article_count: int = Field(ge=0); weighted_mean: float | None = None
    median: float | None = None; bullish_fraction: float | None = None; neutral_fraction: float | None = None
    bearish_fraction: float | None = None; strongest_positive_news_id: str | None = None
    strongest_negative_news_id: str | None = None

class MacroObservation(FrozenModel):
    series_id: str; label: str; observation_date: date; value: float | None
    realtime_start: date | None = None; realtime_end: date | None = None; units: str | None = None

class PredictionMarketObservation(FrozenModel):
    available: bool; event_id: str | None = None; market_id: str | None = None
    condition_id: str | None = None; token_id: str | None = None; question: str | None = None
    outcome: str | None = None; probability: float | None = Field(default=None, ge=0, le=1)
    observed_at: datetime | None = None; relevance_rule: str | None = None
    _a = field_validator("observed_at")(aware)

class FundamentalFact(FrozenModel):
    name: str; value: float | str | None; period_start: date | None = None; period_end: date | None = None
    filing_date: date | None = None; accession_id: str | None = None; form: str | None = None
    fiscal_year: int | None = None; fiscal_period: str | None = None; frame: str | None = None
    unit: str | None = None; is_instant: bool; duration_days: int | None = None; source: str

class FundamentalsSnapshot(FrozenModel):
    available: bool; facts: tuple[FundamentalFact, ...] = (); latest_filing_date: date | None = None

class MarketSnapshot(FrozenModel):
    schema_version: str; ticker: str; decision_date: date; information_cutoff: datetime
    price_bars: tuple[PriceBar, ...]; technicals: TechnicalFeatures; news: tuple[NewsItem, ...] = ()
    sentiment: SentimentSummary; macro: tuple[MacroObservation, ...] = ()
    prediction_markets: tuple[PredictionMarketObservation, ...] = ()
    fundamentals: FundamentalsSnapshot; source_meta: dict[str, SourceMeta]; snapshot_hash: str = ""
    _a = field_validator("information_cutoff")(aware)
    _frozen_source_meta = field_validator("source_meta", mode="after")(frozen_dict)
    @field_validator("ticker")
    @classmethod
    def ticker_upper(cls, v):
        if not v.strip(): raise ValueError("ticker cannot be empty")
        return v.strip().upper()

class SnapshotManifestEntry(FrozenModel):
    snapshot_hash: str; ticker: str; decision_date: date; information_cutoff: datetime
    schema_version: str; config_hash: str; relative_path: str
    validation_status: Literal["VALID"]; created_at: datetime
    _a = field_validator("information_cutoff", "created_at")(aware)
