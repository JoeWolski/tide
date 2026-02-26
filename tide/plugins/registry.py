"""Plugin registry primitives."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class PluginRegistry:
    hooks: dict[str, list[Callable[..., object]]] = field(default_factory=dict)

    def register(self, hook: str, fn: Callable[..., object]) -> None:
        self.hooks.setdefault(hook, []).append(fn)

    def run(self, hook: str, *args: object, **kwargs: object) -> list[object]:
        return [fn(*args, **kwargs) for fn in self.hooks.get(hook, [])]
