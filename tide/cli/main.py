"""CLI entrypoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import click

from tide.config.settings import TideConfig, load_config
from tide.core.errors import ConflictError, TideError
from tide.core.models import BranchNode
from tide.core.stack import InferenceInput, StackInferer
from tide.git.repo import GitRepo
from tide.tui.render import render_json, render_status, render_tree


@dataclass(slots=True)
class CliContext:
    json_output: bool
    yes: bool
    repo: GitRepo
    config: TideConfig


def _emit_error(err: TideError, *, as_json: bool) -> None:
    if as_json:
        if isinstance(err, ConflictError):
            click.echo(json.dumps({"error": "conflict", "files": sorted(err.files)}))
        else:
            click.echo(json.dumps({"error": err.__class__.__name__.lower(), "message": str(err)}))
    else:
        click.echo(str(err), err=True)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "json_output", is_flag=True, help="Machine-readable output.")
@click.option("--yes", is_flag=True, help="Never prompt interactively.")
@click.pass_context
def main(ctx: click.Context, json_output: bool, yes: bool) -> None:
    """Tide CLI."""
    try:
        repo = GitRepo.discover(Path.cwd())
        config = load_config(repo.root)
        ctx.obj = CliContext(json_output=json_output, yes=yes, repo=repo, config=config)
    except TideError as err:
        _emit_error(err, as_json=json_output)
        raise SystemExit(err.exit_code) from err


@main.command()
@click.argument("feature")
@click.option("--stack", default="stack", show_default=True)
@click.option("--dirty", type=click.Choice(["fail", "stash", "move"]), default=None)
@click.pass_obj
def add(obj: CliContext, feature: str, stack: str, dirty: str | None) -> None:
    """Create a new branch in the active stack."""
    del dirty
    try:
        current = obj.repo.current_branch()
        branch = obj.config.branch_name(
            user="local",
            stack=stack,
            feature=feature,
            base=current,
        )
        obj.repo.run("checkout", "-b", branch)
        if obj.json_output:
            click.echo(json.dumps({"created": branch, "from": current}))
        else:
            click.echo(branch)
    except TideError as err:
        _emit_error(err, as_json=obj.json_output)
        raise SystemExit(err.exit_code) from err


@main.command()
@click.pass_obj
def show(obj: CliContext) -> None:
    """Show stack graph in tree format."""
    try:
        branches = [
            BranchNode(name=b, local=True, remote=False) for b in obj.repo.list_local_branches()
        ]
        trunk = obj.config.trunk
        edges = [(b, trunk) for b in sorted(obj.repo.list_local_branches()) if b != trunk]
        graph = StackInferer.infer(
            InferenceInput(branches=branches, pr_edges=[], remote_edges=edges, heuristic_edges=[])
        )
        if obj.json_output:
            click.echo(render_json(graph))
        else:
            click.echo(render_tree(graph, trunk=trunk))
    except TideError as err:
        _emit_error(err, as_json=obj.json_output)
        raise SystemExit(err.exit_code) from err


@main.command()
@click.pass_obj
def status(obj: CliContext) -> None:
    """Show scriptable branch list."""
    try:
        branches = obj.repo.list_local_branches()
        if obj.json_output:
            click.echo(json.dumps({"branches": sorted(branches)}))
        else:
            click.echo(render_status(branches))
    except TideError as err:
        _emit_error(err, as_json=obj.json_output)
        raise SystemExit(err.exit_code) from err


@main.command(name="up")
@click.pass_obj
def up_cmd(obj: CliContext) -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="down")
@click.pass_obj
def down_cmd(obj: CliContext) -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="goto")
@click.argument("target")
@click.pass_obj
def goto_cmd(obj: CliContext, target: str) -> None:
    del obj, target
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="ripple")
@click.pass_obj
def ripple_cmd(obj: CliContext) -> None:
    del obj
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="apply")
@click.argument("target")
@click.pass_obj
def apply_cmd(obj: CliContext, target: str) -> None:
    del obj, target
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.group(name="pr")
def pr_group() -> None:
    """PR commands."""


@pr_group.command(name="create")
@click.option("--stack", "stack_selector", required=True)
@click.option("--scope", type=click.Choice(["path", "subtree", "component"]), default="path")
@click.option("--head-pr", type=int, required=False)
def pr_create_cmd(stack_selector: str, scope: str, head_pr: int | None) -> None:
    del stack_selector, scope, head_pr
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="land")
def land_cmd() -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="checkout")
def checkout_cmd() -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="push")
def push_cmd() -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


@main.command(name="sync")
def sync_cmd() -> None:
    click.echo("not yet implemented", err=True)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
