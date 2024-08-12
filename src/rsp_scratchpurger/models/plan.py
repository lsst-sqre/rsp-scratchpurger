"""Object representing files to be purged, and why."""

from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import Field
from safir.pydantic import CamelCaseModel


class FileClass(StrEnum):
    """Whether a file is large or small."""

    LARGE = "LARGE"
    SMALL = "SMALL"


class FileReason(StrEnum):
    """Whether a file is to be purged on access, creation, or modification
    time grounds.
    """

    ATIME = "ATIME"
    CTIME = "CTIME"
    MTIME = "MTIME"


class FileRecord(CamelCaseModel):
    """A file to be purged, and why."""

    path: Annotated[Path, Field(..., title="Path for file to purge.")]

    file_class: Annotated[
        FileClass, Field(..., title="Class of file to purge (large or small).")
    ]

    file_reason: Annotated[
        FileReason,
        Field(..., title="Reason to purge file (access or creation time)."),
    ]


class Plan(CamelCaseModel):
    """List of files to be purged, and why."""

    files: Annotated[list[FileRecord], Field(..., title="Files to purge")]
