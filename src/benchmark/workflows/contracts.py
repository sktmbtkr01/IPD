from __future__ import annotations

from typing import Protocol

from benchmark.agents.contracts import RunContext, RunResult
from benchmark.core.schemas import MarketSnapshot

CANONICAL_STAGES = (
    "market_analyst",
    "news_analyst",
    "sentiment_analyst",
    "fundamentals_analyst",
    "bull_researcher",
    "bear_researcher",
    "research_manager",
    "trader",
    "risk_aggressive",
    "risk_neutral",
    "risk_conservative",
    "portfolio_manager",
)

STAGE_DEPENDENCIES = {
    "market_analyst": (),
    "news_analyst": (),
    "sentiment_analyst": (),
    "fundamentals_analyst": (),
    "bull_researcher": ("market_analyst", "news_analyst", "sentiment_analyst", "fundamentals_analyst"),
    "bear_researcher": ("market_analyst", "news_analyst", "sentiment_analyst", "fundamentals_analyst"),
    "research_manager": ("bull_researcher", "bear_researcher"),
    "trader": ("research_manager",),
    "risk_aggressive": ("trader", "research_manager"),
    "risk_neutral": ("trader", "research_manager"),
    "risk_conservative": ("trader", "research_manager"),
    "portfolio_manager": (
        "research_manager",
        "trader",
        "risk_aggressive",
        "risk_neutral",
        "risk_conservative",
    ),
}

PARALLEL_GROUPS = (
    ("market_analyst", "news_analyst", "sentiment_analyst", "fundamentals_analyst"),
    ("bull_researcher", "bear_researcher"),
    ("risk_aggressive", "risk_neutral", "risk_conservative"),
)

class FrameworkRunner(Protocol):
    async def run_workflow(self, snapshot: MarketSnapshot, run_context: RunContext) -> RunResult: ...
