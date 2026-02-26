from __future__ import annotations

import subprocess
from pathlib import Path

from tide.core.transactions import RepoTransaction
from tide.git.repo import GitRepo


def run(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def test_transaction_restores_worktree_and_refs(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run(repo, "init", "-b", "main")
    run(repo, "config", "user.email", "t@example.com")
    run(repo, "config", "user.name", "T")
    (repo / "file.txt").write_text("one\n", encoding="utf-8")
    run(repo, "add", "file.txt")
    run(repo, "commit", "-m", "init")

    g = GitRepo(root=repo)
    before = run(repo, "rev-parse", "HEAD")
    try:
        with RepoTransaction(g):
            g.run("checkout", "-b", "feature")
            (repo / "file.txt").write_text("two\n", encoding="utf-8")
            g.run("add", "file.txt")
            g.run("commit", "-m", "change")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    after = run(repo, "rev-parse", "HEAD")
    branches = run(repo, "branch", "--format", "%(refname:short)").splitlines()
    content = (repo / "file.txt").read_text(encoding="utf-8")

    assert before == after
    assert "feature" not in branches
    assert content == "one\n"
