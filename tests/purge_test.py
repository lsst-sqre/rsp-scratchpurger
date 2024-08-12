"""Test purging functionality."""

from pathlib import Path

import pytest
import yaml
from rsp_scratchpurger.models.config import Config
from rsp_scratchpurger.models.plan import FileReason
from rsp_scratchpurger.purger import Purger
from safir.logging import LogLevel

from .util import set_age


@pytest.mark.asyncio
async def test_purge(purger_config: Config, fake_root: Path) -> None:
    set_age(fake_root / "scratch" / "large", FileReason.ATIME, "8h")
    purger = Purger(config=purger_config)
    await purger.plan()
    assert purger._plan is not None
    assert len(purger._plan.files) == 1
    victim = purger._plan.files[0].path
    assert victim.name == "large"
    assert victim.is_file()
    await purger.purge()
    assert not victim.exists()


@pytest.mark.asyncio
async def test_dry_run(purger_config: Config, fake_root: Path) -> None:
    set_age(fake_root / "scratch" / "large", FileReason.ATIME, "8h")
    purger_config.dry_run = True
    purger = Purger(config=purger_config)
    await purger.plan()
    assert purger._plan is not None
    assert len(purger._plan.files) == 1
    victim = purger._plan.files[0].path
    assert victim.name == "large"
    assert victim.is_file()
    await purger.purge()
    # It should not have been deleted.
    assert victim.exists()


@pytest.mark.asyncio
async def test_subdir(purger_config: Config, fake_root: Path) -> None:
    # Rewrite policy to purge small files in `foobar`
    # Rewrite policy doc with shorter ctime
    policy_doc = yaml.safe_load(purger_config.policy_file.read_text())
    policy_doc["directories"][1]["intervals"]["small"] = {}
    policy_doc["directories"][1]["intervals"]["small"][
        "access_interval"
    ] = "1s"
    policy_doc["directories"][1]["intervals"]["small"][
        "creation_interval"
    ] = "1s"
    policy_doc["directories"][1]["intervals"]["small"][
        "modification_interval"
    ] = "1s"
    new_policy = yaml.dump(policy_doc)
    purger_config.policy_file.write_text(new_policy)

    for fn in ("small", "medium", "large"):
        set_age(
            fake_root / "scratch" / "foobar" / fn, FileReason.MTIME, "1000w"
        )
    purger_config.logging.log_level = LogLevel.DEBUG
    purger = Purger(config=purger_config)
    await purger.plan()
    assert purger._plan is not None
    assert len(purger._plan.files) == 3
    victim = purger._plan.files[0].path.parent
    assert victim.name == "foobar"
    assert victim.is_dir()
    await purger.purge()
    assert not victim.exists()
