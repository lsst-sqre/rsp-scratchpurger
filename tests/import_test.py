"""Test basic module functionality."""
import rsp_scratchpurger


def test_import() -> None:
    p = rsp_scratchpurger.Purger()
    assert p is not None
