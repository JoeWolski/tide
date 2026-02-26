"""CLI entrypoint."""

from __future__ import annotations

import json
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import click

from tide.config.settings import TideConfig, load_config
from tide.core.errors import ConflictError, InputError, TideError
from tide.core.service import StackService
from tide.core.transactions import RepoTransaction
from tide.forge.local import LocalForgeProvider
from tide.git.repo import GitRepo
from tide.tui.render import render_json


@dataclass(slots=True)
class CliContext:
    json_output: bool
    yes: bool
    repo: GitRepo
    config: TideConfig
    service: StackService


ConflictMode = Literal["rollback", "pause", "interactive"]


def _conflict_mode(value: str) -> ConflictMode:
    return cast(ConflictMode, value)


def _conflict_mode_for(obj: CliContext, override: str | None) -> ConflictMode:
    if override is not None:
        return _conflict_mode(override)
    value = str(obj.config.values.get("conflict", {}).get("mode", "rollback"))
    if value not in {"rollback", "pause", "interactive"}:
        raise InputError(f"unsupported conflict.mode: {value}")
    return _conflict_mode(value)


def _emit_error(err: TideError, *, as_json: bool) -> None:
    if as_json:
        if isinstance(err, ConflictError):
            click.echo(json.dumps({"error": "conflict", "files": sorted(err.files)}))
        else:
            click.echo(json.dumps({"error": err.__class__.__name__.lower(), "message": str(err)}))
    else:
        click.echo(str(err), err=True)


def _raise(err: TideError, *, as_json: bool) -> None:
    _emit_error(err, as_json=as_json)
    raise SystemExit(err.exit_code) from err


def _dirty_mode(obj: CliContext, override: str | None) -> str:
    if override is not None:
        return override
    default = obj.config.values.get("dirty", {}).get("default", "move")
    return str(default)


def _maybe_move_dirty(repo: GitRepo, target: str, mode: str, operation: str) -> None:
    dirty = repo.dirty_files()
    if not dirty:
        repo.run("checkout", target)
        return
    if mode == "fail":
        raise InputError(f"working tree is dirty; rerun with --dirty=stash|move for {operation}")

    repo.run("stash", "push", "-u", "-m", f"tide-{operation}-dirty")
    repo.run("checkout", target)
    if mode == "move":
        popped = repo.run("stash", "pop", check=False)
        if popped.code != 0:
            files = repo.conflicted_files() or dirty
            raise ConflictError(operation=operation, branches=[target], files=files)


def _run_mutating(obj: CliContext, fn: Callable[[], None], conflict_mode: ConflictMode) -> None:
    try:
        if conflict_mode == "rollback":
            with RepoTransaction(obj.repo):
                fn()
        else:
            fn()
    except ConflictError as err:
        if conflict_mode == "interactive":
            click.echo(
                "conflict detected; repository left in conflicted state for manual resolution",
                err=True,
            )
        elif conflict_mode == "pause":
            click.echo(
                "conflict detected; repository paused in conflicted state (resolve manually)",
                err=True,
            )
        _raise(err, as_json=obj.json_output)
    except TideError as err:
        _raise(err, as_json=obj.json_output)


def _render_show(obj: CliContext) -> str:
    graph = obj.service.infer_graph()
    prs = {pr.head: pr for pr in obj.service.forge.list_prs_sync(list(graph.nodes.keys()))}
    current = obj.repo.current_branch()
    if obj.json_output:
        payload = json.loads(render_json(graph))
        for node in payload["nodes"]:
            pr = prs.get(node)
            node_data = graph.nodes[node]
            payload.setdefault("node_meta", {})[node] = {
                "local": node_data.local,
                "remote": node_data.remote,
                "current": node == current,
            }
            if pr is not None:
                payload.setdefault("prs", {})[node] = {
                    "number": pr.number,
                    "base": pr.base,
                    "draft": pr.draft,
                    "mergeable": pr.mergeable,
                }
        return json.dumps(payload, sort_keys=True)

    children = graph.children()
    trunk = obj.config.trunk
    lines: list[str] = []

    def visit(node: str, prefix: str, marker: str = "") -> None:
        suffix_parts: list[str] = []
        node_data = graph.nodes[node]
        if node_data.local:
            suffix_parts.append("local")
        if node_data.remote:
            suffix_parts.append("remote")
        if node in prs:
            suffix_parts.append(f"PR#{prs[node].number}")
        if node == current:
            suffix_parts.append("current")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        lines.append(f"{prefix}{node}{marker}{suffix}")
        for edge in children.get(node, []):
            edge_marker = "*" if edge.source.value == "heuristic" else ""
            visit(edge.child, prefix + "  ", edge_marker)

    if trunk in graph.nodes:
        visit(trunk, "")
        return "\n".join(lines)
    return "\n".join(sorted(graph.nodes.keys()))


