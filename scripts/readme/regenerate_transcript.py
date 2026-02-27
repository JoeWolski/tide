#!/usr/bin/env python3
"""Regenerate README CLI transcript from live `tide` commands and local Gitea."""

from __future__ import annotations

import argparse
import base64
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

START_MARKER = "<!-- tide-readme-transcript:start -->"
END_MARKER = "<!-- tide-readme-transcript:end -->"


@dataclass(frozen=True, slots=True)
class CommandResult:
    display: str
    output: str
    code: int


def _require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"required tool not found on PATH: {name}")
    return found


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args,
        cwd=None if cwd is None else str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if check and proc.returncode != 0:
        cmd = shlex.join(args)
        details = proc.stdout.strip()
        raise RuntimeError(
            f"command failed ({proc.returncode}): {cmd}\n"
            f"{details if details else '(no output)'}"
        )
    return proc


def _container_status(name: str) -> str | None:
    inspect = _run(
        ["docker", "inspect", "-f", "{{.State.Status}}", name],
        check=False,
    )
    if inspect.returncode != 0:
        return None
    status = inspect.stdout.strip()
    return status if status else None


def _wait_for_gitea(base_urls: list[str], *, timeout_seconds: int = 120) -> str:
    if not base_urls:
        raise RuntimeError("no Gitea base URLs supplied")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for base_url in base_urls:
            health_url = f"{base_url}/api/healthz"
            try:
                with urllib.request.urlopen(health_url, timeout=2) as response:
                    if 200 <= response.status < 300:
                        return base_url
            except (urllib.error.URLError, TimeoutError):
                pass
        time.sleep(1)
    joined = ", ".join(base_urls)
    raise RuntimeError(f"gitea did not become healthy within {timeout_seconds}s ({joined})")


def _api_request(
    base_url: str,
    *,
    method: str,
    path: str,
    username: str,
    password: str,
    payload: dict[str, object] | None = None,
) -> tuple[int, str]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Basic {token}",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        f"{base_url}{path}",
        method=method,
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        return err.code, body


