"""The Purger class provides mechanisms for setting its policy,
planning actions according to its policy, reporting its plans, and
executing its plans.
"""

import asyncio
import datetime
from pathlib import Path

import structlog
import yaml
from safir.logging import Profile, configure_logging
from safir.slack.blockkit import SlackTextBlock

from .constants import ROOT_LOGGER
from .exceptions import NotLockedError, PlanNotReadyError
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
        # Anything that uses the plan should acquire the lock before
        # proceeding.
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
            await self._perform_plan()

    async def _perform_plan(self) -> None:
        # This does the actual work.
        # We split it so we can do a do-it-all run under a single lock.
        if not self._lock.locked():
            raise NotLockedError("Cannot plan: do not have lock")

        self._logger.debug(f"Reloading policy from {self._config.policy_file}")
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
            # Grab the policy.
            current_policy = self._get_directory_policy(
                path=consider, policy=policy
            )
            for root, _, files in consider.walk():
                # Check whether this root has already been handled
                # by another, more specific policy.
                if self._check_visited(root, visited):
                    self._logger.debug(f"Directory {root!s} already checked.")
                    continue
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

        self._plan = Plan(files=purge, directories=visited)

    def _get_directory_policy(
        self, path: Path, policy: Policy
    ) -> DirectoryPolicy:
        for d_policy in policy.directories:
            if d_policy.path == path:
                return d_policy
        # We don't raise a specific error because this should be a can't-
        # happen kind of error: we only ever run _get_directory_policy from
        # inside a loop over policy directories.
        raise ValueError(f"Policy for '{path}' not found")

    def _check_visited(self, root: Path, visited: list[Path]) -> bool:
        return any(vis == root or vis in root.parents for vis in visited)

    def _check_file(
        self, path: Path, policy: DirectoryPolicy, when: datetime.datetime
    ) -> FileRecord | None:
        # This is the actual meat of the purger.  We've found a file.
        # Determine if it is large or small, and then compare its three
        # times against our removal criteria.  If any of them match, mark
        # it for deletion.
        #
        # If it is a match, return a FileRecord; if not, return None.
        self._logger.debug(f"Checking {path!s} against {policy} for {when}")
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
            self._logger.debug(f"atime: {path!s}")
            return FileRecord(
                path=path,
                file_class=f_class,
                file_reason=FileReason.ATIME,
                file_interval=when - atime,
                criterion_interval=a_max,
            )
        if c_max and (ctime + c_max < when):
            self._logger.debug(f"ctime: {path!s}")
            return FileRecord(
                path=path,
                file_class=f_class,
                file_reason=FileReason.CTIME,
                file_interval=when - ctime,
                criterion_interval=c_max,
            )
        if m_max and (mtime + m_max < when):
            self._logger.debug(f"mtime: {path!s}")
            return FileRecord(
                path=path,
                file_class=f_class,
                file_reason=FileReason.MTIME,
                file_interval=when - mtime,
                criterion_interval=m_max,
            )
        return None

    async def report(self) -> None:
        """Report what directories are to be purged."""
        self._logger.debug("Awaiting lock for report()")
        async with self._lock:
            self._logger.debug("Acquired lock for report()")
            await self._perform_report()

    async def _perform_report(self) -> None:
        # This does the actual work.
        # We split it so we can do a do-it-all run under a single lock.
        if not self._lock.locked():
            raise NotLockedError("Cannot report: do not have lock")
        if self._plan is None:
            raise PlanNotReadyError("Cannot report: plan not ready")
        rpt_text = str(self._plan)
        if self._config.alert_hook is not None:
            rpt_msg = SlackTextBlock(
                heading="Purge plan",
                text=rpt_text,  # May be truncated
            )
            self._logger.info(rpt_msg)
        elif self._config.logging.profile == Profile.production:
            # Just log the plan.
            self._logger.info({"plan": self._plan})
        else:
            # Log the human-friendly plan.
            self._logger.info(rpt_text)

    async def purge(self) -> None:
        """Purge files and after-purge-empty directories."""
        if self._config.dry_run:
            self._logger.warning(
                "Cannot purge because dry_run enabled; reporting instead"
            )
            await self.report()
            return
        self._logger.debug("Awaiting lock for purge()")
        async with self._lock:
            self._logger.debug("Acquired lock for purge()")
            await self._perform_purge()

    async def _perform_purge(self) -> None:
        # This does the actual work.
        # We split it so we can do a do-it-all run under a single lock.
        if not self._lock.locked():
            raise NotLockedError("Cannot purge: do not have lock")
        if self._plan is None:
            raise PlanNotReadyError("Cannot purge: plan not ready")
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
            if victim in self._plan.directories:
                self._logger.debug(
                    f"Won't remove directory {victim!s} named"
                    " directly in policy"
                )
                continue
            if len(list(victim.glob("*"))) == 0:
                self._logger.debug(f"Removing directory {victim!s}")
                victim.rmdir()
        self._logger.debug("Purge complete")
        # We've acted on the plan, so it is no longer valid.  We must
        # rerun plan() before running purge() or report() again.
        self._plan = None

    async def execute(self) -> None:
        """Create a plan, report it, and immediately execute it.

        This is the do-it-all method and will be the usual entrypoint for
        actual use.
        """
        self._logger.debug("Awaiting lock for execute()")
        async with self._lock:
            self._logger.debug("Acquired lock for execute()")
            await self._perform_plan()
            await self._perform_report()
            await self._perform_purge()
