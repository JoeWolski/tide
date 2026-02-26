"""GitHub provider placeholders.

Concrete network implementation is intentionally minimal in this baseline.
"""

from __future__ import annotations

from tide.core.errors import ForgeError
from tide.forge.base import PullRequest


class GitHubProvider:
    async def get_pr_for_branch(self, branch: str) -> PullRequest | None:
        raise ForgeError("github provider network integration not configured")

    async def create_pr(
        self, head: str, base: str, title: str, body: str, draft: bool
    ) -> PullRequest:
        raise ForgeError("github provider network integration not configured")

    async def list_prs(self, branches: list[str]) -> list[PullRequest]:
        raise ForgeError("github provider network integration not configured")