def _replace_line(path: Path, *, old: str, new: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    updated: list[str] = []
    replaced = False
    for line in lines:
        if not replaced and line == old:
            updated.append(new)
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        raise RuntimeError(f"expected line not found in {path}: {old!r}")
    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _append(path: Path, text: str) -> None:
    path.write_text(path.read_text(encoding="utf-8") + text, encoding="utf-8")


def _git(repo: Path, *args: str, env: dict[str, str]) -> str:
    proc = _run(["git", *args], cwd=repo, env=env, check=True)
    return proc.stdout.strip()


def _run_tide(
    repo: Path,
    tide_bin: str,
    args: list[str],
    *,
    env: dict[str, str],
    expected_codes: set[int],
) -> CommandResult:
    display = shlex.join(["tide", *args])
    proc = _run([tide_bin, *args], cwd=repo, env=env, check=False)
    if proc.returncode not in expected_codes:
        details = proc.stdout.strip()
        raise RuntimeError(
            f"unexpected exit code for `{display}`: {proc.returncode} (expected {sorted(expected_codes)})\n"
            f"{details if details else '(no output)'}"
        )
    return CommandResult(display=display, output=proc.stdout, code=proc.returncode)


def _format_block(results: list[CommandResult]) -> str:
    lines = ["```bash"]
    for index, result in enumerate(results):
        if index > 0:
            lines.append("")
        lines.append(f"$ {result.display}")
        payload = result.output.rstrip("\n")
        if payload:
            lines.extend(payload.splitlines())
    lines.append("```")
    return "\n".join(lines)


def _generate_transcript(
    *,
    tide_bin: str,
    demo_repo: Path,
    env: dict[str, str],
) -> str:
    sections: list[str] = []

    def add_heading(title: str) -> None:
        sections.append(title)

    def add_paragraph(text: str) -> None:
        sections.append(textwrap.dedent(text).strip())

    def add_commands(items: list[tuple[list[str], set[int]]]) -> None:
        results = [
            _run_tide(demo_repo, tide_bin, args, env=env, expected_codes=expected)
            for args, expected in items
        ]
        sections.append(_format_block(results))

    add_heading("## Transcript Fixture (auto-generated)")
    add_paragraph(
        """
        - Remote forge: local Gitea (`tideadmin/tide-readme-demo`)
        - Trunk: `main`
        - Every command shown below is the real installed `tide` executable from `PATH`
        - Transcript regenerated by `scripts/readme/regenerate_transcript.py`
        """
    )

    add_heading("## Situation: Understand Current Stack State (`show`, `status`)")
    add_commands(
        [
            (["show"], {0}),
            (["status"], {0}),
        ]
    )

    add_heading("## Situation: Create New Stack Entries (`add`)")
    add_commands(
        [
            (["add", "api"], {0}),
            (["add", "tests"], {0}),
        ]
    )

    add_heading("## Situation: Navigate Between Parent/Child (`up`, `down`, `goto`, `checkout`)")
    add_commands(
        [
            (["up"], {0}),
            (["down"], {0, 6}),
            (["goto", "main"], {0}),
            (["checkout", "local/stack/api"], {0}),
        ]
    )

    # Seed stack history with real commits before server interaction.
    _append(demo_repo / "app.txt", "api-v1\n")
    _git(demo_repo, "add", "app.txt", env=env)
    _git(demo_repo, "commit", "-m", "api-v1", env=env)

    add_heading(
        "## Situation: Push Stack Entries To Server (`push`) And Inspect Updated State (`show`)"
    )
    add_commands([(["push"], {0})])
    _git(demo_repo, "branch", "--unset-upstream", "local/stack/api", env=env)
    _git(demo_repo, "config", "branch.local/stack/api.tide-parent", "main", env=env)
    add_paragraph("`show` immediately after server-affecting command:")
    add_commands([(["show"], {0})])

    # Make child branch diverge from parent, then publish it.
    _run_tide(
        demo_repo,
        tide_bin,
        ["checkout", "local/stack/tests"],
        env=env,
        expected_codes={0},
    )
    (demo_repo / "tests.txt").write_text("tests-v1\n", encoding="utf-8")
    _git(demo_repo, "add", "tests.txt", env=env)
    _git(demo_repo, "commit", "-m", "tests-v1", env=env)

    add_heading("### Push `local/stack/tests`")
    add_commands([(["push"], {0})])
    _git(demo_repo, "branch", "--unset-upstream", "local/stack/tests", env=env)
    _git(
        demo_repo,
        "config",
        "branch.local/stack/tests.tide-parent",
        "local/stack/api",
        env=env,
    )
    add_paragraph("`show` immediately after server-affecting command:")
    add_commands([(["show"], {0})])

    # Parent changes after child branch exists, so ripple has real work to do.
    _run_tide(
        demo_repo,
        tide_bin,
        ["checkout", "local/stack/api"],
        env=env,
        expected_codes={0},
    )
    _append(demo_repo / "app.txt", "api-v2\n")
    _git(demo_repo, "add", "app.txt", env=env)
    _git(demo_repo, "commit", "-m", "api-v2", env=env)

    add_heading("## Situation: Propagate Parent Changes Upward (`ripple`)")
    add_commands(
        [
            (["ripple"], {0}),
            (["show"], {0}),
        ]
    )

    add_heading("## Situation: Apply Current Branch Diff To Another Stack Entry (`apply`)")
    add_commands(
        [
            (["checkout", "local/stack/tests"], {0}),
            (["apply", "local/stack/api"], {0}),
            (["show"], {0}),
        ]
    )

    add_heading("## Situation: Land Fails When PRs Are Missing (`land` validation)")
    add_commands(
        [
            (["land", "--stack", "local/stack/tests", "--scope", "path"], {2}),
            (["--json", "land", "--stack", "local/stack/tests", "--scope", "path"], {2}),
        ]
    )

    add_heading("## Situation: Create Missing PRs For Stack Path (`pr create`)")
    add_commands(
        [
            (["pr", "create", "--stack", "local/stack/tests", "--scope", "path"], {0}),
            (["show"], {0}),
            (["--json", "status"], {0}),
        ]
    )

    add_heading("## Situation: Land Stack Path (`land`) Then Push Trunk (`push`)")
    add_commands(
        [
            (["land", "--stack", "local/stack/tests", "--scope", "path"], {0}),
            (["show"], {0}),
            (["push"], {0}),
            (["show"], {0}),
        ]
    )

    add_heading("## Situation: Sync Local Branch With Updated Remote (`sync`)")
    add_commands(
        [
            (["sync"], {0}),
            (["show"], {0}),
        ]
    )

    # Build a deterministic conflict for apply --conflict=pause.
    _git(demo_repo, "checkout", "main", env=env)
    _git(demo_repo, "checkout", "-b", "local/conflict", env=env)
    _replace_line(demo_repo / "app.txt", old="base", new="base-conflict-branch")
    _git(demo_repo, "add", "app.txt", env=env)
    _git(demo_repo, "commit", "-m", "conflict-branch", env=env)
    _git(demo_repo, "checkout", "main", env=env)
    _replace_line(demo_repo / "app.txt", old="base", new="base-conflict-main")
    _git(demo_repo, "add", "app.txt", env=env)
    _git(demo_repo, "commit", "-m", "conflict-main", env=env)

    add_heading("## Situation: Conflict Mode Demonstration (`--conflict=pause`)")
    add_commands(
        [
            (["checkout", "local/conflict"], {0}),
            (["apply", "main", "--conflict=pause"], {4}),
        ]
    )
    _git(demo_repo, "checkout", "main", env=env)
    _git(demo_repo, "branch", "-D", "local/conflict", env=env)

    add_heading("## Situation: Machine-Readable Graph And Non-Interactive Flags")
    add_commands(
        [
            (["checkout", "main"], {0}),
            (["--json", "show"], {0}),
            (["--yes", "--json", "status"], {0}),
        ]
    )

    return "\n\n".join(section.strip() for section in sections if section.strip()) + "\n"


def _update_readme(readme_path: Path, generated: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    start_index = text.find(START_MARKER)
    end_index = text.find(END_MARKER)
    if start_index < 0 or end_index < 0 or end_index <= start_index:
        raise RuntimeError(
            f"README markers not found or malformed: {START_MARKER!r} / {END_MARKER!r}"
        )
    start_body = start_index + len(START_MARKER)
    new_text = (
        text[:start_body]
        + "\n\n"
        + generated.rstrip()
        + "\n\n"
        + text[end_index:]
    )
    readme_path.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--readme",
        type=Path,
        default=Path("README.md"),
        help="README path to update (default: README.md)",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("/workspace/tmp/tide-readme"),
        help="Scratch workspace for local Gitea + demo repo",
    )
    parser.add_argument(
        "--gitea-image",
        default=os.environ.get("TIDE_README_GITEA_IMAGE", "gitea/gitea:1.22.6"),
        help="Docker image for local Gitea",
    )
    parser.add_argument(
        "--gitea-port",
        type=int,
        default=3300,
        help="Host port to map Gitea HTTP service to",
    )
    parser.add_argument(
        "--container-name",
        default="tide-readme-gitea",
        help="Container name for local Gitea",
    )
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Leave Gitea container running for debugging",
    )
    parser.add_argument(
        "--reuse-container",
        action="store_true",
        help="Reuse an existing named Gitea container and persisted data for faster reruns",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print generated transcript to stdout without editing README",
    )
    args = parser.parse_args()

    _require_tool("git")
    _require_tool("docker")
    tide_bin = _require_tool("tide")

    repo_root = Path.cwd()
    readme_path = args.readme if args.readme.is_absolute() else (repo_root / args.readme)
    workspace = args.workspace

    demo_repo = workspace / "demo-repo"
    gitea_data = workspace / "gitea-data"
    xdg_home = workspace / ".xdg"
    fake_home = workspace / ".home"

    if args.reuse_container:
        workspace.mkdir(parents=True, exist_ok=True)
        gitea_data.mkdir(parents=True, exist_ok=True)
        if demo_repo.exists():
            shutil.rmtree(demo_repo)
        if xdg_home.exists():
            shutil.rmtree(xdg_home)
        if fake_home.exists():
            shutil.rmtree(fake_home)
    else:
        if workspace.exists():
            shutil.rmtree(workspace)
        gitea_data.mkdir(parents=True, exist_ok=True)
    demo_repo.mkdir(parents=True, exist_ok=True)

    container = args.container_name
    username = "tideadmin"
    password = "tidepassword123"
    email = "tideadmin@example.com"
    repo_name = "tide-readme-demo"

    cleanup_needed = True
    existing_status = _container_status(container)
    if args.reuse_container:
        if existing_status is None:
            run_cmd = [
                "docker",
                "run",
                "--detach",
                "--name",
                container,
                "--publish",
                f"127.0.0.1:{args.gitea_port}:3000",
                "--volume",
                f"{gitea_data}:/data",
                "--env",
                "USER_UID=1000",
                "--env",
                "USER_GID=1000",
                "--env",
                "GITEA__security__INSTALL_LOCK=true",
                "--env",
                "GITEA__service__DISABLE_REGISTRATION=true",
                "--env",
                "GITEA__server__ROOT_URL=http://127.0.0.1:3000/",
                "--env",
                "GITEA__server__DOMAIN=127.0.0.1",
                "--env",
                "GITEA__server__HTTP_PORT=3000",
                args.gitea_image,
            ]
            _run(run_cmd, check=True)
        elif existing_status != "running":
            _run(["docker", "start", container], check=True)
    else:
        _run(["docker", "rm", "-f", container], check=False)
        run_cmd = [
            "docker",
            "run",
            "--detach",
            "--name",
            container,
            "--publish",
            f"127.0.0.1:{args.gitea_port}:3000",
            "--volume",
            f"{gitea_data}:/data",
            "--env",
            "USER_UID=1000",
            "--env",
            "USER_GID=1000",
            "--env",
            "GITEA__security__INSTALL_LOCK=true",
            "--env",
            "GITEA__service__DISABLE_REGISTRATION=true",
            "--env",
            "GITEA__server__ROOT_URL=http://127.0.0.1:3000/",
            "--env",
            "GITEA__server__DOMAIN=127.0.0.1",
            "--env",
            "GITEA__server__HTTP_PORT=3000",
            args.gitea_image,
        ]
        _run(run_cmd, check=True)
    try:
        inspect = _run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                container,
            ]
        )
        container_ip = inspect.stdout.strip()
        if not container_ip:
            raise RuntimeError("failed to resolve Gitea container IP")

        candidates = [
            f"http://127.0.0.1:{args.gitea_port}",
            f"http://{container_ip}:3000",
        ]
        base_url = _wait_for_gitea(candidates, timeout_seconds=120)
        parsed_base = urllib.parse.urlparse(base_url)
        if not parsed_base.netloc:
            raise RuntimeError(f"invalid Gitea base URL: {base_url}")
        remote_host = parsed_base.netloc

        create_user = _run(
            [
                "docker",
                "exec",
                "--user",
                "git",
                container,
                "gitea",
                "admin",
                "user",
                "create",
                "--username",
                username,
                "--password",
                password,
                "--email",
                email,
                "--admin",
                "--must-change-password=false",
            ],
            check=False,
        )
        if create_user.returncode != 0 and "already exists" not in create_user.stdout.lower():
            raise RuntimeError(
                "failed to create Gitea admin user:\n" + create_user.stdout.strip()
            )

        delete_status, delete_body = _api_request(
            base_url,
            method="DELETE",
            path=f"/api/v1/repos/{username}/{repo_name}",
            username=username,
            password=password,
            payload=None,
        )
        if delete_status not in {204, 404}:
            raise RuntimeError(
                f"failed to reset existing Gitea repo ({delete_status}): {delete_body}"
            )

        status_code, body = _api_request(
            base_url,
            method="POST",
            path="/api/v1/user/repos",
            username=username,
            password=password,
            payload={"name": repo_name, "private": False, "auto_init": False},
        )
        if status_code != 201:
            raise RuntimeError(f"failed to create Gitea repo ({status_code}): {body}")

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_AUTHOR_NAME"] = "Tide README Bot"
        env["GIT_AUTHOR_EMAIL"] = "tide-readme@example.com"
        env["GIT_COMMITTER_NAME"] = "Tide README Bot"
        env["GIT_COMMITTER_EMAIL"] = "tide-readme@example.com"
        env["XDG_CONFIG_HOME"] = str(xdg_home)
        env["HOME"] = str(fake_home)
        env["TERM"] = "dumb"

        _git(demo_repo, "init", "-b", "main", env=env)
        _git(demo_repo, "config", "user.name", env["GIT_AUTHOR_NAME"], env=env)
        _git(demo_repo, "config", "user.email", env["GIT_AUTHOR_EMAIL"], env=env)
        _git(
            demo_repo,
            "remote",
            "add",
            "origin",
            f"http://{username}:{password}@{remote_host}/{username}/{repo_name}.git",
            env=env,
        )
        (demo_repo / "app.txt").write_text("base\n", encoding="utf-8")
        _git(demo_repo, "add", "app.txt", env=env)
        _git(demo_repo, "commit", "-m", "base", env=env)
        _git(demo_repo, "push", "-u", "origin", "main", env=env)

        generated = _generate_transcript(tide_bin=tide_bin, demo_repo=demo_repo, env=env)
        if args.print_only:
            sys.stdout.write(generated)
        else:
            _update_readme(readme_path, generated)
            print(f"updated {readme_path}")

        return 0
    finally:
        if cleanup_needed and not args.keep_container:
            _run(["docker", "rm", "-f", container], check=False)


if __name__ == "__main__":
    raise SystemExit(main())
