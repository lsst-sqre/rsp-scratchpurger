"""Command-line interface for purger."""

from pathlib import Path

import click
import yaml
from pydantic import ValidationError
from safir.asyncio import run_with_asyncio
from safir.click import display_help
from safir.logging import LogLevel, Profile

from .constants import CONFIG_FILE, ENV_PREFIX
from .models.config import Config
from .purger import Purger


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(message="%(version)s")
def main() -> None:
    """Command-line interface for purger."""


@main.command()
@click.pass_context
def help(ctx: click.Context, topic: str | None) -> None:
    """Show help for any command."""
    display_help(main, ctx, topic)


config_option = click.option(
    "-c",
    "--config-file",
    "--config",
    envvar=ENV_PREFIX + "CONFIG_FILE",
    type=click.Path(path_type=Path),
    help="Purger application configuration file",
)
policy_option = click.option(
    "-p",
    "--policy-file",
    "--policy",
    envvar=ENV_PREFIX + "POLICY_FILE",
    type=click.Path(path_type=Path),
    help="Purger policy file",
)
debug_option = click.option(
    "-d",
    "--debug",
    envvar=ENV_PREFIX + "DEBUG",
    type=bool,
    help="Enable debug logging",
)
dry_run_option = click.option(
    "-x",
    "--dry-run",
    envvar=ENV_PREFIX + "DRY_RUN",
    type=bool,
    help="Dry run: take no action, just emit what would be done.",
)


def _get_config(
    config_file: Path | None = None,
    policy_file: Path | None = None,
    debug: bool | None = None,
    dry_run: bool | None = None,
) -> Config:
    try:
        if config_file is None:
            config_file = CONFIG_FILE
        c_obj = yaml.safe_load(config_file.read_text())
        config = Config.model_validate(c_obj)
    except (FileNotFoundError, ValidationError):
        config = Config()
    if policy_file is not None:
        config.policy_file = policy_file
    if debug is not None:
        config.logging.log_level = LogLevel.DEBUG
        config.logging.profile = Profile.development
    if dry_run is not None:
        config.dry_run = dry_run
    return config


@config_option
@policy_option
@debug_option
@dry_run_option
@run_with_asyncio
async def report(
    *,
    config_file: Path | None,
    policy_file: Path | None,
    debug: bool | None,
    dry_run: bool | None,
) -> None:
    """Report what would be purged."""
    config = _get_config(
        config_file=config_file,
        policy_file=policy_file,
        debug=debug,
        dry_run=dry_run,
    )
    purger = Purger(config=config)
    await purger.plan()
    await purger.report()


@config_option
@policy_option
@debug_option
@dry_run_option
async def purge(
    *,
    config_file: Path | None,
    policy_file: Path | None,
    debug: bool | None,
    dry_run: bool | None,
) -> None:
    """Report what would be purged."""
    config = _get_config(
        config_file=config_file,
        policy_file=policy_file,
        debug=debug,
        dry_run=dry_run,
    )
    purger = Purger(config=config)
    await purger.plan()
    await purger.purge()
