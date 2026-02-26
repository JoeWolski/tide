"""Repository transaction manager.

This implementation snapshots refs, index/worktree/untracked state, worktrees,
sparse-checkout state, and submodule state, then rolls back on failure or signal.
"""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Literal, TypeAlias

from tide.core.errors import GitError
from tide.git.repo import GitRepo, GitResult


@dataclass(slots=True)
class SubmoduleSnapshot:
    path: Path
    head: str
    had_staged_or_dirty: bool
    stash_base_count: int
    stash_marker: str


@dataclass(slots=True)
class SparseCheckoutSnapshot:
    enabled: bool
    patterns: str | None


@dataclass(slots=True)
class RepoSnapshot:
    head_ref: str | None
    head: str
    refs_path: Path
    had_staged_or_dirty: bool
    stash_base_count: int
    stash_marker: str
    worktrees: set[Path]
    sparse_checkout: SparseCheckoutSnapshot
    submodules: list[SubmoduleSnapshot]


SignalHandler: TypeAlias = signal.Handlers | int | None | Callable[[int, FrameType | None], object]


class RepoTransaction(AbstractContextManager["RepoTransaction"]):
    def __init__(self, repo: GitRepo) -> None:
        self.repo = repo
        self.snapshot: RepoSnapshot | None = None
        self._old_handlers: dict[int, SignalHandler] = {}
        self._rolled_back = False

    def __enter__(self) -> RepoTransaction:
        head_ref = self.repo.run("symbolic-ref", "-q", "HEAD", check=False).stdout.strip() or None
        head = self.repo.run("rev-parse", "HEAD").stdout.strip()
        refs_dump = self.repo.run("show-ref", check=False).stdout

        fd, refs_file = tempfile.mkstemp(prefix="tide-refs-", text=True)
        os.close(fd)
        refs_path = Path(refs_file)
        refs_path.write_text(refs_dump, encoding="utf-8")

        marker = f"tide-tx-snapshot-{uuid.uuid4().hex}"
        status = self.repo.run("status", "--porcelain").stdout
        dirty = bool(status.strip())
        stash_count = len(self.repo.run("stash", "list", check=False).stdout.splitlines())
        if dirty:
            self.repo.run("stash", "push", "-u", "-m", marker)

        self.snapshot = RepoSnapshot(
            head_ref=head_ref,
            head=head,
            refs_path=refs_path,
            had_staged_or_dirty=dirty,
            stash_base_count=stash_count,
            stash_marker=marker,
            worktrees=self._worktrees(),
            sparse_checkout=self._capture_sparse_checkout(),
            submodules=self._capture_submodules(marker=marker),
        )
        self._install_signal_handlers()
        return self

    def _install_signal_handlers(self) -> None:
        def handler(_signum: int, _frame: FrameType | None) -> None:
            self.rollback()
            raise KeyboardInterrupt("transaction interrupted; rollback executed")

        for sig in (signal.SIGINT, signal.SIGTERM):
            self._old_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, handler)

    def _restore_signal_handlers(self) -> None:
        for sig, old in self._old_handlers.items():
            signal.signal(sig, old)
        self._old_handlers.clear()

    def _run_git_in(self, cwd: Path, *args: str, check: bool = True) -> GitResult:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        result = GitResult(stdout=out.stdout, stderr=out.stderr, code=out.returncode)
        if check and out.returncode != 0:
            raise RuntimeError(out.stderr.strip() or f"git {' '.join(args)} failed in {cwd}")
        return result

    def _worktrees(self) -> set[Path]:
        out = self.repo.run("worktree", "list", "--porcelain", check=False)
        paths: set[Path] = set()
        for line in out.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            path = Path(line.removeprefix("worktree ")).resolve()
            paths.add(path)
        return paths

    def _capture_sparse_checkout(self) -> SparseCheckoutSnapshot:
        enabled = (
            self.repo.run("config", "--bool", "core.sparseCheckout", check=False)
            .stdout.strip()
            .lower()
            == "true"
        )
        path = self.repo.root / ".git" / "info" / "sparse-checkout"
        patterns = path.read_text(encoding="utf-8") if path.exists() else None
        return SparseCheckoutSnapshot(enabled=enabled, patterns=patterns)

    def _restore_sparse_checkout(self, snapshot: SparseCheckoutSnapshot) -> None:
        path = self.repo.root / ".git" / "info" / "sparse-checkout"
        if snapshot.enabled:
            self.repo.run("config", "core.sparseCheckout", "true")
        else:
            self.repo.run("config", "core.sparseCheckout", "false", check=False)

        if snapshot.patterns is None:
            path.unlink(missing_ok=True)
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.patterns, encoding="utf-8")

    def _capture_submodules(self, *, marker: str) -> list[SubmoduleSnapshot]:
        out = self.repo.run("submodule", "status", "--recursive", check=False)
        if out.code != 0:
            return []

        snapshots: list[SubmoduleSnapshot] = []
        for line in out.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) < 2:
                continue
            path = self.repo.root / parts[1]
            if not path.exists():
                continue

            head = self._run_git_in(path, "rev-parse", "HEAD", check=False).stdout.strip()
            dirty = bool(
                self._run_git_in(path, "status", "--porcelain", check=False).stdout.strip()
            )
            stash_count = len(
                self._run_git_in(path, "stash", "list", check=False).stdout.splitlines()
            )
            sub_marker = f"{marker}-sub-{parts[1].replace('/', '_')}"
            if dirty:
                self._run_git_in(path, "stash", "push", "-u", "-m", sub_marker)
            snapshots.append(
                SubmoduleSnapshot(
                    path=path,
                    head=head,
                    had_staged_or_dirty=dirty,
                    stash_base_count=stash_count,
                    stash_marker=sub_marker,
                )
            )
        return snapshots

    def _find_stash_ref(self, cwd: Path, marker: str) -> str | None:
        lines = self._run_git_in(cwd, "stash", "list", check=False).stdout.splitlines()
        for idx, line in enumerate(lines):
            if marker in line:
                return f"stash@{{{idx}}}"
        return None

    def _drop_stash_until(self, cwd: Path, target_count: int) -> None:
        lines = self._run_git_in(cwd, "stash", "list", check=False).stdout.splitlines()
        while len(lines) > target_count:
            self._run_git_in(cwd, "stash", "drop", "stash@{0}", check=False)
            lines = self._run_git_in(cwd, "stash", "list", check=False).stdout.splitlines()

    def _restore_submodules(self, snapshot: RepoSnapshot) -> None:
        for sub in snapshot.submodules:
            if not sub.path.exists():
                continue
            self._run_git_in(sub.path, "reset", "--hard", sub.head, check=False)
            self._run_git_in(sub.path, "clean", "-fd", check=False)
            if sub.had_staged_or_dirty:
                stash_ref = self._find_stash_ref(sub.path, sub.stash_marker)
                if stash_ref is not None:
                    self._run_git_in(sub.path, "stash", "apply", "--index", stash_ref, check=False)
                    self._run_git_in(sub.path, "stash", "drop", stash_ref, check=False)
            self._drop_stash_until(sub.path, sub.stash_base_count)

    def _cleanup_new_worktrees(self, snapshot: RepoSnapshot) -> None:
        current = self._worktrees()
        to_remove = sorted(path for path in current if path not in snapshot.worktrees)
        for path in to_remove:
            if path.resolve() == self.repo.root.resolve():
                continue
            self.repo.run("worktree", "remove", "--force", str(path), check=False)

    def rollback(self) -> None:
        if self._rolled_back or self.snapshot is None:
            return

        snapshot = self.snapshot
        # Force workspace to a clean baseline before ref restore.
        self.repo.run("reset", "--hard", snapshot.head)
        self.repo.run("clean", "-fd")

        self._restore_sparse_checkout(snapshot.sparse_checkout)

        lines = [
            line
            for line in snapshot.refs_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        wanted_refs = set()
        for line in lines:
            sha, ref = line.split(" ", maxsplit=1)
            wanted_refs.add(ref)
            self.repo.run("update-ref", ref, sha)

        current_refs_raw = self.repo.run("show-ref", check=False).stdout
        for line in current_refs_raw.splitlines():
            sha, ref = line.split(" ", maxsplit=1)
            del sha
            if ref.startswith("refs/heads/") and ref not in wanted_refs:
                self.repo.run("update-ref", "-d", ref)

        if snapshot.head_ref is not None:
            self.repo.run("checkout", "-q", snapshot.head_ref.removeprefix("refs/heads/"))
        else:
            self.repo.run("checkout", "-q", snapshot.head)

        self._restore_submodules(snapshot)
        self._cleanup_new_worktrees(snapshot)

        if snapshot.had_staged_or_dirty:
            stash_ref = self._find_stash_ref(self.repo.root, snapshot.stash_marker)
            if stash_ref is not None:
                self.repo.run("stash", "apply", "--index", stash_ref, check=False)
                self.repo.run("stash", "drop", stash_ref, check=False)

        self._drop_stash_until(self.repo.root, snapshot.stash_base_count)
        self._rolled_back = True

    def commit(self) -> None:
        if self.snapshot is None:
            return

        snapshot = self.snapshot
        if snapshot.had_staged_or_dirty:
            stash_ref = self._find_stash_ref(self.repo.root, snapshot.stash_marker)
            if stash_ref is not None:
                restored = self.repo.run("stash", "apply", "--index", stash_ref, check=False)
                if restored.code != 0:
                    raise GitError(
                        "failed to restore pre-transaction dirty state; "
                        f"recover with: git stash apply --index {stash_ref}"
                    )
                self.repo.run("stash", "drop", stash_ref, check=False)

        for sub in snapshot.submodules:
            if not sub.had_staged_or_dirty or not sub.path.exists():
                continue
            stash_ref = self._find_stash_ref(sub.path, sub.stash_marker)
            if stash_ref is not None:
                restored = self._run_git_in(
                    sub.path,
                    "stash",
                    "apply",
                    "--index",
                    stash_ref,
                    check=False,
                )
                if restored.code != 0:
                    raise GitError(
                        "failed to restore pre-transaction submodule dirty state; "
                        f"recover in {sub.path} with: git stash apply --index {stash_ref}"
                    )
                self._run_git_in(sub.path, "stash", "drop", stash_ref, check=False)

        self._rolled_back = True

    def __exit__(self, exc_type: object, exc: object, tb: object) -> Literal[False]:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            self._restore_signal_handlers()
            if self.snapshot is not None and self.snapshot.refs_path.exists():
                self.snapshot.refs_path.unlink(missing_ok=True)
        return False
