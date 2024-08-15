"""CLI for the filesystem purger."""

import argparse
import asyncio
import os
from pathlib import Path

import yaml
from pydantic import HttpUrl, ValidationError
from safir.logging import LogLevel, Profile

from .constants import CONFIG_FILE, ENV_PREFIX
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
    config_file = Path(override_cf) if override_cf else Path(CONFIG_FILE)
    try:
        config_obj = yaml.safe_load(config_file.read_text())
        config = Config.model_validate(config_obj)
    except (FileNotFoundError, UnicodeDecodeError, ValidationError):
        # If the file is not there, or readable, or parseable, just
        # start with an empty config and add our command-line options.
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
    # Add the Slack alert hook, if we have it.  We should not set this in the
    # config YAML, or the command line, because it's a secret.
    # It ends up getting injected into the environment (which isn't much
    # better) via a K8s secret.
    hook = os.getenv(ENV_PREFIX + "ALERT_HOOK", "")
    if hook:
        config.alert_hook = HttpUrl(url=hook)
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


def execute() -> None:
    """Make a plan, report, and purge files."""
    purger = _get_executor("Report and purge files.")
    asyncio.run(purger.execute())
