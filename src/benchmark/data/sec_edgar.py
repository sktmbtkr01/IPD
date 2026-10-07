from __future__ import annotations
from datetime import date
from urllib.parse import quote
from benchmark.core.schemas import FundamentalFact, FundamentalsSnapshot
from benchmark.data.cache import RawCache
from benchmark.data.http import get_json

TICKERS_URL="https://www.sec.gov/files/company_tickers.json"
FACTS_URL="https://data.sec.gov/api/xbrl/companyfacts"
CONCEPTS={
 "Revenue":["RevenueFromContractWithCustomerExcludingAssessedTax","Revenues"],
 "NetIncome":["NetIncomeLoss"],"DilutedEPS":["EarningsPerShareDiluted"],
 "Assets":["Assets"],"Liabilities":["Liabilities"],
 "Cash":["CashAndCashEquivalentsAtCarryingValue"],
 "OperatingCashFlow":["NetCashProvidedByUsedInOperatingActivities"],
 "StockholdersEquity":["StockholdersEquity"]}
FORMS={"10-K","10-Q","10-K/A","10-Q/A"}

class SecConnector:
    def __init__(self,cache:RawCache,user_agent:str,get=get_json): self.cache,self.user_agent,self.get=cache,user_agent,get
    def _fetch(self,url,params,refresh=False):
        key=self.cache.request_key("sec",url,params)
        if not refresh and (cached:=self.cache.load("sec",key)): return cached
        payload=self.get(url,{"User-Agent":self.user_agent,"Accept-Encoding":"gzip, deflate"})
        return self.cache.store("sec",url,params,payload)
    def resolve_cik(self,ticker,refresh=False):
        artifact=self._fetch(TICKERS_URL,{"resource":"company_tickers"},refresh)
        for row in artifact.payload.values():
            if row.get("ticker","").upper()==ticker.upper(): return f"{int(row['cik_str']):010d}",artifact
        raise ValueError(f"SEC CIK not found for {ticker}")
    def fetch_company_facts(self,ticker,refresh=False):
        cik,tickers=self.resolve_cik(ticker,refresh)
        return self._fetch(f"{FACTS_URL}/CIK{quote(cik)}.json",{"ticker":ticker.upper(),"cik":cik},refresh),tickers
    @staticmethod
    def normalize(artifact,cutoff):
        us_gaap=artifact.payload.get("facts",{}).get("us-gaap",{}); selected=[]
        for name,candidates in CONCEPTS.items():
            eligible=[]
            for concept in candidates:
                for unit,rows in us_gaap.get(concept,{}).get("units",{}).items():
                    for row in rows:
                        try: filed=date.fromisoformat(row["filed"]); end=date.fromisoformat(row["end"])
                        except (KeyError,ValueError): continue
                        if filed<=cutoff.date() and row.get("form") in FORMS:
                            eligible.append((filed,end,concept,unit,row))
            if eligible:
                latest_filed=max(x[0] for x in eligible); latest_end=max(x[1] for x in eligible if x[0]==latest_filed)
                same_report=[x for x in eligible if x[0]==latest_filed and x[1]==latest_end]
                def preference(item):
                    row=item[4]; start=row.get("start")
                    if not start: return (2,0)
                    days=(date.fromisoformat(row["end"])-date.fromisoformat(start)).days
                    return (1, days if name=="OperatingCashFlow" else -days)
                filed,end,concept,unit,row=max(same_report,key=preference)
                start=date.fromisoformat(row["start"]) if row.get("start") else None
                selected.append(FundamentalFact(name=name,value=row.get("val"),period_start=start,period_end=end,filing_date=filed,
                  accession_id=row.get("accn"),form=row.get("form"),fiscal_year=row.get("fy"),fiscal_period=row.get("fp"),
                  frame=row.get("frame"),unit=unit,is_instant=start is None,duration_days=(end-start).days if start else None,
                  source=f"SEC XBRL us-gaap:{concept}"))
        latest=max((x.filing_date for x in selected if x.filing_date),default=None)
        return FundamentalsSnapshot(available=bool(selected),facts=tuple(selected),latest_filing_date=latest)
