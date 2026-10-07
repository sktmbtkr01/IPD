from benchmark.core.schemas import MarketSnapshot
class PointInTimeViolation(ValueError): pass

def validate_point_in_time(snapshot: MarketSnapshot):
    cutoff = snapshot.information_cutoff; errors = []
    if any(x.timestamp > cutoff for x in snapshot.price_bars): errors.append("price bar after cutoff")
    if snapshot.technicals.as_of > cutoff: errors.append("technicals after cutoff")
    if any(x.published_at > cutoff for x in snapshot.news): errors.append("news after cutoff")
    if any(x.observed_at and x.observed_at > cutoff for x in snapshot.prediction_markets): errors.append("prediction market after cutoff")
    if any(x.filing_date and x.filing_date > cutoff.date() for x in snapshot.fundamentals.facts): errors.append("filing after cutoff")
    if any(x.realtime_start and x.realtime_start > cutoff.date() for x in snapshot.macro): errors.append("macro unavailable at cutoff")
    if errors: raise PointInTimeViolation("; ".join(errors))
