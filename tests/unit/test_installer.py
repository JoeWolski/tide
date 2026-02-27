from __future__ import annotations

from pathlib import Path

import pytest

from tide.core.errors import InputError
from tide.installer.manager import InstallerManager, UpdatePlan


def test_resolve_spec_for_channels(monkeypatch) -> None:
    manager = InstallerManager(
        config_dir=Path("/tmp/tide-config"),
        bin_dir=Path("/tmp/tide-bin"),
        python_executable="python3",
    )
    monkeypatch.setenv("TIDE_MASTER_SPEC", "git+https://example.invalid/repo@master")

    assert manager.resolve_spec("release", None) == "tide"
    assert (
        manager.resolve_spec("master", None)
        == "git+https://example.invalid/repo@master"
    )
    assert manager.resolve_spec("release", "local/path") == "local/path"
    with pytest.raises(InputError):
        manager.resolve_spec("off", None)


def test_should_auto_update_uses_ttl(tmp_path: Path) -> None:
    manager = InstallerManager(
        config_dir=tmp_path / "cfg",
        bin_dir=tmp_path / "bin",
        python_executable="python3",
    )
    manager.update_state(channel="release", spec="tide", now=100)
    assert manager.should_auto_update(now=120, ttl_seconds=30, force=False) is False
    assert manager.should_auto_update(now=131, ttl_seconds=30, force=False) is True
    assert manager.should_auto_update(now=101, ttl_seconds=9999, force=True) is True


def test_install_and_launcher_are_created_atomically(monkeypatch, tmp_path: Path) -> None:
    manager = InstallerManager(
        config_dir=tmp_path / "cfg",
        bin_dir=tmp_path / "bin",
        python_executable="/usr/bin/python3",
    )

    calls: list[list[str]] = []

    class Result:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def fake_run(cmd: list[str], text: bool, capture_output: bool, check: bool) -> Result:
        del text, capture_output, check
        calls.append(cmd)
        return Result()

    monkeypatch.setattr("tide.installer.manager.subprocess.run", fake_run)

    site = manager.install_or_update(
        UpdatePlan(channel="release", spec="tide", ttl_seconds=3600)
    )
    assert site.exists()
    assert site.name == "site-packages"
    assert manager.current_site_packages("release") == site
    assert calls and "--target" in calls[0]

    launcher = manager.write_launcher(channel="release")
    content = launcher.read_text(encoding="utf-8")
    assert launcher.exists()
    assert "PYTHONPATH=" in content
    assert "-m tide.cli.main" in content
