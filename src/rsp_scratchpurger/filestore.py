"""Work with Google Filestore shares.

Initially, create, list, and purge backups.
"""

import datetime
import logging

from google.cloud import filestore_v1

from .util import DEFAULT_BACKUP_PREFIX, backup_name_from_datetime


class FilestoreTool:
    """Each instance of the FilestoreTool class corresponds to a single
    file share.

    Backups: create a backup, list backups, purge all but the n most
    recent backups.
    """

    def __init__(
        self,
        project: str,
        location: str,
        instance: str,
        share_name: str = "share1",
        debug: bool = False,  # noqa: FBT001 FBT002
    ) -> None:
        self.project = project
        self.location = location
        self.instance = instance
        self._logger = logging.getLogger(__name__)
        level = logging.INFO
        if debug:
            level = logging.DEBUG
        logging.basicConfig(level=level)
        self._logger.setLevel(level)

        # Location must be a zone, e.g. "us-central1-b"; backups only
        #  require a region, but we'll handle the chopping.
        components = location.split("-")
        if len(components) != 3:
            raise ValueError("Location must be a zone, e.g. 'us-central1-b1")
        region = f"{components[0]}-{components[1]}"
        self.share_name = share_name
        # Unless we're using Enterprise Filestores (we don't as of
        #  January 2024), this is always "share1".

        # Default credentials should be fine--we will use WorkloadIdentity
        self._client = filestore_v1.CloudFilestoreManagerClient()
        locs = f"projects/{project}/locations/"
        self._zone_parent = f"{locs}{location}"
        self._region_parent = f"{locs}{region}"
        self._name = f"{self.instance}/{self.share_name}"
        self._logger.debug(f"FilestoreTool initialized for {self._name}")

    # Backup API

    def backup(self, prefix: str | None = None) -> None:
        """Create a backup."""
        now = datetime.datetime.now(tz=datetime.UTC)
        backup_id = backup_name_from_datetime(now, prefix=prefix)
        backup_obj = filestore_v1.types.Backup(
            description=f"Backup for {self._name} at {now!s}",
            source_instance=f"{self._zone_parent}/instances/{self.instance}",
            source_file_share=self.share_name,
        )
        request = filestore_v1.types.CreateBackupRequest(
            parent=self._region_parent,
            backup=backup_obj,
            backup_id=backup_id,
        )
        self._logger.info(f"Backup requested for {self._name}")
        # Fire-and-forget
        self._client.create_backup(request=request)

    def list_backups(self, prefix: str | None = None) -> list[str]:
        """List backups in Ready state for this file share."""
        if prefix is None:
            prefix = DEFAULT_BACKUP_PREFIX
        backup_list: list[str] = []
        results = self._client.list_backups(parent=self._region_parent)
        for backup in results:
            # Pull out instance and backup ID
            instance_id = backup.source_instance.split("/")[-1]
            backup_id = backup.name.split("/")[-1]
            # Only match the right ones for this file share
            if (
                backup.source_file_share == self.share_name
                and instance_id == self.instance
                and backup_id.startswith(prefix)
                and backup.state == filestore_v1.types.Backup.State.READY
            ):
                backup_list.append(backup_id)
                self._logger.debug(f"Matched backup {backup_id}/{instance_id}")
            else:
                rej_str = f"Rejected backup {backup_id}/{instance_id}"
                if backup.source_file_share != self.share_name:
                    rej_str += (
                        f" -- File share source {backup.source_file_share}"
                        f" did not match {self.share_name}"
                    )
                if instance_id != self.instance:
                    rej_str += (
                        f" -- Instance source {instance_id} did not match"
                        f" {self.instance}"
                    )
                if not backup_id.startswith(prefix):
                    rej_str += (
                        f" -- Backup ID {backup_id} does not start"
                        f" with {prefix}"
                    )
                if backup.state != filestore_v1.types.Backup.State.READY:
                    rej_str += f" -- Backup state {backup.state} is not READY"
                self._logger.debug(rej_str)
        # Sort backups reverse-lexigraphically, which amounts to
        # sorting them by date, newest first
        backup_list.sort(reverse=True)
        self._logger.debug(f"Backups for {self._name}: {backup_list}")
        return backup_list

    def purge_backups(self, keep: int = 6, prefix: str | None = None) -> None:
        """Purge all but 'keep' backups for this file share."""
        if keep < 1:
            raise ValueError("'keep' must be a positive integer")
        backups = self.list_backups(prefix=prefix)
        doomed = backups[keep:]
        if not doomed:
            self._logger.info("No backups requested for deletion.")
            return
        self._logger.info(
            f"Requesting backup deletion for {self._name}: {doomed}"
        )
        for victim in doomed:
            # Also fire-and-forget
            request = filestore_v1.types.DeleteBackupRequest(
                name=f"{self._region_parent}/backups/{victim}"
            )
            self._client.delete_backup(request=request)
