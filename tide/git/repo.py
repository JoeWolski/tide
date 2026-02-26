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
        cmd = ["git", *args]
        out = subprocess.run(cmd, cwd=self.root, text=True, capture_output=True, check=False)
        result = GitResult(stdout=out.stdout, stderr=out.stderr, code=out.returncode)
        if check and out.returncode != 0:
            raise GitError(out.stderr.strip() or f"git {' '.join(args)} failed")
        return result

    def current_branch(self) -> str:
        return self.run("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def list_local_branches(self) -> list[str]:
        out = self.run("for-each-ref", "--format=%(refname:short)", "refs/heads")
        return sorted([line.strip() for line in out.stdout.splitlines() if line.strip()])

    def merge_base(self, a: str, b: str) -> str:
        return self.run("merge-base", a, b).stdout.strip()
