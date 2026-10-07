from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from benchmark.agents.contracts import (
    AnalystReport,
    FinalDecision,
    ResearchArgument,
    ResearchManagerReport,
    RiskReport,
    RunContext,
    RunMetrics,
    RunResult,
    StageMetric,
    TraderPlan,
    WorkflowState,
)
from benchmark.agents.prompt_registry import PromptRegistry
from benchmark.core.hashing import canonical_json, content_hash
from benchmark.core.schemas import MarketSnapshot
from benchmark.execution.contracts import FailedRunArtifact, RunArtifact, WorkflowCheckpoint
from benchmark.workflows.contracts import CANONICAL_STAGES, PARALLEL_GROUPS, STAGE_DEPENDENCIES


FOUNDATION_SCHEMAS: tuple[type[BaseModel], ...] = (
    MarketSnapshot,
    AnalystReport,
    ResearchArgument,
    ResearchManagerReport,
    TraderPlan,
    RiskReport,
    FinalDecision,
    RunContext,
    WorkflowState,
    StageMetric,
    RunMetrics,
    RunResult,
    WorkflowCheckpoint,
    RunArtifact,
    FailedRunArtifact,
)


def build_foundation_manifest(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    prompts = PromptRegistry(project_root / "src" / "benchmark" / "agents" / "prompts")
    prompt_specs = prompts.load_all()
    manifest = {
        "manifest_version": "1.0.0",
        "schema_hashes": {
            schema.__name__: content_hash(schema.model_json_schema()) for schema in FOUNDATION_SCHEMAS
        },
        "prompt_versions": {stage: spec.version for stage, spec in prompt_specs.items()},
        "prompt_hashes": {stage: spec.sha256 for stage, spec in prompt_specs.items()},
        "prompt_bundle_hash": prompts.bundle_hash(),
        "workflow_hash": content_hash(
            {
                "stages": CANONICAL_STAGES,
                "dependencies": STAGE_DEPENDENCIES,
                "parallel_groups": PARALLEL_GROUPS,
            }
        ),
        "config_hashes": {
            name: content_hash(json.loads((project_root / "configs" / name).read_text(encoding="utf-8")))
            for name in ("data.json", "experiment.json", "snapshot_manifest.json")
        },
    }
    return {**manifest, "foundation_hash": content_hash(manifest)}


def verify_foundation_manifest(project_root: Path) -> None:
    path = project_root / "configs" / "foundation_manifest.json"
    expected = json.loads(path.read_text(encoding="utf-8"))
    actual = build_foundation_manifest(project_root)
    if expected != actual:
        raise ValueError("foundation manifest is stale; intentionally regenerate it after reviewing changes")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify the frozen benchmark foundation manifest")
    parser.add_argument("command", choices=("show", "verify"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.command == "verify":
        verify_foundation_manifest(args.project_root)
        print("foundation manifest verified")
    else:
        print(canonical_json(build_foundation_manifest(args.project_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
