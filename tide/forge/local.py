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

    @property
    def land_path(self) -> Path:
        return self.repo.root / ".git" / "tide" / "land.json"

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
                        checks_summary=(
                            None
                            if item.get("checks_summary") is None
                            else str(item.get("checks_summary"))
                        ),
                        review_summary=(
                            None
                            if item.get("review_summary") is None
                            else str(item.get("review_summary"))
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

    def _load_land_state(self) -> dict[str, object]:
        if not self.land_path.exists():
            return {"submissions": [], "closures": []}
        data = json.loads(self.land_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"submissions": [], "closures": []}
        submissions = data.get("submissions")
        closures = data.get("closures")
        return {
            "submissions": submissions if isinstance(submissions, list) else [],
            "closures": closures if isinstance(closures, list) else [],
        }

    def _save_land_state(self, state: dict[str, object]) -> None:
        self.land_path.parent.mkdir(parents=True, exist_ok=True)
        self.land_path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")

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

    def submit_queue_bundle_sync(self, pr_numbers: list[int], *, provider: str) -> dict[str, object]:
        state = self._load_land_state()
        submissions = state["submissions"]
        assert isinstance(submissions, list)
        next_id = 1
        if submissions:
            prior_ids = [
                int(item["id"])
                for item in submissions
                if isinstance(item, dict) and "id" in item and str(item["id"]).isdigit()
            ]
            next_id = max(prior_ids, default=0) + 1
        submission = {
            "id": next_id,
            "provider": provider,
            "pr_numbers": sorted(pr_numbers),
            "status": "queued",
            "mode": "stack-bundle",
        }
        submissions.append(submission)
        self._save_land_state(state)
        return submission

    def close_pr_sync(self, pr_number: int, comment: str) -> None:
        state = self._load_land_state()
        closures = state["closures"]
        assert isinstance(closures, list)
        closures.append({"pr_number": pr_number, "comment": comment, "state": "closed"})
        self._save_land_state(state)
