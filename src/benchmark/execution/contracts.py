from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from benchmark.agents.contracts import (
    LLMCallMetric,
    NormalizedError,
    RunContext,
    RunResult,
    StageMetric,
    WorkflowState,
)
from benchmark.core.schemas import FrozenModel, aware


class EnvironmentMetadata(FrozenModel):
    python_version: str
    platform: str
    packages: dict[str, str | None]
    captured_at: datetime
    _aware = field_validator("captured_at")(aware)


class WorkflowCheckpoint(FrozenModel):
    context: RunContext
    state: WorkflowState
    call_metrics: tuple[LLMCallMetric, ...] = ()
    stage_metrics: tuple[StageMetric, ...] = ()
    started_at: datetime
    elapsed_ms: float = Field(default=0, ge=0)
    resume_count: int = Field(default=0, ge=0)
    _aware = field_validator("started_at")(aware)


class RunArtifact(FrozenModel):
    schema_version: str = "1.0.0"
    result: RunResult
    environment: EnvironmentMetadata
    artifact_hash: str = ""


class FailedRunArtifact(FrozenModel):
    schema_version: str = "1.0.0"
    context: RunContext
    error: NormalizedError
    checkpoint: WorkflowCheckpoint
    failed_at: datetime
    environment: EnvironmentMetadata
    details: dict[str, Any] = Field(default_factory=dict)
    artifact_hash: str = ""
    _aware = field_validator("failed_at")(aware)
