from __future__ import annotations

import subprocess
from pathlib import Path

from tide.core.transactions import RepoTransaction
from tide.git.repo import GitRepo


def run(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def run_ok(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


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


def test_transaction_restores_dirty_submodule_state(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    run_ok(sub, "init", "-b", "main")
    run_ok(sub, "config", "user.email", "t@example.com")
    run_ok(sub, "config", "user.name", "T")
    (sub / "mod.txt").write_text("base\n", encoding="utf-8")
    run_ok(sub, "add", "mod.txt")
    run_ok(sub, "commit", "-m", "init submodule")

    repo = tmp_path / "repo"
    repo.mkdir()
    run_ok(repo, "init", "-b", "main")
    run_ok(repo, "config", "user.email", "t@example.com")
    run_ok(repo, "config", "user.name", "T")
    (repo / "file.txt").write_text("one\n", encoding="utf-8")
    run_ok(repo, "add", "file.txt")
    run_ok(repo, "commit", "-m", "init")
    run_ok(
        repo,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        str(sub),
        "vendor/sub",
    )
    run_ok(repo, "commit", "-am", "add submodule")

    sub_worktree = repo / "vendor" / "sub"
    sub_worktree_file = sub_worktree / "mod.txt"
    sub_worktree_file.write_text("dirty-before\n", encoding="utf-8")
    before_sub_content = sub_worktree_file.read_text(encoding="utf-8")

    g = GitRepo(root=repo)
    before_head = run(repo, "rev-parse", "HEAD")
    try:
        with RepoTransaction(g):
            g.run("checkout", "-b", "feature")
            (repo / "file.txt").write_text("two\n", encoding="utf-8")
            g.run("add", "file.txt")
            g.run("commit", "-m", "change")
            sub_worktree_file.write_text("dirty-during\n", encoding="utf-8")
            raise RuntimeError("force rollback")
    except RuntimeError:
        pass

    after_head = run(repo, "rev-parse", "HEAD")
    branches = run(repo, "branch", "--format", "%(refname:short)").splitlines()
    after_sub_content = sub_worktree_file.read_text(encoding="utf-8")

    assert before_head == after_head
    assert "feature" not in branches
    assert after_sub_content == before_sub_content
