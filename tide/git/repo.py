"""Deterministic git wrappers."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from tide.core.errors import GitError


@dataclass(slots=True)
class GitResult:
    stdout: str
    stderr: str
    code: int


@dataclass(slots=True)
class GitRepo:
    root: Path

    @classmethod
    def discover(cls, start: Path) -> GitRepo:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            text=True,
            capture_output=True,
            check=False,
        )
        if out.returncode != 0:
            raise GitError(out.stderr.strip() or "not a git repository")
        return cls(root=Path(out.stdout.strip()))

    def run(self, *args: str, check: bool = True) -> GitResult:
        out = subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        result = GitResult(stdout=out.stdout, stderr=out.stderr, code=out.returncode)
        if check and out.returncode != 0:
            raise GitError(out.stderr.strip() or f"git {' '.join(args)} failed")
        return result

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def head_commit(self, rev: str = "HEAD") -> str:
        return self.run("rev-parse", rev).stdout.strip()

    def list_local_branches(self) -> list[str]:
        out = self.run("for-each-ref", "--format=%(refname:short)", "refs/heads")
        return sorted(line.strip() for line in out.stdout.splitlines() if line.strip())

    def list_remote_branches(self) -> list[str]:
        out = self.run("for-each-ref", "--format=%(refname:short)", "refs/remotes", check=False)
        return sorted(line.strip() for line in out.stdout.splitlines() if line.strip())

    def branch_parent_hint(self, branch: str) -> str | None:
        key = f"branch.{branch}.tide-parent"
        out = self.run("config", "--get", key, check=False)
        value = out.stdout.strip()
        return value if value else None

    def set_branch_parent_hint(self, branch: str, parent: str) -> None:
        self.run("config", f"branch.{branch}.tide-parent", parent)

    def merge_base(self, a: str, b: str) -> str:
        return self.run("merge-base", a, b).stdout.strip()

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        out = self.run("merge-base", "--is-ancestor", ancestor, descendant, check=False)
        return out.code == 0

    def rev_distance(self, base: str, head: str) -> int:
        out = self.run("rev-list", "--count", f"{base}..{head}")
        return int(out.stdout.strip())

    def dirty_files(self) -> list[str]:
        out = self.run("status", "--porcelain")
        files: list[str] = []
        for line in out.stdout.splitlines():
            if not line.strip():
                continue
            files.append(line[3:])
        return sorted(files)

    def conflicted_files(self) -> list[str]:
        out = self.run("diff", "--name-only", "--diff-filter=U", check=False)
        return sorted(line.strip() for line in out.stdout.splitlines() if line.strip())

    def branch_exists(self, branch: str) -> bool:
        return self.run("show-ref", "--verify", f"refs/heads/{branch}", check=False).code == 0

    def branch_upstream(self, branch: str) -> str | None:
        out = self.run(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            f"{branch}@{{upstream}}",
            check=False,
        )
        upstream = out.stdout.strip()
        return upstream or None

    def upstream_branch_name(self, branch: str) -> str | None:
        upstream = self.branch_upstream(branch)
        if upstream is None:
            return None
        if "/" not in upstream:
            return upstream
        return upstream.split("/", maxsplit=1)[1]

    def ahead_behind(self, branch: str, upstream: str) -> tuple[int, int]:
        out = self.run("rev-list", "--left-right", "--count", f"{branch}...{upstream}")
        parts = out.stdout.strip().split()
        if len(parts) != 2:
            raise GitError(f"unexpected rev-list output for divergence: {out.stdout!r}")
        ahead = int(parts[0])
        behind = int(parts[1])
        return ahead, behind
