import gzip, json, time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

def get_json(url: str, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers=headers or {"User-Agent": "IPD-input-benchmark/0.1"})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                body=response.read()
                if response.headers.get("Content-Encoding","").lower()=="gzip": body=gzip.decompress(body)
                return json.loads(body.decode("utf-8"))
        except HTTPError as error:
            if error.code not in (429,500,502,503,504) or attempt==2: raise
            time.sleep(2**attempt)
    raise RuntimeError("HTTP retry loop exhausted")
