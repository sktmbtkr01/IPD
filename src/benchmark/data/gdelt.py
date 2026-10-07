from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlencode
from benchmark.core.schemas import NewsItem
from benchmark.data.cache import RawCache
from benchmark.data.http import get_json

ENDPOINT="https://api.gdeltproject.org/api/v2/doc/doc"
class GdeltError(RuntimeError): pass

class GdeltConnector:
    """Deterministic metadata-only fallback for historical company news."""
    def __init__(self,cache:RawCache,get=get_json): self.cache,self.get=cache,get
    def fetch_news(self,ticker,start,cutoff,refresh=False):
        company={"AAPL":"\"Apple Inc\" OR AAPL"}.get(ticker.upper(),ticker.upper())
        params={"query":f"({company}) sourcelang:english","mode":"artlist","maxrecords":250,"format":"json",
          "sort":"datedesc","startdatetime":start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
          "enddatetime":cutoff.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")}
        key=self.cache.request_key("gdelt",ENDPOINT,params)
        if not refresh and (cached:=self.cache.load("gdelt",key)): return cached
        payload=self.get(f"{ENDPOINT}?{urlencode(params)}")
        if not isinstance(payload,dict): raise GdeltError("unexpected GDELT response")
        return self.cache.store("gdelt",ENDPOINT,params,payload)
    @staticmethod
    def normalize(artifact,cutoff):
        unique={}
        for row in artifact.payload.get("articles",[]):
            raw=(row.get("seendate") or "").rstrip("Z")
            parsed=None
            for fmt in ("%Y%m%dT%H%M%S","%Y%m%d%H%M%S"):
                try: parsed=datetime.strptime(raw,fmt).replace(tzinfo=timezone.utc); break
                except ValueError: pass
            if parsed is None or parsed>cutoff.astimezone(timezone.utc): continue
            url=row.get("url"); identity=url or f"{row.get('title','')}|{row.get('domain','')}|{raw}"
            item=NewsItem(id=sha256(identity.encode()).hexdigest()[:20],title=row.get("title") or "Untitled",
              source=f"GDELT:{row.get('domain') or 'unknown'}",url=url,published_at=parsed)
            unique[item.id]=item
        return tuple(sorted(unique.values(),key=lambda x:x.published_at))
