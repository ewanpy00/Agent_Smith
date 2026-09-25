"""Loading of JSON configuration files into Pydantic models."""
from __future__ import annotations

from pathlib import Path

from models import SandboxConfig


def load_sandbox_config(path: str | Path | None = None) -> SandboxConfig:
    """Load a SandboxConfig from a JSON file; without a path use the model defaults."""
    if path is None:
        return SandboxConfig()
    return SandboxConfig.model_validate_json(Path(path).read_text())
