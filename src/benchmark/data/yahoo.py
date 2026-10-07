import json
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from benchmark.core.schemas import PriceBar
from benchmark.data.cache import RawCache

ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart"
class YahooDataError(RuntimeError): pass

def _get(url):
    with urlopen(Request(url, headers={"User-Agent": "input-benchmark/0.1"}), timeout=30) as response:
        return json.loads(response.read())

class YahooConnector:
    def __init__(self, cache: RawCache, get_json=_get): self.cache, self.get_json = cache, get_json
    def fetch_daily(self, ticker, start, end, refresh=False):
        if start.tzinfo is None or end.tzinfo is None: raise ValueError("timezone-aware dates required")
        ticker = ticker.strip().upper(); endpoint = f"{ENDPOINT}/{ticker}"
        params = {"ticker": ticker, "period1": int(start.timestamp()), "period2": int(end.timestamp()), "interval": "1d", "events": "div,splits"}
        key = self.cache.request_key("yahoo", endpoint, params)
        if not refresh and (cached := self.cache.load("yahoo", key)): return cached
        query = urlencode({k: v for k, v in params.items() if k != "ticker"})
        return self.cache.store("yahoo", endpoint, params, self.get_json(f"{endpoint}?{query}"))
    @staticmethod
    def normalize(artifact, cutoff):
        try:
            result = artifact.payload["chart"]["result"][0]; timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            adjusted = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
        except (KeyError, IndexError, TypeError) as error:
            raise YahooDataError(f"invalid Yahoo response: {error}") from error
        bars = []
        for i, stamp in enumerate(timestamps):
            values = {name: quote[name][i] for name in ("open", "high", "low", "close", "volume")}
            when = datetime.fromtimestamp(stamp, tz=timezone.utc)
            if any(v is None for v in values.values()) or when > cutoff.astimezone(timezone.utc): continue
            bars.append(PriceBar(timestamp=when, adjusted_close=adjusted[i] if adjusted else None, **values))
        return tuple(sorted(bars, key=lambda b: b.timestamp))
