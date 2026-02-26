"""Config loading and naming semantics."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

from tide.core.errors import InputError

DEFAULTS: dict[str, Any] = {
    "repo": {"trunk": "main"},
    "naming": {"branch_template": "$USER/$STACK/$FEATURE"},
    "stack": {"ripple": {"strategy": "rebase"}},
    "dirty": {"default": "move"},
    "conflict": {"mode": "rollback"},
    "forge": {
        "provider": "github",
        "github": {"transport": "graphql", "auth": "gh"},
    },
    "collab": {"mode": "fork"},
    "auto_update": {"channel": "release", "ttl_seconds": 3600},
}

TOKEN_RE = re.compile(r"\$(USER|STACK|FEATURE|DATE|N|BASE)")
TOKEN_ANY_RE = re.compile(r"\$([A-Z][A-Z0-9_]*)")
INVALID_REF_RE = re.compile(r"[~^:?*\[\]\\]|\.\.|//|@$|\.$")


@dataclass(frozen=True, slots=True)
class TideConfig:
    values: dict[str, Any]

    @property
    def branch_template(self) -> str:
        return str(self.values["naming"]["branch_template"])

    @property
    def trunk(self) -> str:
        return str(self.values["repo"]["trunk"])

    def branch_name(
        self,
        *,
        user: str,
        stack: str,
        feature: str,
        n: int = 1,
        base: str = "",
        at: datetime | None = None,
    ) -> str:
        if at is None:
            at = datetime.now(tz=UTC)
        mapping = {
            "USER": user,
            "STACK": stack,
            "FEATURE": feature,
            "DATE": at.strftime("%Y%m%d"),
            "N": str(n),
            "BASE": base,
        }

        def repl(match: re.Match[str]) -> str:
            return mapping[match.group(1)]

        rendered = TOKEN_RE.sub(repl, self.branch_template)
        return slugify_ref(rendered)


def slugify_ref(value: str) -> str:
    cleaned = re.sub(r"\s+", "-", value.strip().lower())
    cleaned = re.sub(r"[^a-z0-9/_\-.]", "-", cleaned)
    cleaned = re.sub(r"-+", "-", cleaned)
    cleaned = re.sub(r"/+", "/", cleaned)
    cleaned = cleaned.strip("/.")
    if not cleaned or INVALID_REF_RE.search(cleaned):
        raise InputError(f"invalid branch name after slugification: {value!r}")
    return cleaned


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8"))


def load_config(repo_root: Path, *, env: dict[str, str] | None = None) -> TideConfig:
    env_map = os.environ if env is None else env
    user_path = Path(user_config_dir("tide")) / "config.toml"
    repo_path = repo_root / ".git" / "tide" / "config.toml"

    values = _deep_merge(DEFAULTS, _read_toml(user_path))
    values = _deep_merge(values, _read_toml(repo_path))

    if "TIDE_TRUNK" in env_map:
        values = _deep_merge(values, {"repo": {"trunk": env_map["TIDE_TRUNK"]}})

    template = str(values["naming"]["branch_template"])
    if "$FEATURE" not in template:
        raise InputError("naming.branch_template must include $FEATURE")
    supported_tokens = {"USER", "STACK", "FEATURE", "DATE", "N", "BASE"}
    unknown_tokens = sorted(
        token for token in TOKEN_ANY_RE.findall(template) if token not in supported_tokens
    )
    if unknown_tokens:
        raise InputError(
            "naming.branch_template contains unsupported token(s): "
            + ", ".join(f"${token}" for token in unknown_tokens)
        )

    ripple = str(values.get("stack", {}).get("ripple", {}).get("strategy", "rebase"))
    if ripple not in {"rebase", "merge", "cherry-pick"}:
        raise InputError(f"stack.ripple.strategy must be rebase|merge|cherry-pick, got: {ripple}")

    dirty_default = str(values.get("dirty", {}).get("default", "move"))
    if dirty_default not in {"fail", "stash", "move"}:
        raise InputError(f"dirty.default must be fail|stash|move, got: {dirty_default}")

    conflict_mode = str(values.get("conflict", {}).get("mode", "rollback"))
    if conflict_mode not in {"rollback", "interactive", "pause"}:
        raise InputError(f"conflict.mode must be rollback|interactive|pause, got: {conflict_mode}")

    collab_mode = str(values.get("collab", {}).get("mode", "fork"))
    if collab_mode not in {"fork", "direct"}:
        raise InputError(f"collab.mode must be fork|direct, got: {collab_mode}")

    auto_update_channel = str(values.get("auto_update", {}).get("channel", "release"))
    if auto_update_channel not in {"release", "master", "off"}:
        raise InputError(
            "auto_update.channel must be release|master|off, "
            f"got: {auto_update_channel}"
        )

    forge_provider = str(values.get("forge", {}).get("provider", "github"))
    if forge_provider != "github":
        raise InputError(f"forge.provider must be github, got: {forge_provider}")

    forge_github = values.get("forge", {}).get("github", {})
    transport = str(forge_github.get("transport", "graphql"))
    if transport not in {"graphql", "rest"}:
        raise InputError(f"forge.github.transport must be graphql|rest, got: {transport}")

    auth = str(forge_github.get("auth", "gh"))
    if auth not in {"gh", "env", "keyring", "manual"}:
        raise InputError(f"forge.github.auth must be gh|env|keyring|manual, got: {auth}")

    return TideConfig(values=values)
