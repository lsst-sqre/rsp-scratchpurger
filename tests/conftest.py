"""Pytest configuration and fixtures."""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml
from rsp_scratchpurger.models.config import Config
from rsp_scratchpurger.models.v1.policy import Policy


@pytest.fixture
def purger_config() -> Iterator[Config]:
    policy_file = Path(__file__).parent / "support" / "policy.yaml"
    policy_doc = yaml.safe_load(policy_file.read_text())
    policy = Policy.model_validate(policy_doc)
    config_file = Path(__file__).parent / "support" / "config.yaml"
    config_doc = yaml.safe_load(config_file.read_text())
    config = Config.model_validate(config_doc)

    with TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        scratch_dir = temp_dir / "scratch"
        scratch_foobar = scratch_dir / "foobar"
        scratch_foobar.mkdir(parents=True)

        policy.directories[0].path = scratch_dir
        policy.directories[1].path = scratch_foobar

        new_policy_dict = policy.to_dict()
        new_policy_doc = yaml.dump(new_policy_dict)

        new_policy_file = temp_dir / "policy.yaml"

        new_policy_file.write_text(new_policy_doc)

        config = Config()
        config.policy_file = new_policy_file

        yield config
