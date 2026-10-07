from __future__ import annotations
import math
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlencode
from benchmark.core.schemas import NewsItem, SentimentSummary
from benchmark.data.cache import RawCache
from benchmark.data.http import get_json

ENDPOINT="https://api.marketaux.com/v1/news/all"
class MarketauxError(RuntimeError): pass

class MarketauxConnector:
    def __init__(self,cache:RawCache,api_token:str,min_match_score:float=10.0,bullish:float=0.15,bearish:float=-0.15,get=get_json):
        self.cache,self.api_token,self.min_match_score,self.bullish,self.bearish,self.get=cache,api_token,min_match_score,bullish,bearish,get
    def _page(self,ticker,start,cutoff,page,refresh=False):
        params={"symbols":ticker.upper(),"filter_entities":"true","must_have_entities":"true","language":"en",
          "published_after":start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
          "published_before":cutoff.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
          "sort":"published_at","min_match_score":self.min_match_score,"limit":3,"page":page}
        cache_params={**params,"token_fingerprint":sha256(self.api_token.encode()).hexdigest()[:12]}
        key=self.cache.request_key("marketaux",ENDPOINT,cache_params)
        artifact=None if refresh else self.cache.load("marketaux",key)
        if artifact is None:
            payload=self.get(f"{ENDPOINT}?{urlencode({**params,'api_token':self.api_token})}")
            artifact=self.cache.store("marketaux",ENDPOINT,cache_params,payload)
        if "error" in artifact.payload:
            error=artifact.payload["error"]; raise MarketauxError(error.get("message",str(error)) if isinstance(error,dict) else str(error))
        return artifact
    def fetch_news(self,ticker,start,cutoff,max_pages=100,refresh=False):
        first=self._page(ticker,start,cutoff,1,refresh); meta=first.payload.get("meta",{})
        total=math.ceil(int(meta.get("found",0))/max(int(meta.get("limit",3)),1)); pages=min(max(total,1),max_pages)
        return tuple([first]+[self._page(ticker,start,cutoff,page,refresh) for page in range(2,pages+1)])
    def normalize(self,artifacts,ticker,cutoff):
        unique={}
        for artifact in artifacts:
            for row in artifact.payload.get("data",[]):
                try: published=datetime.fromisoformat(row["published_at"].replace("Z","+00:00")).astimezone(timezone.utc)
                except (KeyError,ValueError): continue
                if published>cutoff.astimezone(timezone.utc): continue
                entity=next((x for x in row.get("entities",[]) if x.get("symbol","").upper()==ticker.upper()),None)
                if entity is None: continue
                url=row.get("url"); identity=row.get("uuid") or url or f"{row.get('title','')}|{published.isoformat()}"
                item=NewsItem(id=str(identity),title=row.get("title") or "Untitled",
                  summary=row.get("description") or row.get("snippet"),source=(row.get("source") or "marketaux"),url=url,
                  published_at=published,ticker_relevance=_relevance(entity.get("match_score")),
                  ticker_sentiment_score=_float(entity.get("sentiment_score")),
                  ticker_sentiment_label=_label(_float(entity.get("sentiment_score")),self.bullish,self.bearish))
                unique[item.id]=item
        return tuple(sorted(unique.values(),key=lambda x:x.published_at))

def _float(value):
    try: return float(value)
    except (TypeError,ValueError): return None
def _relevance(value):
    score=_float(value)
    return None if score is None else max(0.0,min(1.0,score/100.0))
def _label(value,bullish,bearish):
    if value is None: return None
    if value>bullish: return "Bullish"
    if value<bearish: return "Bearish"
    return "Neutral"