def _status_payload(obj: CliContext) -> dict[str, object]:
    graph = obj.service.infer_graph()
    prs = {pr.head: pr for pr in obj.service.forge.list_prs_sync(list(graph.nodes.keys()))}
    rows: list[dict[str, object]] = []
    for branch in sorted(graph.nodes.keys()):
        parent = obj.service.parent_of(graph, branch)
        edge = graph.parents.get(branch)
        pr = prs.get(branch)
        rows.append(
            {
                "branch": branch,
                "local": graph.nodes[branch].local,
                "remote": graph.nodes[branch].remote,
                "parent": parent,
                "source": None if edge is None else edge.source.value,
                "pr": None if pr is None else pr.number,
            }
        )
    return {"branches": rows}


def _ripple_from(obj: CliContext, root: str, conflict_mode: ConflictMode) -> None:
    strategy = str(obj.config.values.get("stack", {}).get("ripple", {}).get("strategy", "rebase"))
    graph = obj.service.infer_graph()
    todo: list[tuple[str, str]] = []

    def walk(parent: str) -> None:
        for child in obj.service.children_of(graph, parent):
            todo.append((child, parent))
            walk(child)

    walk(root)

    for child, parent in todo:
        obj.repo.run("checkout", child)
        if strategy in {"rebase", "cherry-pick"}:
            out = obj.repo.run("rebase", parent, check=False)
            if out.code != 0:
                if conflict_mode == "rollback":
                    obj.repo.run("rebase", "--abort", check=False)
                raise obj.service.conflict_from_git_failure(
                    operation="ripple",
                    branches=[child, parent],
                )
        elif strategy == "merge":
            out = obj.repo.run("merge", "--no-edit", parent, check=False)
            if out.code != 0:
                if conflict_mode == "rollback":
                    obj.repo.run("merge", "--abort", check=False)
                raise obj.service.conflict_from_git_failure(
                    operation="ripple",
                    branches=[child, parent],
                )
        else:
            raise InputError(f"unsupported ripple strategy: {strategy}")


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
@click.option("--yes", is_flag=True, help="Never prompt interactively.")
@click.pass_context
def main(ctx: click.Context, json_output: bool, yes: bool) -> None:
    """Tide CLI."""
    try:
        repo = GitRepo.discover(Path.cwd())
        config = load_config(repo.root)
        forge = LocalForgeProvider(repo)
        service = StackService(repo=repo, config=config, forge=forge)
        ctx.obj = CliContext(
            json_output=json_output,
            yes=yes,
            repo=repo,
            config=config,
            service=service,
        )
    except TideError as err:
        _raise(err, as_json=json_output)


@main.command()
@click.argument("feature")
@click.option("--stack", default="stack", show_default=True)
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.pass_obj
def add(obj: CliContext, feature: str, stack: str, dirty: str | None) -> None:
    """Create a new branch in the active stack."""

    def run() -> None:
        mode = _dirty_mode(obj, dirty)
        if mode == "fail" and obj.repo.dirty_files():
            raise InputError("working tree is dirty; rerun with --dirty=stash|move")

        current = obj.repo.current_branch()
        branch = obj.config.branch_name(
            user="local",
            stack=stack,
            feature=feature,
            base=current,
        )
        obj.repo.run("checkout", "-b", branch)
        obj.repo.set_branch_parent_hint(branch, current)
        if obj.json_output:
            click.echo(json.dumps({"created": branch, "from": current}))
        else:
            click.echo(branch)

    _run_mutating(obj, run, "rollback")


@main.command()
@click.pass_obj
def show(obj: CliContext) -> None:
    """Show stack graph in tree format."""
    try:
        click.echo(_render_show(obj))
    except TideError as err:
        _raise(err, as_json=obj.json_output)


@main.command()
@click.pass_obj
def status(obj: CliContext) -> None:
    """Show scriptable stack status."""
    try:
        payload = _status_payload(obj)
        if obj.json_output:
            click.echo(json.dumps(payload, sort_keys=True))
            return
        rows = payload["branches"]
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            location = "LR" if row["local"] and row["remote"] else "L" if row["local"] else "R"
            parent = "-" if row["parent"] is None else row["parent"]
            source = "-" if row["source"] is None else row["source"]
            pr = "-" if row["pr"] is None else row["pr"]
            click.echo(
                f"{row['branch']}\tloc={location}\tparent={parent}\tsource={source}\tpr={pr}"
            )
    except TideError as err:
        _raise(err, as_json=obj.json_output)


