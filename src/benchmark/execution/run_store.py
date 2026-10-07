from __future__ import annotations

import json
from pathlib import Path
import re
from typing import TypeVar

from pydantic import BaseModel

from benchmark.agents.contracts import RunResult
from benchmark.core.hashing import canonical_json, content_hash
from benchmark.execution.contracts import FailedRunArtifact, RunArtifact, WorkflowCheckpoint
from benchmark.execution.environment import capture_environment


SAFE_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
ArtifactT = TypeVar("ArtifactT", bound=BaseModel)


class RunStore:
    """Immutable JSON artifact store with collision detection and safe paths."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def save_result(self, result: RunResult) -> Path:
        path = self._run_directory(result.context) / "result.json"
        if path.exists():
            existing = self._load(path, RunArtifact)
            if existing.result != result:
                raise FileExistsError(f"immutable artifact collision: {path}")
            return path
        environment = capture_environment()
        provisional = RunArtifact(result=result, environment=environment)
        artifact = provisional.model_copy(update={"artifact_hash": content_hash(provisional)})
        self._write_immutable(path, artifact)
        return path

    def load_result(self, experiment_id: str, framework: str, run_id: str) -> RunArtifact:
        return self._load(self._directory(experiment_id, framework, run_id) / "result.json", RunArtifact)

    def save_failure(self, artifact: FailedRunArtifact) -> Path:
        provisional = artifact.model_copy(update={"artifact_hash": ""})
        frozen = provisional.model_copy(update={"artifact_hash": content_hash(provisional)})
        path = self._run_directory(artifact.context) / "failure.json"
        self._write_immutable(path, frozen)
        return path

    def load_failure(self, experiment_id: str, framework: str, run_id: str) -> FailedRunArtifact:
        return self._load(self._directory(experiment_id, framework, run_id) / "failure.json", FailedRunArtifact)

    def save_checkpoint(self, checkpoint: WorkflowCheckpoint) -> Path:
        digest = content_hash(checkpoint)
        path = self._run_directory(checkpoint.context) / "checkpoints" / f"{digest}.json"
        self._write_immutable(path, checkpoint)
        return path

    def load_checkpoint(
        self, experiment_id: str, framework: str, run_id: str, checkpoint_hash: str
    ) -> WorkflowCheckpoint:
        if not re.fullmatch(r"[0-9a-f]{64}", checkpoint_hash):
            raise ValueError("checkpoint_hash must be a lowercase SHA-256 digest")
        path = self._directory(experiment_id, framework, run_id) / "checkpoints" / f"{checkpoint_hash}.json"
        return self._load(path, WorkflowCheckpoint)

    def _run_directory(self, context) -> Path:
        return self._directory(context.experiment_id, context.framework.value, context.run_id)

    def _directory(self, experiment_id: str, framework: str, run_id: str) -> Path:
        parts = tuple(self._safe_identifier(value) for value in (experiment_id, framework, run_id))
        path = (self.root / parts[0] / parts[1] / parts[2]).resolve()
        if self.root not in path.parents:
            raise ValueError("run path escapes store root")
        return path

    @staticmethod
    def _safe_identifier(value: str) -> str:
        if SAFE_IDENTIFIER.fullmatch(value) is None:
            raise ValueError(f"unsafe run-store identifier: {value!r}")
        return value

    @staticmethod
    def _write_immutable(path: Path, value: BaseModel) -> None:
        serialized = canonical_json(value) + "\n"
        if path.exists():
            if path.read_text(encoding="utf-8") != serialized:
                raise FileExistsError(f"immutable artifact collision: {path}")
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _load(path: Path, model: type[ArtifactT]) -> ArtifactT:
        payload = json.loads(path.read_text(encoding="utf-8"))
        loaded = model.model_validate(payload)
        if hasattr(loaded, "artifact_hash"):
            expected = loaded.artifact_hash
            unhashed = loaded.model_copy(update={"artifact_hash": ""})
            if expected != content_hash(unhashed):
                raise ValueError(f"artifact integrity check failed: {path}")
        return loaded
