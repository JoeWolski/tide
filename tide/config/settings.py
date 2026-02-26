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

    return TideConfig(values=values)
