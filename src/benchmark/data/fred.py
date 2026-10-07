from __future__ import annotations
from datetime import date
from hashlib import sha256
from urllib.parse import urlencode
from benchmark.core.schemas import MacroObservation
from benchmark.data.cache import RawCache
from benchmark.data.http import get_json

ENDPOINT="https://api.stlouisfed.org/fred/series/observations"
LABELS={"DFF":"Effective Federal Funds Rate","CPIAUCSL":"Consumer Price Index","UNRATE":"Unemployment Rate","DGS10":"10-Year Treasury Yield","T10Y2Y":"10Y-2Y Treasury Spread"}
UNITS={"DFF":"Percent","CPIAUCSL":"Index 1982-1984=100","UNRATE":"Percent","DGS10":"Percent","T10Y2Y":"Percentage points"}
class FredError(RuntimeError): pass

class FredConnector:
    def __init__(self,cache:RawCache,api_key:str,get=get_json): self.cache,self.api_key,self.get=cache,api_key,get
    def fetch_series(self,series_id:str,as_of:date,refresh=False):
        params={"series_id":series_id,"realtime_start":as_of.isoformat(),"realtime_end":as_of.isoformat(),
          "observation_end":as_of.isoformat(),"sort_order":"desc","limit":1,"file_type":"json"}
        cache_params={**params,"apikey_fingerprint":sha256(self.api_key.encode()).hexdigest()[:12]}
        key=self.cache.request_key("fred",ENDPOINT,cache_params)
        if not refresh and (cached:=self.cache.load("fred",key)): return cached
        payload=self.get(f"{ENDPOINT}?{urlencode({**params,'api_key':self.api_key})}")
        if "error_code" in payload: raise FredError(payload.get("error_message","FRED error"))
        return self.cache.store("fred",ENDPOINT,cache_params,payload)
    @staticmethod
    def normalize(artifact,series_id):
        rows=artifact.payload.get("observations",[])
        if not rows: return MacroObservation(series_id=series_id,label=LABELS.get(series_id,series_id),observation_date=date.min,value=None,units=UNITS.get(series_id))
        row=rows[0]; raw=row.get("value")
        return MacroObservation(series_id=series_id,label=LABELS.get(series_id,series_id),observation_date=date.fromisoformat(row["date"]),
          value=None if raw in (None,".") else float(raw),realtime_start=date.fromisoformat(row["realtime_start"]),
          realtime_end=date.fromisoformat(row["realtime_end"]),units=UNITS.get(series_id))
