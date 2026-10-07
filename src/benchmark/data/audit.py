from dataclasses import dataclass
from benchmark.core.hashing import calculate_snapshot_hash
from benchmark.core.schemas import MarketSnapshot
from benchmark.data.validators import validate_point_in_time

@dataclass(frozen=True)
class AuditReport:
    errors: tuple[str,...]
    warnings: tuple[str,...]
    @property
    def valid(self): return not self.errors

def audit_snapshot(snapshot: MarketSnapshot, expected_macro: tuple[str,...], require_news: bool=False) -> AuditReport:
    errors=[]; warnings=[]
    try: validate_point_in_time(snapshot)
    except ValueError as error: errors.append(str(error))
    if calculate_snapshot_hash(snapshot)!=snapshot.snapshot_hash: errors.append("snapshot hash mismatch")
    if len(snapshot.price_bars)<50: errors.append("insufficient price history")
    timestamps=[x.timestamp for x in snapshot.price_bars]
    if timestamps!=sorted(set(timestamps)): errors.append("price timestamps are not sorted and unique")
    if not snapshot.technicals.version: errors.append("indicator version missing")
    macro_ids=tuple(x.series_id for x in snapshot.macro)
    if macro_ids!=expected_macro: errors.append("macro series set/order mismatch")
    if any(not x.units for x in snapshot.macro): errors.append("macro units missing")
    if not snapshot.fundamentals.available: errors.append("fundamentals unavailable")
    for fact in snapshot.fundamentals.facts:
        if not fact.accession_id or not fact.form or not fact.unit: errors.append(f"incomplete SEC provenance: {fact.name}")
        if fact.period_start and fact.duration_days!=(fact.period_end-fact.period_start).days: errors.append(f"invalid duration: {fact.name}")
        if fact.is_instant != (fact.period_start is None): errors.append(f"invalid instant classification: {fact.name}")
    news_meta=snapshot.source_meta.get("news")
    if require_news and (news_meta is None or not news_meta.available): errors.append("required news unavailable")
    elif news_meta is None or not news_meta.available: warnings.append("historical news unavailable")
    if not snapshot.sentiment.available: warnings.append("ticker-specific sentiment unavailable")
    return AuditReport(tuple(errors),tuple(warnings))
