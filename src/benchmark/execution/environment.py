from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
import platform

from benchmark.execution.contracts import EnvironmentMetadata


DEFAULT_PACKAGES = ("pydantic", "langgraph", "crewai", "autogen-agentchat", "boto3")


def capture_environment(packages: tuple[str, ...] = DEFAULT_PACKAGES) -> EnvironmentMetadata:
    versions: dict[str, str | None] = {}
    for package in packages:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return EnvironmentMetadata(
        python_version=platform.python_version(),
        platform=platform.platform(),
        packages=versions,
        captured_at=datetime.now(UTC),
    )
