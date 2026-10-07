import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from benchmark.core.hashing import canonical_json, content_hash

@dataclass(frozen=True)
class RawArtifact:
    provider: str
    endpoint: str
    parameters: dict[str, Any]
    request_key: str
    retrieved_at: datetime
    payload: dict[str, Any]

class RawCache:
    def __init__(self, root: Path): self.root = root
    @staticmethod
    def request_key(provider, endpoint, parameters):
        return content_hash({"provider": provider, "endpoint": endpoint, "parameters": parameters})
    def path_for(self, provider, key): return self.root / provider / f"{key}.json"
    def load(self, provider, key):
        path = self.path_for(provider, key)
        if not path.exists(): return None
        d = json.loads(path.read_text(encoding="utf-8"))
        return RawArtifact(d["provider"], d["endpoint"], d["parameters"], d["request_key"], datetime.fromisoformat(d["retrieved_at"]), d["payload"])
    def store(self, provider, endpoint, parameters, payload, retrieved_at=None):
        key = self.request_key(provider, endpoint, parameters)
        artifact = RawArtifact(provider, endpoint, parameters, key, retrieved_at or datetime.now(timezone.utc), payload)
        path = self.path_for(provider, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical_json(artifact.__dict__) + "\n", encoding="utf-8")
        return artifact
