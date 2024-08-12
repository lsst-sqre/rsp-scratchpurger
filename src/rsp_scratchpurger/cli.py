"""CLI for the filesystem purger."""

import argparse
import asyncio
import os
from pathlib import Path

import yaml
from pydantic import ValidationError
from safir.logging import LogLevel, Profile

from .constants import ENV_PREFIX
from .models.config import Config
from .models.v1.policy import Policy
from .purger import Purger


def _add_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "-c",
        "--config-file",
        "--config",
        help="Application configuration file",
    )
    parser.add_argument(
        "-p",
        "--policy-file",
        "--policy",
        help="Purger policy configuration file",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug logging"
    )
    parser.add_argument(
        "-x",
        "--dry-run",
        action="store_true",
        help="Do not act, but report what would be done",
    )

    return parser


def _postprocess_args_to_config(raw_args: argparse.Namespace) -> Config:
    config: Config | None = None
    override_cf = raw_args.config_file or os.getenv(
        ENV_PREFIX + "CONFIG_FILE", ""
    )
    if override_cf:
        config_file = Path(override_cf)
        try:
            config_obj = yaml.safe_load(config_file.read_text())
            config = Config.model_validate(config_obj)
        except (FileNotFoundError, UnicodeDecodeError, ValidationError):
            config = Config()
    else:
        config = Config()
    # Validate policy.  If the file is specified, use that; if not, use
    # defaults from config.
    override_pf = raw_args.policy_file or os.getenv(
        ENV_PREFIX + "POLICY_FILE", ""
    )
    policy_file = Path(override_pf) if override_pf else config.policy_file
    policy_obj = yaml.safe_load(policy_file.read_text())
    Policy.model_validate(policy_obj)
    # If we get this far, it's a legal policy file.
    config.policy_file = policy_file
    # For dry-run and debug, if specified, use that, and if not, do whatever
    # the config says.
    if raw_args.debug is not None:
        if raw_args.debug:
            config.logging.log_level = LogLevel.DEBUG
            config.logging.profile = Profile.development
        else:
            # User asked for no debug, so let's override the config.
            # I guess?
            config.logging.log_level = LogLevel.INFO
            config.logging.profile = Profile.production
    if raw_args.dry_run is not None:
        config.dry_run = raw_args.dry_run
    return config


def _get_executor(desc: str) -> Purger:
    parser = argparse.ArgumentParser(description=desc)
    parser = _add_args(parser)
    args = parser.parse_args()
    config = _postprocess_args_to_config(args)
    return Purger(config=config)


def report() -> None:
    """Report what files would be purged."""
    reporter = _get_executor("Report what files would be purged.")
    asyncio.run(reporter.plan())
    asyncio.run(reporter.report())


def purge() -> None:
    """Purge files."""
    purger = _get_executor("Purge files.")
    asyncio.run(purger.plan())
    asyncio.run(purger.purge())
