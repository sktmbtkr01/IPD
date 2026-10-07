from __future__ import annotations
import os
from pathlib import Path

def load_dotenv(path: Path = Path(".env")) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""
    if not path.exists(): return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value: raise RuntimeError(f"required environment variable is missing: {name}")
    return value
