from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from statistics import median
from urllib.parse import urlencode
from benchmark.core.schemas import NewsItem, SentimentSummary
from benchmark.data.cache import RawCache
from benchmark.data.http import get_json

ENDPOINT = "https://www.alphavantage.co/query"

class AlphaVantageError(RuntimeError): pass

class AlphaVantageConnector:
    def __init__(self, cache: RawCache, api_key: str, get=get_json):
        self.cache, self.api_key, self.get = cache, api_key, get
    def fetch_news(self, ticker, start, cutoff, refresh=False):
        params={"function":"NEWS_SENTIMENT","tickers":ticker.upper(),"time_from":start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M"),
          "time_to":cutoff.astimezone(timezone.utc).strftime("%Y%m%dT%H%M"),"limit":1000,"sort":"EARLIEST"}
        cache_params={**params,"apikey_fingerprint":sha256(self.api_key.encode()).hexdigest()[:12]}
        key=self.cache.request_key("alpha_vantage",ENDPOINT,cache_params)
        artifact=None if refresh else self.cache.load("alpha_vantage",key)
        if artifact is None:
            payload=self.get(f"{ENDPOINT}?{urlencode({**params,'apikey':self.api_key})}")
            artifact=self.cache.store("alpha_vantage",ENDPOINT,cache_params,payload)
        payload=artifact.payload
        if "Information" in payload or "Note" in payload or "Error Message" in payload:
            raise AlphaVantageError(payload.get("Information") or payload.get("Note") or payload.get("Error Message"))
        return artifact
    @staticmethod
    def normalize(artifact, ticker, cutoff):
        unique={}
        for row in artifact.payload.get("feed",[]):
            try: published=datetime.strptime(row["time_published"],"%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
            except (KeyError,ValueError): continue
            if published > cutoff.astimezone(timezone.utc): continue
            ticker_row=next((x for x in row.get("ticker_sentiment",[]) if x.get("ticker","").upper()==ticker.upper()),{})
            url=row.get("url"); identity=url or f"{row.get('title','')}|{row.get('source','')}|{published.isoformat()}"
            item=NewsItem(id=sha256(identity.encode()).hexdigest()[:20],title=row.get("title") or "Untitled",
              summary=row.get("summary"),source=row.get("source") or "unknown",url=url,published_at=published,
              ticker_relevance=_float(ticker_row.get("relevance_score")),ticker_sentiment_score=_float(ticker_row.get("ticker_sentiment_score")),
              ticker_sentiment_label=ticker_row.get("ticker_sentiment_label"))
            unique[item.id]=item
        return tuple(sorted(unique.values(),key=lambda x:x.published_at))

def _float(value):
    try: return float(value)
    except (TypeError,ValueError): return None

def summarize_sentiment(news: tuple[NewsItem,...]) -> SentimentSummary:
    scored=[x for x in news if x.ticker_sentiment_score is not None]
    if not scored: return SentimentSummary(available=False,article_count=len(news))
    weights=[x.ticker_relevance if x.ticker_relevance is not None else 1.0 for x in scored]
    total=sum(weights); weighted=sum(x.ticker_sentiment_score*w for x,w in zip(scored,weights))/total if total else None
    labels=[(x.ticker_sentiment_label or "").lower() for x in scored]; n=len(scored)
    positive=max(scored,key=lambda x:x.ticker_sentiment_score); negative=min(scored,key=lambda x:x.ticker_sentiment_score)
    return SentimentSummary(available=True,article_count=len(news),weighted_mean=weighted,
      median=median(x.ticker_sentiment_score for x in scored),bullish_fraction=sum("bull" in x for x in labels)/n,
      neutral_fraction=sum("neutral" in x for x in labels)/n,bearish_fraction=sum("bear" in x for x in labels)/n,
      strongest_positive_news_id=positive.id,strongest_negative_news_id=negative.id)
