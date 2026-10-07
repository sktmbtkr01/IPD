from datetime import date, datetime, timezone
from benchmark.data.alpha_vantage import AlphaVantageConnector, summarize_sentiment
from benchmark.data.cache import RawCache
from benchmark.data.fred import FredConnector
from benchmark.data.sec_edgar import SecConnector
from benchmark.data.gdelt import GdeltConnector
from benchmark.data.marketaux import MarketauxConnector

def test_alpha_filters_future_and_aggregates(tmp_path):
    payload={"feed":[{"title":"eligible","source":"fixture","url":"https://x/1","time_published":"20260714T120000",
      "ticker_sentiment":[{"ticker":"AAPL","relevance_score":"0.8","ticker_sentiment_score":"0.5","ticker_sentiment_label":"Bullish"}]},
      {"title":"future","source":"fixture","url":"https://x/2","time_published":"20260715T120000","ticker_sentiment":[]}]}
    artifact=RawCache(tmp_path).store("alpha_vantage","fixture",{},payload)
    news=AlphaVantageConnector.normalize(artifact,"AAPL",datetime(2026,7,14,20,tzinfo=timezone.utc))
    assert len(news)==1 and summarize_sentiment(news).bullish_fraction==1

def test_fred_preserves_vintage_dates(tmp_path):
    payload={"observations":[{"realtime_start":"2026-07-14","realtime_end":"2026-07-14","date":"2026-07-13","value":"4.25"}]}
    artifact=RawCache(tmp_path).store("fred","fixture",{},payload)
    value=FredConnector.normalize(artifact,"DFF")
    assert value.value==4.25 and value.realtime_start==date(2026,7,14)

def test_sec_excludes_filings_after_cutoff(tmp_path):
    rows=[{"filed":"2026-05-01","end":"2026-03-31","form":"10-Q","val":100,"accn":"old"},
      {"filed":"2026-08-01","end":"2026-06-30","form":"10-Q","val":200,"accn":"future"}]
    payload={"facts":{"us-gaap":{"Assets":{"units":{"USD":rows}}}}}
    artifact=RawCache(tmp_path).store("sec","fixture",{},payload)
    result=SecConnector.normalize(artifact,datetime(2026,7,14,20,tzinfo=timezone.utc))
    assert result.facts[0].value==100 and result.facts[0].accession_id=="old"

def test_gdelt_filters_future_and_deduplicates(tmp_path):
    payload={"articles":[{"title":"Apple report","domain":"example.com","url":"https://example.com/a","seendate":"20260714T120000Z"},
      {"title":"duplicate","domain":"example.com","url":"https://example.com/a","seendate":"20260714T130000Z"},
      {"title":"future","domain":"example.com","url":"https://example.com/b","seendate":"20260715T120000Z"}]}
    artifact=RawCache(tmp_path).store("gdelt","fixture",{},payload)
    news=GdeltConnector.normalize(artifact,datetime(2026,7,14,20,tzinfo=timezone.utc))
    assert len(news)==1 and news[0].source=="GDELT:example.com"

def test_marketaux_normalizes_entity_scores(tmp_path):
    payload={"meta":{"found":1,"limit":3},"data":[{"uuid":"one","title":"Apple news","source":"example.com",
      "published_at":"2026-07-14T12:00:00Z","entities":[{"symbol":"AAPL","match_score":28.0,"sentiment_score":0.4}]}]}
    artifact=RawCache(tmp_path).store("marketaux","fixture",{},payload)
    connector=MarketauxConnector(RawCache(tmp_path),"token")
    news=connector.normalize((artifact,),"AAPL",datetime(2026,7,14,20,tzinfo=timezone.utc))
    assert news[0].ticker_relevance==0.28 and news[0].ticker_sentiment_label=="Bullish"
