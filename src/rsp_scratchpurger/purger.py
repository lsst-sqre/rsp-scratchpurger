"""The Purger class provides mechanisms for setting its policy,
planning actions according to its policy, reporting its plans, and
executing its plans.
"""

import asyncio
import datetime
from pathlib import Path

import structlog
import yaml
from safir.logging import configure_logging
from safir.slack.blockkit import SlackTextBlock

from .constants import ROOT_LOGGER
from .exceptions import PlanNotReadyError, PolicyNotFoundError
from .models.config import Config
from .models.plan import FileClass, FileReason, FileRecord, Plan
from .models.v1.policy import DirectoryPolicy, Policy


class Purger:
    """Object to plan and execute filesystem purges."""

    def __init__(
        self, config: Config, logger: structlog.BoundLogger | None = None
    ) -> None:
        self._config = config
        if logger is None:
            self._logger = structlog.get_logger(ROOT_LOGGER)
            configure_logging(
                name=ROOT_LOGGER,
                profile=config.logging.profile,
                log_level=config.logging.log_level,
                add_timestamp=config.logging.add_timestamp,
            )
        else:
            self._logger = logger
        self._logger.debug("Purger initialized")
        self._lock = asyncio.Lock()
        self._plan: Plan | None = None

    def set_policy_file(self, policy_file: Path) -> None:
        old = self._config.policy_file
        self._config.policy_file = policy_file
        self._logger.debug(f"Reset policy file: '{old}' -> '{policy_file}'")

    async def plan(self) -> None:
        """Scan our directories and assemble a plan.  We can only do this
        when an operation is not in progress, hence the lock.
        """
        self._logger.debug("Attempting to acquire lock for plan()")
        async with self._lock:
            self._logger.debug("Lock for plan() acquired.")

            self._logger.debug(
                f"Reloading policy from {self._config.policy_file}"
            )
            policy_doc = yaml.safe_load(self._config.policy_file.read_text())
            policy = Policy.model_validate(policy_doc)

            # Invalidate any current plan
            self._plan = None

            directories = policy.get_directories()

            visited: list[Path] = []

            # Set time at beginning of run
            now = datetime.datetime.now(tz=datetime.UTC)
            purge: list[FileRecord] = []
            while directories:
                # Take a directory (the longest remaining) off the end
                # of the list, and consider it.
                consider = directories.pop()
                self._logger.debug(f"Considering {consider!s}")
                for root, dirs, files in consider.walk():
                    # Grab the policy.
                    current_policy = self._get_directory_policy(
                        path=root, policy=policy
                    )
                    # Filter out any we already visited.  Yes,
                    # Path.walk() lets you modify the list dirs inside
                    # the loop.  Creepy but handy for exactly this
                    # pruning task.
                    remove_dirs = self._filter_out(dirs, visited)
                    for rem in remove_dirs:
                        self._logger.debug(f"Pruning {rem}")
                        try:
                            dirs.remove(str(rem))
                        except ValueError:
                            # We shouldn't get here, but I'm hazy on how
                            # that pruning really works.
                            self._logger.exception(
                                f"Tried to remove {rem!s} "
                                "; not in list to consider."
                            )

                    # Check each file.
                    for file in files:
                        purge_file = self._check_file(
                            path=root / file, policy=current_policy, when=now
                        )
                        if purge_file is not None:
                            self._logger.debug(
                                f"Adding {purge_file} to purge list"
                            )
                            purge.append(purge_file)
                # OK, we're done with this tree.  Skip it when
                # considering higher (shorter-named) directories.
                visited.insert(0, consider)

            self._plan = Plan(files=purge)

    def _get_directory_policy(
        self, path: Path, policy: Policy
    ) -> DirectoryPolicy:
        for d_policy in policy.directories:
            if d_policy.path == path:
                return d_policy
        raise PolicyNotFoundError(f"Policy for '{path}' not found")

    def _filter_out(self, dirs: list[str], visited: list[Path]) -> list[Path]:
        # I'm sure there's an elegant way to do this as a double
        # comprehension
        remove: list[Path] = []
        for vis in visited:
            remove.extend([Path(x) for x in dirs if x.startswith(str(vis))])
        return list(set(remove))  # Remove any duplicates

    def _check_file(
        self, path: Path, policy: DirectoryPolicy, when: datetime.datetime
    ) -> FileRecord | None:
        st = path.stat()
        # Get large-or-small policy, depending.
        size = st.st_size
        if size >= policy.threshold:
            ivals = policy.intervals.large
            f_class = FileClass.LARGE
        else:
            ivals = policy.intervals.small
            f_class = FileClass.SMALL
        atime = datetime.datetime.fromtimestamp(st.st_atime, tz=datetime.UTC)
        ctime = datetime.datetime.fromtimestamp(st.st_ctime, tz=datetime.UTC)
        mtime = datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.UTC)
        a_max = ivals.access_interval
        c_max = ivals.creation_interval
        m_max = ivals.modification_interval

        # Check the file against the intervals
        if a_max and (atime + a_max < when):
            return FileRecord(
                path=path, file_class=f_class, file_reason=FileReason.ATIME
            )
        if c_max and (ctime + c_max < when):
            return FileRecord(
                path=path, file_class=f_class, file_reason=FileReason.CTIME
            )
        if m_max and (mtime + m_max < when):
            return FileRecord(
                path=path, file_class=f_class, file_reason=FileReason.MTIME
            )
        return None

    async def report(self) -> None:
        """Report what directories are to be purged."""
        if self._plan is None:
            raise PlanNotReadyError("Cannot report: plan not ready")
        self._logger.debug("Awaiting lock for report()")
        async with self._lock:
            self._logger.debug("Acquired lock for report()")
            if self._config.alert_hook is not None:
                rpt_text = [
                    f"{x.path!s}: {x.file_reason}" for x in self._plan.files
                ]
                if len(rpt_text) == 0:
                    rpt_text = ["No files to be purged"]
                rpt_msg = SlackTextBlock(
                    heading="Purge plan",
                    text="\n".join(rpt_text),  # May be truncated
                )
                self._logger.info(rpt_msg)
            else:
                # Just log the plan.
                self._logger.info({"plan": self._plan})

    async def purge(self) -> None:
        """Purge files and after-purge-empty directories."""
        if self._config.dry_run:
            self._logger.warning(
                "Cannot purge because dry_run enabled; reporting instead"
            )
            await self.report()
            return
        if self._plan is None:
            raise PlanNotReadyError("Cannot purge: plan not ready")
        self._logger.debug("Awaiting lock for purge()")
        async with self._lock:
            self._logger.debug("Acquired lock for purge()")
            victim_dirs: set[Path] = set()
            for purge_file in self._plan.files:
                path = purge_file.path
                self._logger.debug(f"Removing {path!s}")
                path.unlink()
                victim_dirs.add(path.parent)
            self._logger.debug("File purge complete; removing empty dirs")
            vd_l = sorted(
                list(victim_dirs), key=lambda x: len(str(x)), reverse=True
            )
            for victim in vd_l:
                if len(list(victim.glob("*"))) == 0:
                    self._logger.debug(f"Removing directory {victim!s}")
                    victim.rmdir()
            self._logger.debug("Purge complete")
            self._plan = None