@main.command(name="up")
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def up_cmd(obj: CliContext, dirty: str | None, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        graph = obj.service.infer_graph()
        current = obj.repo.current_branch()
        parent = obj.service.parent_of(graph, current)
        if parent is None:
            raise InputError(f"no parent for branch '{current}'")
        _maybe_move_dirty(obj.repo, parent, _dirty_mode(obj, dirty), "up")
        if obj.json_output:
            click.echo(json.dumps({"checked_out": parent}))
        else:
            click.echo(parent)

    _run_mutating(obj, run, conflict_mode)


@main.command(name="down")
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def down_cmd(obj: CliContext, dirty: str | None, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        graph = obj.service.infer_graph()
        current = obj.repo.current_branch()
        child = obj.service.choose_single_child(graph, current)
        _maybe_move_dirty(obj.repo, child, _dirty_mode(obj, dirty), "down")
        if obj.json_output:
            click.echo(json.dumps({"checked_out": child}))
        else:
            click.echo(child)

    _run_mutating(obj, run, conflict_mode)


@main.command(name="goto")
@click.argument("target")
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def goto_cmd(obj: CliContext, target: str, dirty: str | None, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        if not obj.repo.branch_exists(target):
            raise InputError(f"unknown branch: {target}")
        _maybe_move_dirty(obj.repo, target, _dirty_mode(obj, dirty), "goto")
        if obj.json_output:
            click.echo(json.dumps({"checked_out": target}))
        else:
            click.echo(target)

    _run_mutating(obj, run, conflict_mode)


@main.command(name="ripple")
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def ripple_cmd(obj: CliContext, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        root = obj.repo.current_branch()
        _ripple_from(obj, root, conflict_mode)
        obj.repo.run("checkout", root)
        if obj.json_output:
            click.echo(json.dumps({"rippled_from": root}))
        else:
            click.echo(root)

    _run_mutating(obj, run, conflict_mode)


@main.command(name="apply")
@click.argument("target")
@click.option("--ripple/--no-ripple", default=False)
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def apply_cmd(obj: CliContext, target: str, ripple: bool, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        if not obj.repo.branch_exists(target):
            raise InputError(f"unknown target branch: {target}")
        current = obj.repo.current_branch()
        patch = obj.repo.run("diff", "--binary", f"{target}...{current}").stdout
        patch_name_out = obj.repo.run(
            "diff",
            "--name-only",
            f"{target}...{current}",
        ).stdout
        patch_files = sorted(line.strip() for line in patch_name_out.splitlines() if line.strip())
        if not patch.strip():
            raise InputError(f"no diff to apply from '{current}' to '{target}'")

        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as handle:
            handle.write(patch)
            patch_path = handle.name

        try:
            with tempfile.TemporaryDirectory(prefix="tide-apply-worktree-") as worktree_dir:
                obj.repo.run("worktree", "add", worktree_dir, target)
                try:
                    wt_repo = GitRepo(Path(worktree_dir))
                    applied = wt_repo.run("apply", "--index", patch_path, check=False)
                    if applied.code != 0:
                        files = wt_repo.conflicted_files() or patch_files
                        raise ConflictError(
                            operation="apply",
                            branches=[current, target],
                            files=files,
                        )
                    staged = wt_repo.run("diff", "--cached", "--name-only").stdout.strip()
                    if staged:
                        wt_repo.run("commit", "-m", f"apply: {current} -> {target}")
                finally:
                    obj.repo.run("worktree", "remove", "--force", worktree_dir, check=False)
            if ripple:
                start = obj.repo.current_branch()
                _ripple_from(obj, target, conflict_mode)
                obj.repo.run("checkout", start)
        finally:
            Path(patch_path).unlink(missing_ok=True)

        if obj.json_output:
            click.echo(json.dumps({"applied": {"from": current, "to": target}, "ripple": ripple}))
        else:
            click.echo(f"{current} -> {target}")

    _run_mutating(obj, run, conflict_mode)


@main.group(name="pr")
def pr_group() -> None:
    """PR commands."""


@pr_group.command(name="create")
@click.option("--stack", "stack_selector", required=True)
@click.option("--scope", type=click.Choice(["path", "subtree", "component"]), default="path")
@click.option("--head-pr", type=int, required=False)
@click.option("--draft/--ready", default=True)
@click.pass_obj
def pr_create_cmd(
    obj: CliContext,
    stack_selector: str,
    scope: str,
    head_pr: int | None,
    draft: bool,
) -> None:
    del head_pr

    def run() -> None:
        graph = obj.service.infer_graph()
        branches = obj.service.resolve_scope(graph, stack_selector, scope)
        created = obj.service.create_missing_prs(graph, branches, draft=draft)
        payload = {
            "created": [
                {"number": pr.number, "head": pr.head, "base": pr.base, "draft": pr.draft}
                for pr in created
            ]
        }
        if obj.json_output:
            click.echo(json.dumps(payload, sort_keys=True))
            return
        for pr in created:
            click.echo(f"#{pr.number} {pr.head} -> {pr.base}")

    _run_mutating(obj, run, "rollback")


@main.command(name="land")
@click.option("--stack", "stack_selector", default=None)
@click.option("--scope", type=click.Choice(["path", "subtree", "component"]), default="path")
@click.option("--mode", type=click.Choice(["squash-each", "close-non-head"]), default="squash-each")
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def land_cmd(
    obj: CliContext,
    stack_selector: str | None,
    scope: str,
    mode: str,
    conflict: str | None,
) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        graph = obj.service.infer_graph()
        selector = obj.repo.current_branch() if stack_selector is None else stack_selector
        branches = obj.service.resolve_scope(graph, selector, scope)
        trunk = obj.config.trunk
        to_land = [branch for branch in branches if branch != trunk]

        missing = obj.service.missing_prs(to_land)
        if missing:
            msg = (
                f"missing PRs for branches: {', '.join(missing)}\n"
                f"run: tide pr create --stack {selector} --scope {scope}"
            )
            raise InputError(msg)

        obj.service.ensure_mergeable(to_land)

        if mode == "close-non-head":
            if obj.json_output:
                click.echo(json.dumps({"closed": sorted(to_land)}))
            else:
                click.echo("closed non-head PRs")
            return

        ordered = [branch for branch in reversed(branches) if branch != trunk]
        obj.repo.run("checkout", trunk)
        for branch in ordered:
            merged = obj.repo.run("merge", "--squash", branch, check=False)
            if merged.code != 0:
                if conflict_mode == "rollback":
                    obj.repo.run("merge", "--abort", check=False)
                raise obj.service.conflict_from_git_failure(
                    operation="land",
                    branches=[branch, trunk],
                )
            staged = obj.repo.run("diff", "--cached", "--name-only").stdout.strip()
            if not staged:
                continue
            obj.repo.run("commit", "-m", f"land: {branch}")

        if obj.json_output:
            click.echo(json.dumps({"landed": ordered, "trunk": trunk}))
        else:
            click.echo(f"landed {len(ordered)} branches onto {trunk}")

    _run_mutating(obj, run, conflict_mode)


@main.command(name="checkout")
@click.argument("target")
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.pass_obj
def checkout_cmd(obj: CliContext, target: str, dirty: str | None) -> None:
    def run() -> None:
        if not obj.repo.branch_exists(target):
            raise InputError(f"unknown branch: {target}")
        _maybe_move_dirty(obj.repo, target, _dirty_mode(obj, dirty), "checkout")
        if obj.json_output:
            click.echo(json.dumps({"checked_out": target}))
        else:
            click.echo(target)

    _run_mutating(obj, run, "rollback")


@main.command(name="push")
@click.pass_obj
def push_cmd(obj: CliContext) -> None:
    def run() -> None:
        current = obj.repo.current_branch()
        obj.repo.run("push", "-u", "origin", current)
        if obj.json_output:
            click.echo(json.dumps({"pushed": current}))
        else:
            click.echo(current)

    _run_mutating(obj, run, "rollback")


@main.command(name="sync")
@click.option(
    "--conflict",
    type=click.Choice(["rollback", "interactive", "pause"]),
    default=None,
)
@click.pass_obj
def sync_cmd(obj: CliContext, conflict: str | None) -> None:
    conflict_mode = _conflict_mode_for(obj, conflict)

    def run() -> None:
        current = obj.repo.current_branch()
        upstream = obj.repo.run(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
            check=False,
        ).stdout.strip()
        if not upstream:
            raise InputError(f"branch '{current}' has no upstream configured")

        obj.repo.run("fetch", "origin")
        rebased = obj.repo.run("rebase", upstream, check=False)
        if rebased.code != 0:
            if conflict_mode == "rollback":
                obj.repo.run("rebase", "--abort", check=False)
            raise obj.service.conflict_from_git_failure(
                operation="sync",
                branches=[current, upstream],
            )
        if obj.json_output:
            click.echo(json.dumps({"synced": current, "upstream": upstream}))
        else:
            click.echo(current)

    _run_mutating(obj, run, conflict_mode)


if __name__ == "__main__":
    main()
