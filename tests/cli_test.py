"""Test the CLI."""

import subprocess


def test_backup_cli() -> None:
    cp = subprocess.run("purge_backups", check=False)
    assert cp.returncode == 2    # It won't have the arguments
