from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["XDG_CONFIG_HOME"] = str(repo / ".xdg")
    return subprocess.run(
        ["python3", "-m", "tide.cli.main", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=check,
        env=env,
    )


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def init_repo(path: Path) -> None:
    git(path, "init", "-b", "main")
    git(path, "config", "user.email", "t@example.com")
    git(path, "config", "user.name", "T")


def test_land_fails_with_missing_prs_and_fix_command(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "feat1")
    (repo / "f.txt").write_text("feat1\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat1")
    git(repo, "config", "branch.feat1.tide-parent", "main")

    git(repo, "checkout", "-b", "feat2")
    (repo / "f.txt").write_text("feat2\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat2")
    git(repo, "config", "branch.feat2.tide-parent", "feat1")

    out = run(repo, "land", "--stack", "feat2", "--scope", "path", check=False)
    assert out.returncode == 2
    assert "missing PRs for branches: feat1, feat2" in out.stderr
    assert "run: tide pr create --stack feat2 --scope path" in out.stderr


def test_apply_conflict_returns_json_and_rolls_back(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / "f.txt").write_text("line\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "feat")
    (repo / "f.txt").write_text("line feat\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat change")

    git(repo, "checkout", "main")
    (repo / "f.txt").write_text("line main\n", encoding="utf-8")
    git(repo, "commit", "-am", "main change")

    git(repo, "checkout", "feat")
    before = git(repo, "rev-parse", "HEAD")

    out = run(repo, "--json", "apply", "main", check=False)
    assert out.returncode == 4
    payload = json.loads(out.stdout)
    assert payload["error"] == "conflict"
    assert "f.txt" in payload["files"]

    after = git(repo, "rev-parse", "HEAD")
    assert before == after
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feat"
    assert (repo / "f.txt").read_text(encoding="utf-8") == "line feat\n"


def test_status_json_is_deterministic(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "b")
    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "a")

    first = run(repo, "--json", "status")
    second = run(repo, "--json", "status")
    assert first.stdout == second.stdout


def test_ripple_conflict_pause_keeps_repo_in_conflicted_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / "f.txt").write_text("line\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "feat1")
    (repo / "f.txt").write_text("line feat1\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat1")
    git(repo, "config", "branch.feat1.tide-parent", "main")

    git(repo, "checkout", "-b", "feat2")
    (repo / "f.txt").write_text("line feat2\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat2")
    git(repo, "config", "branch.feat2.tide-parent", "feat1")

    git(repo, "checkout", "main")
    (repo / "f.txt").write_text("line main\n", encoding="utf-8")
    git(repo, "commit", "-am", "main")

    out = run(repo, "ripple", "--conflict", "pause", check=False)
    assert out.returncode == 4
    assert "conflict detected; repository paused in conflicted state" in out.stderr
    assert (repo / ".git" / "rebase-merge").exists()
    status = git(repo, "status", "--porcelain")
    assert "UU f.txt" in status
