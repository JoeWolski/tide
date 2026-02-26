"""Simple commit-keyed cache helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class CommitCache:
    root: Path

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            return loaded
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path_for(key).write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
