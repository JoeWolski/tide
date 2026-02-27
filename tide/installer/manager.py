"""Installer runtime management with atomic channel switching."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from platformdirs import user_config_dir

from tide.core.errors import InputError, InstallError


@dataclass(frozen=True, slots=True)
class UpdatePlan:
    channel: str
    spec: str
    ttl_seconds: int


@dataclass(slots=True)
class InstallerManager:
    config_dir: Path
    bin_dir: Path
    python_executable: str

    @classmethod
    def from_defaults(cls) -> InstallerManager:
        return cls(
            config_dir=Path(user_config_dir("tide")),
            bin_dir=Path.home() / ".local" / "bin",
            python_executable=sys.executable,
        )

    @property
    def installer_dir(self) -> Path:
        return self.config_dir / "installer"

    @property
    def channels_dir(self) -> Path:
        return self.installer_dir / "channels"

    @property
    def state_path(self) -> Path:
        return self.installer_dir / "state.json"

    def resolve_spec(self, channel: str, override: str | None) -> str:
        if override:
            return override
        if channel == "release":
            return "tide"
        if channel == "master":
            return os.environ.get(
                "TIDE_MASTER_SPEC",
                "git+https://github.com/JoeWolski/tide.git@master",
            )
        if channel == "off":
            raise InputError("auto_update.channel is off; pass --spec to install/update explicitly")
        raise InputError(f"unsupported install channel: {channel}")

    def should_auto_update(self, *, now: int, ttl_seconds: int, force: bool) -> bool:
        if force:
            return True
        state = self._load_state()
        last_checked = int(state.get("last_checked", 0))
        return now - last_checked >= ttl_seconds

    def current_site_packages(self, channel: str) -> Path | None:
        link = self.channels_dir / f"{channel}-current"
        if not link.exists():
            return None
        if not link.is_symlink():
            return None
        target = link.resolve()
        site = target / "site-packages"
        if not site.exists():
            return None
        return site

    def install_or_update(self, plan: UpdatePlan) -> Path:
        self.installer_dir.mkdir(parents=True, exist_ok=True)
        self.channels_dir.mkdir(parents=True, exist_ok=True)

        stamp = int(time.time())
        version_dir = self.channels_dir / f"{plan.channel}-{stamp}-{uuid4().hex[:8]}"
        site_packages = version_dir / "site-packages"
        site_packages.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.python_executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--target",
            str(site_packages),
            plan.spec,
        ]
        out = subprocess.run(cmd, text=True, capture_output=True, check=False)
        if out.returncode != 0:
            raise InstallError(out.stderr.strip() or out.stdout.strip() or "pip install failed")

        current_link = self.channels_dir / f"{plan.channel}-current"
        tmp_link = self.channels_dir / f".{plan.channel}-current-{uuid4().hex[:8]}"
        os.symlink(version_dir.name, tmp_link)
        os.replace(tmp_link, current_link)
        return current_link.resolve() / "site-packages"

    def write_launcher(self, *, channel: str, destination: Path | None = None) -> Path:
        dest = destination or (self.bin_dir / "tide")
        dest.parent.mkdir(parents=True, exist_ok=True)

        current_link = self.channels_dir / f"{channel}-current"
        if not current_link.exists():
            raise InstallError(
                f"no installed runtime for channel '{channel}'; run installer install/update first"
            )

        py = shlex.quote(self.python_executable)
        site = shlex.quote(str(current_link / "site-packages"))
        body = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f'PYTHONPATH="{site}:${{PYTHONPATH:-}}" exec {py} -m tide.cli.main "$@"\n'
        )
        tmp = dest.with_name(f".{dest.name}.{uuid4().hex[:8]}")
        tmp.write_text(body, encoding="utf-8")
        tmp.chmod(0o755)
        os.replace(tmp, dest)
        return dest

    def update_state(self, *, channel: str, spec: str, now: int | None = None) -> None:
        self.installer_dir.mkdir(parents=True, exist_ok=True)
        payload = self._load_state()
        payload.update(
            {
                "last_checked": int(time.time() if now is None else now),
                "channel": channel,
                "spec": spec,
            }
        )
        tmp = self.state_path.with_name(f".{self.state_path.name}.{uuid4().hex[:8]}")
        tmp.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def status(self, channel: str) -> dict[str, object]:
        state = self._load_state()
        site_packages = self.current_site_packages(channel)
        return {
            "channel": channel,
            "installed": site_packages is not None,
            "site_packages": None if site_packages is None else str(site_packages),
            "last_checked": int(state.get("last_checked", 0)),
            "last_channel": state.get("channel"),
            "last_spec": state.get("spec"),
            "launcher": str(self.bin_dir / "tide"),
        }

    def _load_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        if isinstance(raw, dict):
            return raw
        return {}
