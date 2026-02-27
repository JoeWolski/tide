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


def test_apply_success_uses_worktree_and_commits_target(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "feat")
    (repo / "f.txt").write_text("feat\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat change")

    feat_before = git(repo, "rev-parse", "feat")
    main_before = git(repo, "rev-parse", "main")

    out = run(repo, "apply", "main")
    assert out.returncode == 0
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "feat"

    feat_after = git(repo, "rev-parse", "feat")
    main_after = git(repo, "rev-parse", "main")
    assert feat_after == feat_before
    assert main_after != main_before
    assert git(repo, "show", "main:f.txt") == "feat"

    worktrees = git(repo, "worktree", "list", "--porcelain")
    assert worktrees.count("worktree ") == 1


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


def test_default_conflict_mode_comes_from_config(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(
        '[conflict]\nmode = "pause"\n',
        encoding="utf-8",
    )

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

    out = run(repo, "ripple", check=False)
    assert out.returncode == 4
    assert "repository paused in conflicted state" in out.stderr


def test_ripple_cherry_pick_strategy_preserves_child_commit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(
        "[stack.ripple]\nstrategy = \"cherry-pick\"\n",
        encoding="utf-8",
    )

    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "base.txt")
    git(repo, "commit", "-m", "base")

    git(repo, "checkout", "-b", "feat1")
    (repo / "base.txt").write_text("feat1-a\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat1 a")
    git(repo, "config", "branch.feat1.tide-parent", "main")

    git(repo, "checkout", "-b", "feat2")
    (repo / "child.txt").write_text("feat2\n", encoding="utf-8")
    git(repo, "add", "child.txt")
    git(repo, "commit", "-m", "feat2")
    git(repo, "config", "branch.feat2.tide-parent", "feat1")
    feat2_before = git(repo, "rev-parse", "feat2")

    git(repo, "checkout", "feat1")
    (repo / "base.txt").write_text("feat1-b\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat1 b")

    out = run(repo, "ripple")
    assert out.returncode == 0

    # Cherry-pick mode should retain original child commits and append copied commits.
    is_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", feat2_before, "feat2"],
        cwd=repo,
        check=False,
    )
    assert is_ancestor.returncode == 0
    assert git(repo, "show", "-s", "--format=%s", "feat2") == "feat1 b"


def test_land_close_non_head_only_reports_non_head_branches(tmp_path: Path) -> None:
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

    run(repo, "pr", "create", "--stack", "feat2", "--scope", "path")
    out = run(
        repo,
        "--json",
        "land",
        "--stack",
        "feat2",
        "--scope",
        "path",
        "--mode",
        "close-non-head",
    )
    payload = json.loads(out.stdout)
    assert payload["head"] == "feat2"
    assert payload["closed"] == ["feat1"]


def test_show_includes_disconnected_components(tmp_path: Path) -> None:
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

    git(repo, "checkout", "main")
    git(repo, "checkout", "--orphan", "lonely")
    git(repo, "rm", "-rf", ".")
    (repo / "solo.txt").write_text("solo\n", encoding="utf-8")
    git(repo, "add", "solo.txt")
    git(repo, "commit", "-m", "lonely")

    out = run(repo, "show")
    assert out.returncode == 0
    rendered = out.stdout.strip()
    assert "main" in rendered
    assert "feat1" in rendered
    assert "lonely" in rendered
