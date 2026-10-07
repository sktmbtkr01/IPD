from __future__ import annotations
import hashlib, json
from datetime import date, datetime, time, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from pydantic import BaseModel

def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel): value = value.model_dump(mode="python")
    if isinstance(value, dict): return {str(k): _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, (list, tuple)): return [_canonical(v) for v in value]
    if isinstance(value, datetime): return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date): return value.isoformat()
    if isinstance(value, time): return value.isoformat()
    if isinstance(value, Enum): return value.value
    if isinstance(value, Path): return value.as_posix()
    return value

def canonical_json(value: Any) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))

def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()

def calculate_snapshot_hash(snapshot: BaseModel) -> str:
    data = snapshot.model_dump(mode="python")
    data.pop("snapshot_hash", None)
    for meta in data.get("source_meta", {}).values(): meta.pop("retrieved_at", None)
    return content_hash(data)
