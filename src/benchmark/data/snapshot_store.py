import json
from datetime import datetime, timezone
from pathlib import Path
from benchmark.core.hashing import calculate_snapshot_hash, canonical_json
from benchmark.core.schemas import MarketSnapshot, SnapshotManifestEntry
from benchmark.data.validators import validate_point_in_time

class SnapshotStore:
    def __init__(self, root: Path): self.root = root
    def persist(self, snapshot: MarketSnapshot, config_hash: str):
        validate_point_in_time(snapshot); digest = calculate_snapshot_hash(snapshot)
        frozen = snapshot.model_copy(update={"snapshot_hash": digest})
        relative = Path(frozen.ticker) / frozen.decision_date.isoformat() / f"{digest}.json"
        target = self.root / "snapshots" / relative; target.parent.mkdir(parents=True, exist_ok=True)
        serialized = canonical_json(frozen) + "\n"
        # retrieved_at is intentionally excluded from content identity. If the
        # same content already exists, preserve the first immutable artifact.
        if not target.exists():
            target.write_text(serialized, encoding="utf-8")
        entry = SnapshotManifestEntry(snapshot_hash=digest, ticker=frozen.ticker, decision_date=frozen.decision_date,
          information_cutoff=frozen.information_cutoff, schema_version=frozen.schema_version, config_hash=config_hash,
          relative_path=relative.as_posix(), validation_status="VALID", created_at=datetime.now(timezone.utc))
        manifest = self.root / "manifests" / "snapshots.jsonl"; manifest.parent.mkdir(parents=True, exist_ok=True)
        existing = {(json.loads(x)["snapshot_hash"],json.loads(x)["config_hash"]) for x in manifest.read_text(encoding="utf-8").splitlines()} if manifest.exists() else set()
        if (digest,config_hash) not in existing:
            with manifest.open("a", encoding="utf-8") as handle: handle.write(canonical_json(entry) + "\n")
        return frozen, target
