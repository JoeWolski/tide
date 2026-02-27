"""GitHub CLI-backed provider helpers."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass

from tide.core.errors import ForgeError, InputError
from tide.forge.base import PullRequest
from tide.git.repo import GitRepo


@dataclass(frozen=True, slots=True)
class GitHubPullRequest:
    number: int
    url: str
    head: str
    base: str
    merge_state_status: str | None = None


@dataclass(slots=True)
class GitHubProvider:
    repo: GitRepo

    def _run_gh(self, *args: str) -> str:
        proc = subprocess.run(
            ["gh", *args],
            cwd=self.repo.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            msg = proc.stderr.strip() or proc.stdout.strip() or f"gh {' '.join(args)} failed"
            raise ForgeError(msg)
        return proc.stdout

    def repo_slug(self) -> str:
        origin = self.repo.remote_url("origin")
        if origin is None:
            raise InputError("remote 'origin' is required for queue-stack mode")

        ssh_scp = re.match(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$", origin)
        if ssh_scp is not None:
            return f"{ssh_scp.group('owner')}/{ssh_scp.group('repo')}"

        ssh_url = re.match(
            r"^(?:ssh://)?git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            origin,
        )
        if ssh_url is not None:
            return f"{ssh_url.group('owner')}/{ssh_url.group('repo')}"

        https_url = re.match(
            r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
            origin,
        )
        if https_url is not None:
            return f"{https_url.group('owner')}/{https_url.group('repo')}"

        raise InputError(f"unsupported origin remote URL for GitHub mode: {origin}")

    def pr_link(self, number: int) -> str:
        return f"https://github.com/{self.repo_slug()}/pull/{number}"

    def get_open_pr_for_head(self, head: str) -> GitHubPullRequest | None:
        out = self._run_gh(
            "pr",
            "list",
            "--state",
            "open",
            "--head",
            head,
            "--json",
            "number,url,headRefName,baseRefName",
            "--repo",
            self.repo_slug(),
        )
        data = json.loads(out)
        if not isinstance(data, list):
            raise ForgeError(f"unexpected gh pr list response for head '{head}'")
        matches = [
            item
            for item in data
            if isinstance(item, dict) and str(item.get("headRefName", "")) == head
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise InputError(f"multiple open PRs found for branch '{head}'")
        item = matches[0]
        return GitHubPullRequest(
            number=int(item["number"]),
            url=str(item["url"]),
            head=str(item["headRefName"]),
            base=str(item["baseRefName"]),
        )

    def merge_state_status(self, number: int) -> str | None:
        out = self._run_gh(
            "pr",
            "view",
            str(number),
            "--json",
            "mergeStateStatus",
            "--repo",
            self.repo_slug(),
        )
        data = json.loads(out)
        if not isinstance(data, dict):
            raise ForgeError(f"unexpected gh pr view response for PR #{number}")
        value = data.get("mergeStateStatus")
        return None if value is None else str(value)

    def create_pr(self, *, head: str, base: str, title: str, body: str) -> GitHubPullRequest:
        self._run_gh(
            "pr",
            "create",
            "--head",
            head,
            "--base",
            base,
            "--title",
            title,
            "--body",
            body,
            "--repo",
            self.repo_slug(),
        )
        pr = self.get_open_pr_for_head(head)
        if pr is None:
            raise ForgeError(f"unable to resolve newly created PR for head '{head}'")
        return pr

    def enqueue_pr(self, number: int) -> None:
        # On merge-queue protected branches, auto-merge places the PR into the queue.
        self._run_gh("pr", "merge", str(number), "--auto", "--repo", self.repo_slug())

    def comment_pr(self, number: int, body: str) -> None:
        self._run_gh("pr", "comment", str(number), "--body", body, "--repo", self.repo_slug())

    def close_pr(self, number: int) -> None:
        self._run_gh("pr", "close", str(number), "--repo", self.repo_slug())

    def get_pr_for_branch_sync(self, branch: str) -> PullRequest | None:
        pr = self.get_open_pr_for_head(branch)
        if pr is None:
            return None
        return PullRequest(number=pr.number, head=pr.head, base=pr.base, title=pr.url, draft=False)

    def create_pr_sync(
        self, head: str, base: str, title: str, body: str, draft: bool
    ) -> PullRequest:
        if draft:
            raise ForgeError("draft PR creation is not supported by GitHubProvider sync adapter")
        pr = self.create_pr(head=head, base=base, title=title, body=body)
        return PullRequest(number=pr.number, head=pr.head, base=pr.base, title=title, draft=False)

    def list_prs_sync(self, branches: list[str]) -> list[PullRequest]:
        prs: list[PullRequest] = []
        for branch in branches:
            pr = self.get_open_pr_for_head(branch)
            if pr is None:
                continue
            prs.append(
                PullRequest(number=pr.number, head=pr.head, base=pr.base, title=pr.url, draft=False)
            )
        return sorted(prs, key=lambda p: p.number)
