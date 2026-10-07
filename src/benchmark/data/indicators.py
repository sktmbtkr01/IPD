import math, statistics
from benchmark.core.schemas import PriceBar, TechnicalFeatures

def sma(values, n): return statistics.fmean(values[-n:]) if len(values) >= n else None
def ema(values, n):
    if not values: return []
    alpha = 2 / (n + 1); result = [values[0]]
    for value in values[1:]: result.append(alpha * value + (1 - alpha) * result[-1])
    return result
def ret(values, n): return values[-1] / values[-n-1] - 1 if len(values) > n and values[-n-1] else None

def compute_technicals(bars: tuple[PriceBar, ...], version: str = "1.0.0") -> TechnicalFeatures:
    if not bars: raise ValueError("at least one price bar is required")
    closes = [b.adjusted_close if b.adjusted_close is not None else b.close for b in bars]
    e12, e20, e26 = ema(closes, 12), ema(closes, 20), ema(closes, 26)
    macds = [a-b for a, b in zip(e12, e26, strict=True)]; signal = ema(macds, 9)
    changes = [b-a for a, b in zip(closes, closes[1:])]; rsi = None
    if len(changes) >= 14:
        recent = changes[-14:]; gain = statistics.fmean(max(x, 0) for x in recent); loss = statistics.fmean(max(-x, 0) for x in recent)
        rsi = 100.0 if loss == 0 else 100 - 100 / (1 + gain/loss)
    mean20 = sma(closes, 20); sd20 = statistics.pstdev(closes[-20:]) if len(closes) >= 20 else None
    ranges = [max(b.high-b.low, abs(b.high-(bars[i-1].close if i else b.close)), abs(b.low-(bars[i-1].close if i else b.close))) for i,b in enumerate(bars)]
    returns = [b/a-1 for a,b in zip(closes, closes[1:]) if a]
    vol = statistics.stdev(returns[-20:])*math.sqrt(252) if len(returns) >= 20 else None
    return TechnicalFeatures(version=version, as_of=bars[-1].timestamp, sma_20=mean20, sma_50=sma(closes,50), ema_20=e20[-1], rsi_14=rsi,
      macd=macds[-1], macd_signal=signal[-1], bollinger_upper=mean20+2*sd20 if sd20 is not None else None,
      bollinger_lower=mean20-2*sd20 if sd20 is not None else None, atr_14=sma(ranges,14), realized_volatility=vol,
      return_1d=ret(closes,1), return_5d=ret(closes,5), return_20d=ret(closes,20))
