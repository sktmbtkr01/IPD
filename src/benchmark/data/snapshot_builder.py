from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from benchmark.core.config import DataConfig
from benchmark.core.schemas import FundamentalsSnapshot, MarketSnapshot, SentimentSummary, SourceMeta
from benchmark.core.hashing import content_hash
from benchmark.data.alpha_vantage import AlphaVantageConnector, summarize_sentiment
from benchmark.data.fred import FredConnector
from benchmark.data.sec_edgar import SecConnector
from benchmark.data.gdelt import GdeltConnector
from benchmark.data.marketaux import MarketauxConnector
from benchmark.data.cache import RawCache
from benchmark.data.indicators import compute_technicals
from benchmark.data.snapshot_store import SnapshotStore
from benchmark.data.yahoo import YahooConnector

def build_market_snapshot(ticker: str, decision_date: date, config: DataConfig,
                          data_root: Path, connector: YahooConnector | None = None):
    """Build the first vertical slice: prices + technicals + immutable storage."""
    cutoff = config.cutoff_for(decision_date)
    connector = connector or YahooConnector(RawCache(data_root / "raw"))
    # Calendar buffer covers weekends/holidays and indicator warm-up.
    start = cutoff - timedelta(days=max(180, config.market_lookback_trading_days * 2))
    artifact = connector.fetch_daily(ticker, start, cutoff + timedelta(days=1))
    bars = connector.normalize(artifact, cutoff)[-config.market_lookback_trading_days:]
    if len(bars) < 50:
        raise ValueError(f"insufficient eligible price history: {len(bars)} bars")
    snapshot = MarketSnapshot(
        schema_version=config.schema_version, ticker=ticker, decision_date=decision_date,
        information_cutoff=cutoff, price_bars=bars, technicals=compute_technicals(bars, config.indicator_set_version),
        sentiment=SentimentSummary(available=False, article_count=0),
        fundamentals=FundamentalsSnapshot(available=False),
        source_meta={"prices": SourceMeta(provider="yahoo", retrieved_at=artifact.retrieved_at,
          request_key=artifact.request_key, source_timestamp=bars[-1].timestamp, available=True)}
    )
    return SnapshotStore(data_root).persist(snapshot, config.config_hash)

