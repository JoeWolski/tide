from __future__ import annotations

from pathlib import Path

import pytest

from tide.core.errors import InputError
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


@pytest.mark.parametrize(
    ("config_text", "expected"),
    [
        ('[naming]\nbranch_template = "$USER/$STACK/$FEATURE/$BOGUS"\n', "$BOGUS"),
        ('[stack.ripple]\nstrategy = "rebase-ish"\n', "stack.ripple.strategy"),
        ('[dirty]\ndefault = "keep"\n', "dirty.default"),
        ('[conflict]\nmode = "halt"\n', "conflict.mode"),
        ('[collab]\nmode = "hybrid"\n', "collab.mode"),
        ('[auto_update]\nchannel = "beta"\n', "auto_update.channel"),
        ('[forge]\nprovider = "gitlab"\n', "forge.provider"),
        ('[forge.github]\ntransport = "http"\n', "forge.github.transport"),
        ('[forge.github]\nauth = "token-file"\n', "forge.github.auth"),
    ],
)
def test_load_config_rejects_invalid_values(
    tmp_path: Path,
    config_text: str,
    expected: str,
) -> None:
    repo = tmp_path / "repo"
    (repo / ".git" / "tide").mkdir(parents=True)
    (repo / ".git" / "tide" / "config.toml").write_text(config_text, encoding="utf-8")
    with pytest.raises(InputError) as exc:
        load_config(repo, env={})
    assert expected in str(exc.value)
