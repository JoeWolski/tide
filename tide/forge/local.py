"""Deterministic local forge provider persisted in .git/tide/prs.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from tide.forge.base import PullRequest
from tide.git.repo import GitRepo


@dataclass(slots=True)
class LocalForgeProvider:
    repo: GitRepo

    @property
    def path(self) -> Path:
        return self.repo.root / ".git" / "tide" / "prs.json"

    def _load(self) -> list[PullRequest]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return []
        prs: list[PullRequest] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            try:
                prs.append(
                    PullRequest(
                        number=int(item["number"]),
                        head=str(item["head"]),
                        base=str(item["base"]),
                        title=str(item["title"]),
                        draft=bool(item.get("draft", False)),
                        mergeable=(
                            None if item.get("mergeable") is None else bool(item.get("mergeable"))
                        ),
                    )
                )
            except KeyError:
                continue
        return sorted(prs, key=lambda pr: pr.number)

    def _save(self, prs: list[PullRequest]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(pr) for pr in sorted(prs, key=lambda p: p.number)]
        self.path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")

    def list_prs_sync(self, branches: list[str]) -> list[PullRequest]:
        allowed = set(branches)
        return [pr for pr in self._load() if pr.head in allowed]

    def get_pr_for_branch_sync(self, branch: str) -> PullRequest | None:
        for pr in self._load():
            if pr.head == branch:
                return pr
        return None

    def create_pr_sync(
        self,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool,
    ) -> PullRequest:
        del body
        prs = self._load()
        next_number = max((pr.number for pr in prs), default=0) + 1
        new_pr = PullRequest(number=next_number, head=head, base=base, title=title, draft=draft)
        prs.append(new_pr)
        self._save(prs)
        return new_pr
