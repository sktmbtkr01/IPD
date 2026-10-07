import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field, model_validator
from benchmark.core.hashing import content_hash

class RequiredSources(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prices: bool = True; news: bool = False; macro: bool = False
    fundamentals: bool = False; prediction_markets: bool = False

class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "1.1.0"; decision_timezone: str = "America/New_York"
    decision_time: time = time(16); market_lookback_trading_days: int = Field(90, ge=50)
    news_lookback_days: int = Field(7, ge=1)
    news_min_match_score: float = Field(10.0, ge=0, le=100)
    sentiment_bullish_threshold: float = Field(0.15, ge=-1, le=1)
    sentiment_bearish_threshold: float = Field(-0.15, ge=-1, le=1)
    macro_series: tuple[str, ...] = ("DFF", "CPIAUCSL", "UNRATE", "DGS10", "T10Y2Y")
    indicator_set_version: str = "1.0.0"; required_sources: RequiredSources = RequiredSources()
    @model_validator(mode="after")
    def validate_sentiment_thresholds(self):
        if self.sentiment_bearish_threshold >= self.sentiment_bullish_threshold:
            raise ValueError("bearish threshold must be below bullish threshold")
        return self
    def cutoff_for(self, day: date) -> datetime:
        return datetime.combine(day, self.decision_time, tzinfo=ZoneInfo(self.decision_timezone))
    @property
    def config_hash(self): return content_hash(self)
    @classmethod
    def from_json(cls, path: Path): return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))

