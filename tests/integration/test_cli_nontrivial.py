from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def run(
    repo: Path,
    *args: str,
    check: bool = True,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["XDG_CONFIG_HOME"] = str(repo / ".xdg")
    if env_overrides:
        env.update(env_overrides)
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


def test_land_queue_stack_submits_one_bundle_and_closes_with_parent_child_links(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    git(repo, "remote", "add", "origin", "git@github.com:acme/tide.git")

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

    git(repo, "checkout", "-b", "feat3")
    (repo / "f.txt").write_text("feat3\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat3")
    git(repo, "config", "branch.feat3.tide-parent", "feat2")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_state = tmp_path / "fake-gh-state.json"
    fake_state.write_text(
        json.dumps(
            {
                "next_pr": 10,
                "prs": {
                    "feat1": {
                        "number": 1,
                        "url": "https://github.com/acme/tide/pull/1",
                        "head": "feat1",
                        "base": "main",
                        "mergeStateStatus": "CLEAN",
                        "closed": False,
                        "comments": [],
                    },
                    "feat2": {
                        "number": 2,
                        "url": "https://github.com/acme/tide/pull/2",
                        "head": "feat2",
                        "base": "feat1",
                        "mergeStateStatus": "CLEAN",
                        "closed": False,
                        "comments": [],
                    },
                    "feat3": {
                        "number": 3,
                        "url": "https://github.com/acme/tide/pull/3",
                        "head": "feat3",
                        "base": "feat2",
                        "mergeStateStatus": "CLEAN",
                        "closed": False,
                        "comments": [],
                    },
                },
                "merged_auto": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["TIDE_FAKE_GH_STATE"])
state = json.loads(state_path.read_text(encoding="utf-8"))
args = sys.argv[1:]

if args[:2] != ["pr", "list"] and args[:2] != ["pr", "view"] and args[:2] != ["pr", "create"] and args[:2] != ["pr", "merge"] and args[:2] != ["pr", "comment"] and args[:2] != ["pr", "close"]:
    print("unsupported gh invocation", file=sys.stderr)
    sys.exit(1)

def arg_value(flag: str) -> str | None:
    if flag not in args:
        return None
    idx = args.index(flag)
    if idx + 1 >= len(args):
        return None
    return args[idx + 1]

if args[:2] == ["pr", "list"]:
    head = arg_value("--head")
    out = []
    pr = state["prs"].get(head)
    if pr and not pr.get("closed"):
        out.append(
            {
                "number": pr["number"],
                "url": pr["url"],
                "headRefName": pr["head"],
                "baseRefName": pr["base"],
            }
        )
    print(json.dumps(out))
elif args[:2] == ["pr", "view"]:
    number = int(args[2])
    pr = next(v for v in state["prs"].values() if int(v["number"]) == number)
    print(json.dumps({"mergeStateStatus": pr["mergeStateStatus"]}))
elif args[:2] == ["pr", "create"]:
    head = arg_value("--head")
    base = arg_value("--base")
    number = int(state["next_pr"])
    state["next_pr"] = number + 1
    state["prs"][head] = {
        "number": number,
        "url": f"https://github.com/acme/tide/pull/{number}",
        "head": head,
        "base": base,
        "mergeStateStatus": "CLEAN",
        "closed": False,
        "comments": [],
    }
    print(state["prs"][head]["url"])
elif args[:2] == ["pr", "merge"]:
    state["merged_auto"].append(int(args[2]))
elif args[:2] == ["pr", "comment"]:
    number = int(args[2])
    body = arg_value("--body")
    pr = next(v for v in state["prs"].values() if int(v["number"]) == number)
    pr["comments"].append(body)
elif args[:2] == ["pr", "close"]:
    number = int(args[2])
    pr = next(v for v in state["prs"].values() if int(v["number"]) == number)
    pr["closed"] = True

state_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)

    out = run(
        repo,
        "--json",
        "land",
        "--stack",
        "feat3",
        "--scope",
        "path",
        "--mode",
        "queue-stack",
        "--queue-provider",
        "buildkite",
        env_overrides={
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "TIDE_FAKE_GH_STATE": str(fake_state),
        },
    )
    payload = json.loads(out.stdout)
    assert payload["submitted"]["provider"] == "buildkite"
    assert payload["submitted"]["bundle_pr"] == 10
    assert payload["closed"] == [1, 2, 3]

    gh_state = json.loads(fake_state.read_text(encoding="utf-8"))
    assert gh_state["merged_auto"] == [10]
    assert gh_state["prs"]["feat1"]["closed"] is True
    assert gh_state["prs"]["feat2"]["closed"] is True
    assert gh_state["prs"]["feat3"]["closed"] is True

    assert gh_state["prs"]["feat1"]["comments"] == [
        "Landed as part of stack, child: https://github.com/acme/tide/pull/2"
    ]
    assert gh_state["prs"]["feat2"]["comments"] == [
        "Landed as part of stack, child: https://github.com/acme/tide/pull/3, "
        "parent: https://github.com/acme/tide/pull/1"
    ]
    assert gh_state["prs"]["feat3"]["comments"] == [
        "Landed as part of stack, parent: https://github.com/acme/tide/pull/2"
    ]


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


def test_show_renders_pretty_tree_connectors(tmp_path: Path) -> None:
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

    git(repo, "checkout", "-b", "feat3")
    (repo / "f.txt").write_text("feat3\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat3")
    git(repo, "config", "branch.feat3.tide-parent", "feat1")

    git(repo, "checkout", "main")
    git(repo, "checkout", "-b", "feat2")
    (repo / "g.txt").write_text("feat2\n", encoding="utf-8")
    git(repo, "add", "g.txt")
    git(repo, "commit", "-m", "feat2")
    git(repo, "config", "branch.feat2.tide-parent", "main")
    git(repo, "checkout", "main")

    out = run(repo, "show")
    assert out.returncode == 0
    assert "├─ feat1 (local)" in out.stdout
    assert "│   └─ feat3 (local)" in out.stdout
    assert "└─ feat2 (local)" in out.stdout


def test_pr_create_supports_head_pr_selector_and_templates(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(
        '[forge.github]\n'
        'title_template = "[$BASE] $HEAD"\n'
        'body_template = "body: $HEAD -> $BASE"\n',
        encoding="utf-8",
    )

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
    prs_before = json.loads((repo / ".git" / "tide" / "prs.json").read_text(encoding="utf-8"))
    assert len(prs_before) == 2
    assert prs_before[0]["title"] == "[main] feat1"
    assert prs_before[1]["title"] == "[feat1] feat2"

    git(repo, "checkout", "-b", "feat3")
    (repo / "f.txt").write_text("feat3\n", encoding="utf-8")
    git(repo, "commit", "-am", "feat3")
    git(repo, "config", "branch.feat3.tide-parent", "feat2")

    out = run(
        repo,
        "--json",
        "pr",
        "create",
        "--stack",
        "ignored",
        "--scope",
        "subtree",
        "--head-pr",
        "2",
    )
    payload = json.loads(out.stdout)
    assert len(payload["created"]) == 1
    assert payload["created"][0]["head"] == "feat3"


def test_show_reports_divergence_against_upstream(tmp_path: Path) -> None:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True)

    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    git(repo, "remote", "add", "origin", str(bare))

    (repo / "f.txt").write_text("base\n", encoding="utf-8")
    git(repo, "add", "f.txt")
    git(repo, "commit", "-m", "base")
    git(repo, "push", "-u", "origin", "main")

    (repo / "f.txt").write_text("ahead\n", encoding="utf-8")
    git(repo, "commit", "-am", "ahead")

    out = run(repo, "show")
    assert out.returncode == 0
    assert "div=1/0" in out.stdout


def test_installer_status_json_outputs_shape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)

    out = run(repo, "--json", "installer", "status")
    assert out.returncode == 0
    payload = json.loads(out.stdout)
    assert payload["channel"] == "release"
    assert isinstance(payload["installed"], bool)
    assert "launcher" in payload
