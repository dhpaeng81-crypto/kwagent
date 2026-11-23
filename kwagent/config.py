from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Config:
    raw: dict[str, Any]
    root: Path

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def path(self, name: str) -> Path:
        p = self.root / self.raw["paths"][name]
        if name in ("cache", "models", "reports", "era5"):
            p.mkdir(parents=True, exist_ok=True)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def variables(self) -> list[str]:
        return list(self.raw["variables"].keys())

    @property
    def regions(self) -> list[str]:
        return list(self.raw["regions_active"])


def load_config(path: str | os.PathLike | None = None) -> Config:
    path = Path(path or os.environ.get("KWAGENT_CONFIG", "config.yaml")).resolve()
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Config(raw=raw, root=path.parent)
