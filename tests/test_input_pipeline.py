from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from benchmark.core.hashing import content_hash
from benchmark.core.schemas import PriceBar, TechnicalFeatures, SentimentSummary, FundamentalsSnapshot, SourceMeta, MarketSnapshot, NewsItem
from benchmark.data.cache import RawCache
from benchmark.data.indicators import compute_technicals
from benchmark.data.snapshot_store import SnapshotStore
from benchmark.data.snapshot_builder import build_market_snapshot
from benchmark.core.config import DataConfig
from benchmark.data.validators import PointInTimeViolation
from benchmark.data.yahoo import YahooConnector
from benchmark.data.audit import audit_snapshot

def bars():
    start = datetime(2024,1,2,tzinfo=timezone.utc); result=[]
    for i in range(60):
        close=100+i; result.append(PriceBar(timestamp=start+timedelta(days=i), open=close-.5, high=close+1, low=close-1, close=close, adjusted_close=close, volume=1000+i))
    return tuple(result)

def snapshot():
    items=bars(); cutoff=datetime(2024,4,30,20,tzinfo=timezone.utc)
    return MarketSnapshot(schema_version="1.0.0", ticker="aapl", decision_date=cutoff.date(), information_cutoff=cutoff,
      price_bars=items, technicals=compute_technicals(items), sentiment=SentimentSummary(available=False,article_count=0),
      fundamentals=FundamentalsSnapshot(available=False), source_meta={"prices": SourceMeta(provider="yahoo",retrieved_at=datetime.now(timezone.utc),request_key="abc",available=True)})

def test_hash_is_deterministic(): assert content_hash({"b":2,"a":1}) == content_hash({"a":1,"b":2})
def test_naive_timestamp_rejected():
    with pytest.raises(ValidationError): PriceBar(timestamp=datetime(2024,1,1),open=1,high=2,low=0,close=1,volume=1)
def test_indicators_deterministic():
    assert compute_technicals(bars()) == compute_technicals(bars())
    assert compute_technicals(bars()).sma_50 is not None
def test_cache_roundtrip(tmp_path):
    cache=RawCache(tmp_path); stored=cache.store("x","endpoint",{"a":1},{"ok":True})
    assert cache.load("x",stored.request_key).payload == {"ok":True}
def test_yahoo_normalize_filters_future(tmp_path):
    payload={"chart":{"result":[{"timestamp":[1704067200,1704153600],"indicators":{"quote":[{"open":[10,20],"high":[11,21],"low":[9,19],"close":[10.5,20.5],"volume":[100,200]}],"adjclose":[{"adjclose":[10.5,20.5]}]}}]}}
    artifact=RawCache(tmp_path).store("yahoo","e",{},payload)
    assert len(YahooConnector.normalize(artifact,datetime(2024,1,1,23,59,tzinfo=timezone.utc))) == 1
def test_snapshot_persistence_is_reproducible(tmp_path):
    store=SnapshotStore(tmp_path); a,path=store.persist(snapshot(),"config"); b,_=store.persist(snapshot(),"config")
    assert a.snapshot_hash == b.snapshot_hash and path.exists()
    assert len((tmp_path/"manifests"/"snapshots.jsonl").read_text().splitlines()) == 1
def test_future_news_fails(tmp_path):
    item=NewsItem(id="future",title="x",source="fixture",published_at=datetime(2024,5,1,tzinfo=timezone.utc))
    invalid=snapshot().model_copy(update={"news":(item,)})
    with pytest.raises(PointInTimeViolation): SnapshotStore(tmp_path).persist(invalid,"config")

def test_market_snapshot_builder(tmp_path):
    cache=RawCache(tmp_path/"raw")
    stamps=[int(b.timestamp.timestamp()) for b in bars()]
    values=lambda name: [getattr(b,name) for b in bars()]
    payload={"chart":{"result":[{"timestamp":stamps,"indicators":{"quote":[{k:values(k) for k in ("open","high","low","close","volume")}],"adjclose":[{"adjclose":values("adjusted_close")}]}}]}}
    class FakeConnector:
        def fetch_daily(self,*args,**kwargs): return cache.store("yahoo","fixture",{},payload)
        normalize=staticmethod(YahooConnector.normalize)
    frozen,path=build_market_snapshot("aapl",datetime(2024,4,30).date(),DataConfig(),tmp_path,FakeConnector())
    assert frozen.ticker == "AAPL" and len(frozen.price_bars) == 60 and path.exists()
    report=audit_snapshot(frozen,())
    assert not report.valid and "fundamentals unavailable" in report.errors
