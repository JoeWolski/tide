"""Forge abstraction layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class PullRequest:
    number: int
    head: str
    base: str
    title: str
    draft: bool
    mergeable: bool | None = None


class ForgeTransport(Protocol):
    async def query(self, query: str, variables: dict[str, object]) -> dict[str, object]: ...


class ForgeProvider(Protocol):
    async def get_pr_for_branch(self, branch: str) -> PullRequest | None: ...

    async def create_pr(
        self, head: str, base: str, title: str, body: str, draft: bool
    ) -> PullRequest: ...

    async def list_prs(self, branches: list[str]) -> list[PullRequest]: ...
