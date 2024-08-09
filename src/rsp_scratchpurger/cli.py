"""Command-line interface for Google Filestore tools."""
import argparse
import asyncio
import os
from pathlib import Path

from .purger import Purger
from .constants import POLICY_FILE, ENV_PREFIX


def _add_options() -> argparse.ArgumentParser:
    """Add options applicable to any filestore tool."""
    parser = argparse.ArgumentParser()    
    parser.add_argument(
        "-f",
        "--file",
        "--policy-file",
        help="Policy file for purger",
        default=os.environ.get(f"{ENV_PREFIX}FILE", POLICY_FILE),
        type=Path,
        required=True,
    )
    parser.add_argument(
        "-x",
        "--dry-run",
        help="Do not perform actions, but print what would be done",
        type=bool,
        default=bool(os.environ.get(f"{ENV_PREFIX}DRY_RUN", "")),
    )
    parser.add_argument(
        "-d",
        "--debug",
        "--verbose",
        default=bool(os.environ.get(f"{ENV_PREFIX}DEBUG", "")),
        type=bool,
        help="Verbose debugging output",
    )
    return parser

def purge() -> None:
    """Purge the target filesystems."""
    args = _get_options().parse_args()
    purger = Purger(
        policy_file=args.policy,
        dry_run=args.dry_run,
        debug=args.debug
    )
    asyncio.run(purger.purge())
