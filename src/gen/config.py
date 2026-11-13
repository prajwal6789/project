"""Configuration loading and scale resolution."""

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]


def load_yaml(name: str) -> dict[str, Any]:
    with (ROOT / "config" / name).open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def resolve_scale(scale: str, seed: int | None = None) -> dict[str, Any]:
    config = load_yaml("scale.yaml")
    if scale not in config["scales"]:
        raise ValueError(f"unknown scale: {scale}")
    result = {**config, **config["scales"][scale], "scale": scale}
    if seed is not None:
        result["seed"] = seed
    return result
