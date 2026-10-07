from __future__ import annotations

from collections import Counter
import re
from typing import Iterable

from benchmark.agents.contracts import RunResult


TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def exact_action_agreement(results: Iterable[RunResult]) -> bool | None:
    actions = [result.final_decision.action for result in results]
    return None if not actions else len(set(actions)) == 1


def pairwise_action_agreement(results: Iterable[RunResult]) -> dict[str, bool]:
    values = tuple(results)
    agreement: dict[str, bool] = {}
    for left_index, left in enumerate(values):
        for right in values[left_index + 1 :]:
            key = f"{left.context.framework.value}:{right.context.framework.value}"
            agreement[key] = left.final_decision.action == right.final_decision.action
    return agreement


def fleiss_kappa(action_rows: Iterable[Iterable[str]]) -> float | None:
    """Fleiss' kappa for equal-size rows of categorical framework decisions."""
    rows = [tuple(row) for row in action_rows]
    if not rows:
        return None
    raters = len(rows[0])
    if raters < 2 or any(len(row) != raters for row in rows):
        raise ValueError("Fleiss' kappa requires equal rows with at least two raters")
    categories = sorted({action for row in rows for action in row})
    counts = [Counter(row) for row in rows]
    observed = sum(
        (sum(count * count for count in row.values()) - raters) / (raters * (raters - 1))
        for row in counts
    ) / len(rows)
    proportions = {
        category: sum(row[category] for row in counts) / (len(rows) * raters)
        for category in categories
    }
    expected = sum(value * value for value in proportions.values())
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def evidence_jaccard(left: RunResult, right: RunResult) -> float:
    left_evidence = _evidence(left)
    right_evidence = _evidence(right)
    union = left_evidence | right_evidence
    return 1.0 if not union else len(left_evidence & right_evidence) / len(union)


def rationale_token_jaccard(left: RunResult, right: RunResult) -> float:
    left_tokens = _tokens(left.final_decision.rationale)
    right_tokens = _tokens(right.final_decision.rationale)
    union = left_tokens | right_tokens
    return 1.0 if not union else len(left_tokens & right_tokens) / len(union)


def repeated_run_stability(results: Iterable[RunResult]) -> float | None:
    actions = [result.final_decision.action.value for result in results]
    if not actions:
        return None
    return max(Counter(actions).values()) / len(actions)


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in TOKEN_PATTERN.findall(text)}


def _evidence(result: RunResult) -> set[str]:
    evidence: list[str] = []
    for report in (
        result.market_report,
        result.news_report,
        result.sentiment_report,
        result.fundamentals_report,
    ):
        evidence.extend(report.key_evidence)
    evidence.extend(result.bull_argument.evidence)
    evidence.extend(result.bear_argument.evidence)
    evidence.extend(result.research_manager.reasons)
    return {item.strip().lower() for item in evidence if item.strip()}
