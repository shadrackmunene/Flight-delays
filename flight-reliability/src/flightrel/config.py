"""Configuration loading."""
from __future__ import annotations

import os
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | str | None = None) -> dict:
    """Load config.yaml and resolve paths against the project root."""
    path = Path(path) if path else PROJECT_ROOT / "config.yaml"
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    env_raw = os.environ.get("FLIGHTREL_RAW_DIR")
    if env_raw:
        cfg["paths"]["raw_dir"] = env_raw

    for key, value in cfg["paths"].items():
        p = Path(value)
        cfg["paths"][key] = p if p.is_absolute() else PROJECT_ROOT / p
    return cfg
