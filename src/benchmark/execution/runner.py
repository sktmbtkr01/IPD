from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from benchmark.agents.contracts import RunContext, RunResult
from benchmark.core.schemas import MarketSnapshot
from benchmark.execution.contracts import FailedRunArtifact, WorkflowCheckpoint
from benchmark.execution.environment import capture_environment
from benchmark.execution.run_store import RunStore
from benchmark.workflows.contracts import FrameworkRunner
from benchmark.workflows.reference import ReferenceWorkflowRunner, WorkflowExecutionError


class PersistedWorkflowError(Exception):
    def __init__(
        self,
        cause: WorkflowExecutionError,
        failure_path: Path,
        checkpoint_path: Path,
    ) -> None:
        super().__init__(str(cause))
        self.error = cause.error
        self.checkpoint = cause.checkpoint
        self.failure_path = failure_path
        self.checkpoint_path = checkpoint_path


class ExecutionService:
    """Persist every success or normalized failure around a canonical runner."""

    def __init__(self, runner: FrameworkRunner | ReferenceWorkflowRunner, store: RunStore) -> None:
        self.runner = runner
        self.store = store

    async def execute(
        self,
        snapshot: MarketSnapshot,
        context: RunContext,
        checkpoint: WorkflowCheckpoint | None = None,
    ) -> RunResult:
        try:
            if checkpoint is not None and isinstance(self.runner, ReferenceWorkflowRunner):
                result = await self.runner.run_workflow(snapshot, context, checkpoint)
            elif checkpoint is not None:
                raise ValueError("this framework runner does not declare checkpoint resume support")
            else:
                result = await self.runner.run_workflow(snapshot, context)
        except WorkflowExecutionError as exc:
            checkpoint_path = self.store.save_checkpoint(exc.checkpoint)
            failure = FailedRunArtifact(
                context=context,
                error=exc.error,
                checkpoint=exc.checkpoint,
                failed_at=datetime.now(UTC),
                environment=capture_environment(),
            )
            failure_path = self.store.save_failure(failure)
            raise PersistedWorkflowError(exc, failure_path, checkpoint_path) from exc
        self.store.save_result(result)
        return result
