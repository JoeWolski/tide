"""Repository transaction manager.

This implementation snapshots refs, index/worktree/untracked state, and stashes and
rolls back on failure or signal.
"""

from __future__ import annotations

import os
import signal
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Literal, TypeAlias

from tide.git.repo import GitRepo


@dataclass(slots=True)
class RepoSnapshot:
    head_ref: str | None
    head: str
    refs_path: Path
    had_staged_or_dirty: bool
    stash_base_count: int
    stash_marker: str


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

        status = self.repo.run("status", "--porcelain").stdout
        dirty = bool(status.strip())
        marker = "tide-tx-snapshot"
        stash_count = len(self.repo.run("stash", "list").stdout.splitlines())

        if dirty:
            self.repo.run("stash", "push", "-u", "-m", marker)

        self.snapshot = RepoSnapshot(
            head_ref=head_ref,
            head=head,
            refs_path=refs_path,
            had_staged_or_dirty=dirty,
            stash_base_count=stash_count,
            stash_marker=marker,
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

    def rollback(self) -> None:
        if self._rolled_back or self.snapshot is None:
            return

        snapshot = self.snapshot
        # Force workspace to a clean baseline before ref restore.
        self.repo.run("reset", "--hard", snapshot.head)
        self.repo.run("clean", "-fd")

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

        current_stash_lines = self.repo.run("stash", "list").stdout.splitlines()
        while len(current_stash_lines) > snapshot.stash_base_count:
            self.repo.run("stash", "drop", "stash@{0}")
            current_stash_lines = self.repo.run("stash", "list").stdout.splitlines()

        if snapshot.had_staged_or_dirty:
            # Restore original worktree/index from transaction snapshot.
            self.repo.run("stash", "apply", "--index", "stash@{0}")
            self.repo.run("stash", "drop", "stash@{0}")

        self._rolled_back = True

    def commit(self) -> None:
        if self.snapshot is None:
            return
        if self.snapshot.had_staged_or_dirty:
            # remove saved state if operation succeeded.
            self.repo.run("stash", "drop", "stash@{0}")
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