def build_full_snapshot(ticker: str, decision_date: date, config: DataConfig, data_root: Path,
                        yahoo: YahooConnector, alpha: AlphaVantageConnector,
                        fred: FredConnector, sec: SecConnector, gdelt: GdeltConnector | None = None,
                        marketaux: MarketauxConnector | None = None):
    cutoff=config.cutoff_for(decision_date); start=cutoff-timedelta(days=max(180,config.market_lookback_trading_days*2))
    price_artifact=yahoo.fetch_daily(ticker,start,cutoff+timedelta(days=1)); bars=yahoo.normalize(price_artifact,cutoff)[-config.market_lookback_trading_days:]
    if len(bars)<50: raise ValueError(f"insufficient eligible price history: {len(bars)} bars")
    metadata={"prices":SourceMeta(provider="yahoo",retrieved_at=price_artifact.retrieved_at,request_key=price_artifact.request_key,
      source_timestamp=bars[-1].timestamp,available=True)}
    news=(); sentiment=SentimentSummary(available=False,article_count=0); macro=(); fundamentals=FundamentalsSnapshot(available=False)
    marketaux_error=None
    if marketaux is not None:
      try:
        artifacts=marketaux.fetch_news(ticker,cutoff-timedelta(days=config.news_lookback_days),cutoff)
        news=marketaux.normalize(artifacts,ticker,cutoff); sentiment=summarize_sentiment(news)
        request_key=content_hash([x.request_key for x in artifacts]); retrieved=max(x.retrieved_at for x in artifacts)
        metadata["news"]=SourceMeta(provider="marketaux",retrieved_at=retrieved,request_key=request_key,
          source_timestamp=max((x.published_at for x in news),default=None),available=bool(news),error=None if news else "no matching articles")
        metadata["sentiment"]=SourceMeta(provider="marketaux",retrieved_at=retrieved,request_key=request_key,available=sentiment.available)
      except Exception as error:
        marketaux_error=error
    if not news:
     try:
        a=alpha.fetch_news(ticker,cutoff-timedelta(days=config.news_lookback_days),cutoff); news=alpha.normalize(a,ticker,cutoff); sentiment=summarize_sentiment(news)
        metadata["news"]=SourceMeta(provider="alpha_vantage",retrieved_at=a.retrieved_at,request_key=a.request_key,
          source_timestamp=max((x.published_at for x in news),default=None),available=True)
        metadata["sentiment"]=SourceMeta(provider="alpha_vantage",retrieved_at=a.retrieved_at,request_key=a.request_key,available=sentiment.available)
     except Exception as alpha_error:
        try:
            if gdelt is None: raise RuntimeError("GDELT fallback not configured")
            g=gdelt.fetch_news(ticker,cutoff-timedelta(days=config.news_lookback_days),cutoff); news=gdelt.normalize(g,cutoff)
            metadata["news"]=SourceMeta(provider="gdelt",retrieved_at=g.retrieved_at,request_key=g.request_key,
              source_timestamp=max((x.published_at for x in news),default=None),available=bool(news),
              error=None if news else "no matching articles")
            sentiment=SentimentSummary(available=False,article_count=len(news))
            metadata["sentiment"]=SourceMeta(provider="alpha_vantage",retrieved_at=datetime.now(timezone.utc),
              request_key="unavailable",available=False,error=f"historical ticker sentiment unavailable: {alpha_error}")
        except Exception as fallback_error:
            metadata["news"]=SourceMeta(provider="alpha_vantage",retrieved_at=datetime.now(timezone.utc),request_key="unavailable",available=False,
              error=f"Marketaux: {marketaux_error}; Alpha Vantage: {alpha_error}; GDELT: {fallback_error}")
            metadata["sentiment"]=SourceMeta(provider="alpha_vantage",retrieved_at=datetime.now(timezone.utc),request_key="unavailable",available=False,error=str(alpha_error))
            if config.required_sources.news: raise
    try:
        observations=[]; artifacts=[]
        for series in config.macro_series:
            artifact=fred.fetch_series(series,decision_date); artifacts.append(artifact); observations.append(fred.normalize(artifact,series))
        macro=tuple(observations); available=any(x.value is not None for x in macro)
        metadata["macro"]=SourceMeta(provider="fred_alfred",retrieved_at=max(x.retrieved_at for x in artifacts),
          request_key=content_hash([x.request_key for x in artifacts]),available=available,error=None if available else "no eligible observations")
    except Exception as error:
        metadata["macro"]=SourceMeta(provider="fred_alfred",retrieved_at=datetime.now(timezone.utc),request_key="unavailable",available=False,error=str(error))
        if config.required_sources.macro: raise
    try:
        facts_artifact,_=sec.fetch_company_facts(ticker); fundamentals=sec.normalize(facts_artifact,cutoff)
        metadata["fundamentals"]=SourceMeta(provider="sec_edgar",retrieved_at=facts_artifact.retrieved_at,request_key=facts_artifact.request_key,
          available=fundamentals.available,error=None if fundamentals.available else "no eligible facts")
    except Exception as error:
        metadata["fundamentals"]=SourceMeta(provider="sec_edgar",retrieved_at=datetime.now(timezone.utc),request_key="unavailable",available=False,error=str(error))
        if config.required_sources.fundamentals: raise
    snapshot=MarketSnapshot(schema_version=config.schema_version,ticker=ticker,decision_date=decision_date,information_cutoff=cutoff,
      price_bars=bars,technicals=compute_technicals(bars, config.indicator_set_version),news=news,sentiment=sentiment,macro=macro,
      fundamentals=fundamentals,source_meta=metadata)
    return SnapshotStore(data_root).persist(snapshot,config.config_hash)
