"""Test basic module functionality."""
import rsp_scratchpurger
from rsp_scratchpurger.models.config import Config


def test_import(purger_config: Config) -> None:
    p = rsp_scratchpurger.purger.Purger(config=purger_config)
    assert p is not None
