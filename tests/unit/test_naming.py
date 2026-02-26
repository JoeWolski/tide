from datetime import UTC, datetime

import pytest

from tide.config.settings import DEFAULTS, TideConfig, load_config
from tide.core.errors import InputError


def test_branch_naming_slugifies() -> None:
    cfg = TideConfig(values=DEFAULTS)
    out = cfg.branch_name(
        user="Joe User",
        stack="Payments API",
        feature="Feature: Add /Thing",
        at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert out == "joe-user/payments-api/feature-add-/thing"


def test_load_config_rejects_missing_feature(tmp_path) -> None:
    git = tmp_path / ".git" / "tide"
    git.mkdir(parents=True)
    (git / "config.toml").write_text(
        '[naming]\nbranch_template = "$USER/$STACK"\n',
        encoding="utf-8",
    )
    with pytest.raises(InputError):
        load_config(tmp_path, env={})
