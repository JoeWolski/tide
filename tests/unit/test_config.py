from __future__ import annotations

from pathlib import Path

from tide.config.settings import load_config


def test_repo_config_overrides_user(tmp_path: Path, monkeypatch) -> None:
    user_cfg = tmp_path / "user"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(user_cfg))

    user_dir = user_cfg / "tide"
    user_dir.mkdir(parents=True)
    (user_dir / "config.toml").write_text('[repo]\ntrunk = "main"\n', encoding="utf-8")

    repo = tmp_path / "repo"
    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(
        '[repo]\ntrunk = "develop"\n', encoding="utf-8"
    )

    cfg = load_config(repo, env={})
    assert cfg.trunk == "develop"


def test_env_overrides_repo(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(
        '[repo]\ntrunk = "develop"\n', encoding="utf-8"
    )

    monkeypatch.setenv("TIDE_TRUNK", "release")
    cfg = load_config(repo)
    assert cfg.trunk == "release"
